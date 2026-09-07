"""Intent and Template Router for fast analytical query execution against BigQuery rollup tables.

Bypasses the 4-stage LLM pipeline for common analytical question shapes by routing
queries to pre-materialized rollup tables with zero LLM calls.
"""

import logging
import re
import time
from typing import Any, Optional

from pwa.connections import get_bq_client
from pwa.settings import get_settings

logger = logging.getLogger("pwa.agent.template_router")


def parse_revenue_threshold(text: str) -> Optional[int]:
    """Extract numeric revenue threshold in USD from question text."""
    lower = text.lower()

    # Match $500M, 500M, 500 million, 500 million USD
    m = re.search(r"\$?\s*(\d+(?:\.\d+)?)\s*(b|billion|m|million|k|thousand)?", lower)
    if not m:
        return None

    num = float(m.group(1))
    unit = (m.group(2) or "").lower()

    if unit in ("b", "billion"):
        num *= 1_000_000_000
    elif unit in ("m", "million"):
        num *= 1_000_000
    elif unit in ("k", "thousand"):
        num *= 1_000
    elif num < 10000:
        # e.g. "500" in "over 500 revenue" usually implies 500 million in movie context
        num *= 1_000_000

    # Match nearest standard threshold (100M, 250M, 500M, 1B)
    thresholds = [100_000_000, 250_000_000, 500_000_000, 1_000_000_000]
    val = int(num)
    if val in thresholds:
        return val
    # Return closest threshold
    return min(thresholds, key=lambda t: abs(t - val))


def parse_top_n(text: str, default: int = 5) -> int:
    """Extract limit N from questions like 'Top 5 highest grossing movies'."""
    m = re.search(r"top\s*(\d+)", text.lower())
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return default


def match_template(question: str) -> Optional[dict[str, Any]]:
    """Match natural language question against template catalog.

    Returns dict with template metadata and extracted parameters, or None if no match.
    """
    q_lower = question.lower().strip()

    # 1. Director with Highest Average ROI
    if ("director" in q_lower or "directed" in q_lower) and "roi" in q_lower and ("highest" in q_lower or "average" in q_lower or "top" in q_lower):
        return {
            "template_name": "avg_roi_by_director",
            "description": "Find director with highest average ROI across movies",
            "table_name": "rollup.avg_roi_by_director",
            "params": {"limit": 1},
            "sql_generator": lambda project, params: f"""SELECT director_name, avg_roi, movie_count FROM `{project}.rollup.avg_roi_by_director` ORDER BY avg_roi DESC LIMIT {params['limit']}""",
            "formatter": lambda rows, params: f"The director with the highest average ROI across their movies is {rows[0]['director_name']}, with an average ROI of {rows[0]['avg_roi']:,.2f} across {rows[0]['movie_count']} movies." if rows else "No director data found in rollup table."
        }

    # 2. Average Cast Size by Revenue Threshold
    if "cast size" in q_lower and ("revenue" in q_lower or "gross" in q_lower or "over" in q_lower or "above" in q_lower or "$" in q_lower):
        threshold = parse_revenue_threshold(q_lower) or 500_000_000
        return {
            "template_name": "avg_cast_size_by_revenue_threshold",
            "description": "Calculate average cast size for movies over a revenue threshold",
            "table_name": "rollup.avg_cast_size_by_revenue_threshold",
            "params": {"threshold": threshold},
            "sql_generator": lambda project, params: f"""SELECT revenue_threshold, avg_cast_size, movie_count FROM `{project}.rollup.avg_cast_size_by_revenue_threshold` WHERE revenue_threshold = {params['threshold']}""",
            "formatter": lambda rows, params: f"For movies with over ${params['threshold'] / 1_000_000:,.0f}M in revenue, the average cast size is {rows[0]['avg_cast_size']} across {rows[0]['movie_count']} movies." if rows else f"No data found for revenue threshold ${params['threshold']:,.0f}."
        }

    # 3. Top Grossing Movies
    if ("grossing" in q_lower or "highest revenue" in q_lower or "top revenue" in q_lower) and ("movie" in q_lower or "film" in q_lower or "top" in q_lower):
        limit = parse_top_n(q_lower, default=5)
        return {
            "template_name": "top_grossing_movies",
            "description": "Rank top N highest-grossing movies",
            "table_name": "rollup.top_grossing_movies",
            "params": {"limit": limit},
            "sql_generator": lambda project, params: f"""SELECT rank, title, revenue, director_name FROM `{project}.rollup.top_grossing_movies` WHERE rank <= {params['limit']} ORDER BY rank ASC""",
            "formatter": lambda rows, params: "The top highest-grossing movies are:\n" + "\n".join([f"{r['rank']}. {r['title']} — ${r['revenue'] / 1_000_000:,.1f}M (Director: {r.get('director_name') or 'Unknown'})" for r in rows]) if rows else "No top grossing movies found."
        }

    return None


def route_and_execute(question: str) -> Optional[dict[str, Any]]:
    """Attempt fast-path template routing for incoming question.

    Returns structured dictionary with answer, sql, rows, bytes_scanned, latency if matched,
    or None if question should fall through to full LLM pipeline.
    """
    t0 = time.perf_counter()
    match = match_template(question)
    if not match:
        return None

    settings = get_settings()
    project = settings.gcp_project
    client = get_bq_client()

    sql = match["sql_generator"](project, match["params"])
    logger.info(f"[Template Router MATCH] template='{match['template_name']}' table='{match['table_name']}'")

    try:
        query_job = client.query(sql)
        results = list(query_job.result())
        rows = [dict(row.items()) for row in results]
        bytes_scanned = getattr(query_job, "total_bytes_processed", 0)
        answer = match["formatter"](rows, match["params"])
        elapsed = round(time.perf_counter() - t0, 4)

        return {
            "answer": answer,
            "sql": sql,
            "rows": rows,
            "bytes_scanned": bytes_scanned,
            "routing_latency": elapsed,
            "template_name": match["template_name"],
            "table_name": match["table_name"],
        }
    except Exception as exc:
        logger.warning(f"[Template Router Execution Failed]: {exc}. Falling back to LLM pipeline.")
        return None

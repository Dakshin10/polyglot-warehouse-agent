"""Intent and Template Router — Nexora Technologies Enterprise Platform.

Bypasses the 4-stage LLM pipeline for common analytical question shapes by routing
queries to pre-materialized rollup tables with zero LLM calls.

Enterprise rollup fast-paths:
  1. sales_by_year                   — annual enterprise sales summary
  2. product_sales_by_category       — product category revenue ranking
  3. supplier_purchase_volume        — top suppliers by purchase spend
  4. marketplace_order_volume_by_month — monthly marketplace order trends
  5. customer_order_frequency        — repeat customer analysis
  6. payment_totals_by_year          — payment method breakdown
  7. marketing_leads_by_seller       — marketing funnel performance
"""

import logging
import re
import time
from typing import Any, Optional

from pwa.connections import get_bq_client
from pwa.settings import get_settings

logger = logging.getLogger("pwa.agent.template_router")


def parse_top_n(text: str, default: int = 5) -> int:
    """Extract limit N from questions like 'Top 5 suppliers by revenue'."""
    m = re.search(r"top\s*(\d+)", text.lower())
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return default


def parse_year(text: str) -> Optional[int]:
    """Extract a 4-digit year from question text."""
    m = re.search(r"\b(20\d{2}|19\d{2})\b", text)
    if m:
        return int(m.group(1))
    return None


_YEAR_PATTERN = re.compile(r"\b(19\d\d|20\d\d)\b")
_TEMPORAL_KEYWORDS = frozenset(
    {
        "year",
        "years",
        "yr",
        "yrs",
        "decade",
        "decades",
        "since",
        "recently",
        "lately",
        "over time",
        "yoy",
        "year over year",
        "quarterly",
        "quarter",
    }
)
_TEMPORAL_RANGE_PATTERN = re.compile(r"\b(from|between|after|before|during)\s+(19\d\d|20\d\d|\d{4})\b", re.IGNORECASE)


def _has_temporal_qualifier(q_lower: str) -> bool:
    """Return True if question contains explicit date/year filters.

    Static rollup tables represent all-time aggregates.
    Questions filtered to specific years/months should fall through to the LLM SQL pipeline.
    Exception: templates that explicitly incorporate year filtering handle it internally.
    """
    if _YEAR_PATTERN.search(q_lower):
        return True
    if any(kw in q_lower for kw in _TEMPORAL_KEYWORDS):
        return True
    if _TEMPORAL_RANGE_PATTERN.search(q_lower):
        return True
    return False


def match_template(question: str) -> Optional[dict[str, Any]]:
    """Match natural language question against enterprise template catalog.

    Returns dict with template metadata and extracted parameters, or None if no match.
    """
    q_lower = question.lower().strip()
    s = get_settings()

    # Pre-check: rollup templates 1-3 and 5-7 represent all-time aggregates.
    # Template 4 (monthly order volume) handles years internally.
    has_temporal = _has_temporal_qualifier(q_lower)

    # 1. Sales by Year — total or annual sales revenue
    if ("sales" in q_lower or "revenue" in q_lower) and (
        "year" in q_lower or "annual" in q_lower or "by year" in q_lower or "per year" in q_lower
    ):
        return {
            "template_name": "sales_by_year",
            "description": "Annual enterprise sales revenue summary",
            "table_name": f"{s.bq_ds_rollup}.sales_by_year",
            "params": {},
            "sql_generator": lambda project, params: (
                f"SELECT order_year, order_count, total_sales_usd, avg_order_value_usd "
                f"FROM `{project}.{s.bq_ds_rollup}.sales_by_year` ORDER BY order_year"
            ),
            "formatter": lambda rows, params: (
                "Annual enterprise sales revenue:\n"
                + "\n".join(
                    f"  {r['order_year']}: {int(r['order_count']):,} orders, "
                    f"${float(r['total_sales_usd']):,.2f} total revenue"
                    for r in rows
                )
                if rows
                else "No sales data found."
            ),
        }

    # 2. Product sales by category — category revenue ranking
    if (
        not has_temporal
        and ("category" in q_lower or "categories" in q_lower)
        and (
            "revenue" in q_lower
            or "sales" in q_lower
            or "sold" in q_lower
            or "product" in q_lower
            or "category" in q_lower
        )
    ):
        limit = parse_top_n(q_lower, default=10)
        return {
            "template_name": "product_sales_by_category",
            "description": "Product category revenue ranking",
            "table_name": f"{s.bq_ds_rollup}.product_sales_by_category",
            "params": {"limit": limit},
            "sql_generator": lambda project, params: (
                f"SELECT category_name, subcategory_name, order_count, units_sold, total_revenue_usd "
                f"FROM `{project}.{s.bq_ds_rollup}.product_sales_by_category` "
                f"ORDER BY total_revenue_usd DESC LIMIT {params['limit']}"
            ),
            "formatter": lambda rows, params: (
                f"Top {params['limit']} product categories by revenue:\n"
                + "\n".join(
                    f"  {i + 1}. {r['category_name']} / {r['subcategory_name']}: "
                    f"${float(r['total_revenue_usd']):,.2f} ({int(r['units_sold']):,} units)"
                    for i, r in enumerate(rows)
                )
                if rows
                else "No product category data found."
            ),
        }

    # 3. Supplier purchase volume — top suppliers by procurement spend
    if not has_temporal and (
        "supplier" in q_lower or "vendor" in q_lower or "procurement" in q_lower or "purchase" in q_lower
    ):
        limit = parse_top_n(q_lower, default=10)
        return {
            "template_name": "supplier_purchase_volume",
            "description": "Top suppliers by total purchase spend",
            "table_name": f"{s.bq_ds_rollup}.supplier_purchase_volume",
            "params": {"limit": limit},
            "sql_generator": lambda project, params: (
                f"SELECT supplier_name, credit_rating, is_preferred, order_count, total_purchased_usd "
                f"FROM `{project}.{s.bq_ds_rollup}.supplier_purchase_volume` "
                f"ORDER BY total_purchased_usd DESC LIMIT {params['limit']}"
            ),
            "formatter": lambda rows, params: (
                f"Top {params['limit']} suppliers by total purchase volume:\n"
                + "\n".join(
                    f"  {i + 1}. {r['supplier_name']}: ${float(r['total_purchased_usd']):,.2f} "
                    f"({int(r['order_count'])} POs, credit rating: {r['credit_rating']})"
                    for i, r in enumerate(rows)
                )
                if rows
                else "No supplier data found."
            ),
        }

    # 4. Customer order distribution
    if (
        not has_temporal
        and ("customer" in q_lower or "buyer" in q_lower)
        and ("order" in q_lower or "distribution" in q_lower or "frequency" in q_lower or "repeat" in q_lower)
    ):
        return {
            "template_name": "customer_order_distribution",
            "description": "Customer order distribution summary",
            "table_name": f"{s.bq_ds_rollup}.customer_order_distribution",
            "params": {},
            "sql_generator": lambda project, params: (
                f"SELECT order_bucket, customer_count, total_orders, total_spend_usd "
                f"FROM `{project}.{s.bq_ds_rollup}.customer_order_distribution` ORDER BY total_orders DESC"
            ),
            "formatter": lambda rows, params: (
                "Customer order distribution:\n"
                + "\n".join(f"  {r['order_bucket']}: {int(r['customer_count']):,} customers" for r in rows)
                if rows
                else "No customer order distribution data found."
            ),
        }

    # 5. Employee department headcount
    if not has_temporal and (
        "employee" in q_lower or "headcount" in q_lower or "department" in q_lower or "staff" in q_lower
    ):
        return {
            "template_name": "employee_department_headcount",
            "description": "Employee department headcount summary",
            "table_name": f"{s.bq_ds_rollup}.employee_department_headcount",
            "params": {},
            "sql_generator": lambda project, params: (
                f"SELECT department_name, employee_count, salaried_count, hourly_count "
                f"FROM `{project}.{s.bq_ds_rollup}.employee_department_headcount` ORDER BY employee_count DESC"
            ),
            "formatter": lambda rows, params: (
                "Employee headcount by department:\n"
                + "\n".join(f"  {r['department_name']}: {int(r['employee_count'])} employees" for r in rows)
                if rows
                else "No department headcount data found."
            ),
        }

    # 6. Marketplace monthly sales
    if ("marketplace" in q_lower or "olist" in q_lower or "monthly" in q_lower) and (
        "sales" in q_lower or "order" in q_lower or "volume" in q_lower or "trend" in q_lower
    ):
        year = parse_year(q_lower)
        return {
            "template_name": "marketplace_monthly_sales",
            "description": "Monthly marketplace sales trends",
            "table_name": f"{s.bq_ds_rollup}.marketplace_monthly_sales",
            "params": {"year": year},
            "sql_generator": lambda project, params: (
                f"SELECT year_month, order_count, total_sales_usd "
                f"FROM `{project}.{s.bq_ds_rollup}.marketplace_monthly_sales` ORDER BY year_month"
            ),
            "formatter": lambda rows, params: (
                "Monthly marketplace sales trends:\n"
                + "\n".join(
                    f"  {r['year_month']}: {int(r['order_count']):,} orders, ${float(r['total_sales_usd']):,.2f}"
                    for r in rows
                )
                if rows
                else "No marketplace monthly sales data found."
            ),
        }

    # 7. Marketplace review ratings
    if not has_temporal and ("review" in q_lower or "star" in q_lower or "rating" in q_lower or "sentiment" in q_lower):
        return {
            "template_name": "marketplace_review_ratings",
            "description": "Marketplace review star rating distribution",
            "table_name": f"{s.bq_ds_rollup}.marketplace_review_ratings",
            "params": {},
            "sql_generator": lambda project, params: (
                f"SELECT review_score, review_count, percentage "
                f"FROM `{project}.{s.bq_ds_rollup}.marketplace_review_ratings` ORDER BY review_score DESC"
            ),
            "formatter": lambda rows, params: (
                "Marketplace review star rating distribution:\n"
                + "\n".join(
                    f"  {r['review_score']} Stars: {int(r['review_count']):,} reviews ({float(r['percentage']):.1f}%)"
                    for r in rows
                )
                if rows
                else "No review rating data found."
            ),
        }

    return None


def route_and_execute(question: str) -> Optional[dict[str, Any]]:
    """Attempt fast-path template routing for incoming question.

    Returns structured dict with answer, sql, rows, bytes_scanned, latency if matched,
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

        from pwa.rollups import get_rollup_last_refreshed

        last_refreshed = get_rollup_last_refreshed(match["table_name"])

        table_ref = f"{project}.{match['table_name']}"
        provenance = [
            {
                "table_name": table_ref,
                "type": "rollup",
                "description": f"Pre-materialized BigQuery rollup table ({match['table_name']})",
                "last_refreshed": last_refreshed,
            }
        ]

        return {
            "answer": answer,
            "sql": sql,
            "rows": rows,
            "bytes_scanned": bytes_scanned,
            "routing_latency": elapsed,
            "template_name": match["template_name"],
            "table_name": match["table_name"],
            "guardrails_applied": match.get("guardrails", []),
            "data_provenance": provenance,
        }
    except Exception as exc:
        logger.warning(f"[Template Router Execution Failed]: {exc}. Falling back to LLM pipeline.")
        return None

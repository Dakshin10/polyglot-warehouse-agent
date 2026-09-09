"""Stage 2: SqlGenerationAgent for translating user questions into BigQuery SQL."""

import asyncio
import json
import logging
import pathlib
from typing import Any, Optional

from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from pwa.agent.models import get_agent_model, get_model_for_stage
from pwa.agent.root_agent import _init_env

logger = logging.getLogger("pwa.agent.pipeline.sql_agent")

# ---------------------------------------------------------------------------
# Few-shot example loading
# ---------------------------------------------------------------------------
_FEWSHOT_PATH = pathlib.Path(__file__).parent / "examples" / "sql_fewshot.json"
_FEWSHOT_EXAMPLES: list[dict] = []
try:
    _FEWSHOT_EXAMPLES = json.loads(_FEWSHOT_PATH.read_text(encoding="utf-8"))
except Exception as _e:
    logger.warning(f"[FewShot] Could not load {_FEWSHOT_PATH}: {_e}")

_TOP_K_EXAMPLES = 5  # Number of examples injected per prompt


def _select_examples(question: str, n: int = _TOP_K_EXAMPLES) -> list[dict]:
    """Select the n most relevant few-shot examples using token overlap scoring.

    Uses a simple bag-of-words cosine-style overlap: no embeddings or network
    calls needed, deterministic, fast enough at this scale.
    """
    if not _FEWSHOT_EXAMPLES:
        return []
    q_tokens = set(question.lower().split())

    def _score(ex: dict) -> int:
        return len(q_tokens & set(ex.get("question", "").lower().split()))

    ranked = sorted(_FEWSHOT_EXAMPLES, key=_score, reverse=True)
    return ranked[:n]


def _build_fewshot_block(question: str) -> str:
    """Return a formatted few-shot block for the given question, or empty string."""
    examples = _select_examples(question)
    if not examples:
        return ""
    lines = ["\n=== EXAMPLES (use these as style references, do not copy exactly) ==="]
    for i, ex in enumerate(examples, 1):
        lines.append(f"\nExample {i}:")
        lines.append(f"  Question: {ex['question']}")
        lines.append(f"  SQL: {ex['sql']}")
    return "\n".join(lines)


SQL_GENERATION_INSTRUCTION = """You are a SQL Generation Agent for BigQuery data warehouse.
Your job is to generate ONE valid BigQuery SQL query to answer the user's question, given the grounded schema context.

=== GROUNDED SCHEMA CONTEXT ===
{schema_context}

=== MANDATORY SQL RULES ===
1. READ-ONLY SELECT ONLY: You must ONLY generate a SELECT query. Never use DDL or DML keywords (CREATE, DROP, ALTER, INSERT, UPDATE, DELETE).
2. NO SELECT *: Never use `SELECT *` on large views. Always list explicit column names.
3. ENFORCE LIMIT: Always include a LIMIT clause (default `LIMIT 100`) unless the query is an aggregate returning a single row (e.g. COUNT, SUM, AVG).
4. ALLOWED VIEWS ONLY: Only query views in the `mart` dataset: `mart.v_movie`, `mart.v_movie_credits`, `mart.v_movie_keywords`, `mart.v_movie_full`, `mart.v_integrity_exceptions`.
5. RAW SQL ONLY: Return ONLY the raw SQL query string. Do NOT wrap in ```sql ``` code blocks or add extra explanation text.
6. ROI GUARD: Any query that filters, sorts, or aggregates on `roi` MUST include `WHERE budget_usd > 1000` (or equivalent in a JOIN/subquery) to exclude movies with missing or near-zero budgets that produce astronomically inflated ROI values.
7. ONE-TO-MANY AGGREGATION GUARD: If the question requires filtering or grouping by a one-to-many-related column (such as keywords in `mart.v_movie_keywords`) AND also computing an aggregate (AVG, SUM, COUNT) over movie-level numeric columns (revenue, budget, ROI), you MUST pre-aggregate or filter the one-to-many side first (e.g., using `EXISTS`, `IN (SELECT movie_id FROM mart.v_movie_keywords WHERE ...)` or a subquery) before computing the movie-level aggregate. NEVER perform a raw JOIN against a 1-to-many table before averaging or summing movie metrics, as that double-counts rows and produces incorrect results.
{fewshot_block}"""


def build_sql_agent(schema_context_str: str = "", question: str = "", model: Any = None) -> Agent:
    _init_env()
    selected_model = get_model_for_stage("sql") if model is None else get_agent_model(model)
    context = (
        schema_context_str
        or "Allowed views: mart.v_movie, mart.v_movie_credits, mart.v_movie_keywords, mart.v_movie_full, mart.v_integrity_exceptions."
    )
    fewshot_block = _build_fewshot_block(question) if question else ""
    instruction = SQL_GENERATION_INSTRUCTION.format(schema_context=context, fewshot_block=fewshot_block)
    return Agent(
        name="SqlGenerationAgent",
        model=selected_model,
        instruction=instruction,
    )


# Note: intentionally NOT building a module-level sql_agent singleton here
# (the old `sql_agent = build_sql_agent()` added unnecessary init overhead
# at import time).


def generate_sql(
    question: str, schema_context: dict[str, Any], retry_error: Optional[str] = None, model: Any = None
) -> str:
    """Run Stage 2: Generate a SQL string from question and schema context."""
    logger.debug(f"[Stage 2 - SqlGenerationAgent Input]: question='{question}', retry_error='{retry_error}'")
    _init_env()

    context_str = json.dumps(schema_context, indent=2)
    agent = build_sql_agent(context_str, question=question, model=model)
    runner = InMemoryRunner(agent=agent, app_name="pwa_pipeline")

    user_prompt = f"Question: {question}"
    if retry_error:
        user_prompt += (
            f"\n\nPREVIOUS ATTEMPT FAILED WITH ERROR/EMPTY RESULT:\n{retry_error}\n"
            "Please fix the SQL query to resolve this error."
        )

    async def _run() -> str:
        session = await runner.session_service.create_session(app_name="pwa_pipeline", user_id="pipeline_user")
        response_text = ""
        async for event in runner.run_async(
            user_id="pipeline_user",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)]),
        ):
            if hasattr(event, "content") and event.content:
                for part in getattr(event.content, "parts", []):
                    if getattr(part, "text", None):
                        response_text += part.text
        return response_text.strip()

    raw_sql = asyncio.run(_run())

    clean_sql = raw_sql
    if clean_sql.startswith("```"):
        clean_sql = clean_sql.strip("`").removeprefix("sql").strip()

    logger.debug(f"[Stage 2 - SqlGenerationAgent Output]: SQL='{clean_sql}'")
    return clean_sql

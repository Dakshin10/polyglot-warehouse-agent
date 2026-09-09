"""Stage 4: AnswerSynthesisAgent — natural language answer + viz recommendation.

Returns a tuple ``(clean_answer: str, viz_dict: dict | None)`` so callers can
populate ``PipelineResult.viz_recommendation`` without an additional LLM call.

The LLM is instructed to append a ``<!-- VIZ_JSON {...} -->`` block after the
answer text.  ``_extract_viz_json`` strips the block and returns the parsed dict.
If the block is absent or malformed the viz_dict is ``None`` and the orchestrator
falls back to shape-based heuristics.
"""

import asyncio
import json
import logging
import re
from typing import Any

from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from pwa.agent.models import get_agent_model, get_model_for_stage
from pwa.agent.root_agent import _init_env

logger = logging.getLogger("pwa.agent.pipeline.answer_agent")

# ─── VIZ_JSON delimiter parser ────────────────────────────────────────────────

_VIZ_BLOCK_RE = re.compile(
    r"<!--\s*VIZ_JSON\s*(.*?)\s*-->",
    re.DOTALL | re.IGNORECASE,
)


def _extract_viz_json(raw: str) -> tuple[str, dict | None]:
    """Strip the VIZ_JSON comment block from *raw* and return ``(clean_text, dict)``.

    Returns ``(raw.strip(), None)`` when the block is absent or the JSON inside
    is invalid — the caller should fall back to shape heuristics in that case.
    """
    m = _VIZ_BLOCK_RE.search(raw)
    if not m:
        return raw.strip(), None
    clean = _VIZ_BLOCK_RE.sub("", raw).strip()
    try:
        data = json.loads(m.group(1).strip())
        return clean, data
    except (json.JSONDecodeError, ValueError):
        logger.debug("[AnswerAgent] VIZ_JSON block present but not valid JSON — ignoring.")
        return clean, None


# ─── System instruction ───────────────────────────────────────────────────────

ANSWER_SYNTHESIS_INSTRUCTION = """\
You are an Answer Synthesis Agent for a data warehouse assistant.
Your job is to read the user's natural language question and the query execution
results (or error explanation), and synthesize a clear, concise, and professional
natural language answer.

=== ANSWER RULES ===
1. NATURAL LANGUAGE ONLY: Synthesize the data into a helpful conversational
   response. Do NOT output raw JSON or unformatted rows.
2. ACCURACY: Base your facts strictly on the provided query result rows.
3. OUT OF SCOPE / UNANSWERABLE / ERRORS: If the query result status is 'ERROR'
   or 'EMPTY', explain clearly to the user that the information is not available
   in the warehouse mart views. Do NOT hallucinate data.

=== VISUALIZATION RECOMMENDATION ===
After your natural language answer, append EXACTLY this block (do NOT omit it):

<!-- VIZ_JSON
{
  "primary": {
    "type": "bar|line|scatter|table|metric",
    "x_col": "<column name or null>",
    "y_col": "<column name or null>",
    "reason": "<1 sentence referencing the columns and what the user is comparing>"
  },
  "alternatives": [
    {"type": "...", "x_col": "...", "y_col": "...", "reason": "..."}
  ]
}
-->

RULES for the VIZ recommendation:
- "metric": ONLY for a single aggregate value (1 row result, ≤ 2 columns).
- "line": ONLY for datetime, year-like (2015, 2016 …), or explicitly ordered
  sequences. NEVER suggest line across unordered categories (genre, director
  name, country, etc.) — that would be misleading.
- "bar": for ranked/compared categorical data where order matters.
- "scatter": for two numeric dimensions (e.g. budget vs revenue across many
  movies) where correlation or distribution is the point.
- "table": catch-all when no single chart type adds clarity over the raw data.
- x_col / y_col must exactly match a column name from the result schema, or null.
- "reason": must reference the specific columns and what the user is comparing —
  not a generic template phrase like "this is good for data".
- "alternatives": 0-2 items; omit or leave empty [] if the primary is the only
  sensible choice (e.g. metric result has no good chart alternative).
"""


# ─── Agent factory ────────────────────────────────────────────────────────────

def build_answer_agent(model: Any = None) -> Agent:
    _init_env()
    selected_model = get_model_for_stage("answer") if model is None else get_agent_model(model)
    return Agent(
        name="AnswerSynthesisAgent",
        model=selected_model,
        instruction=ANSWER_SYNTHESIS_INSTRUCTION,
    )


# Note: intentionally NOT building a module-level answer_agent singleton here
# (was adding unnecessary init overhead at import time).


# ─── Main synthesis function ──────────────────────────────────────────────────

def synthesize_answer(
    question: str,
    result: dict[str, Any],
    model: Any = None,
) -> tuple[str, dict | None]:
    """Run Stage 4: synthesize query result rows into a NL response + viz recommendation.

    Args:
        question: Original natural-language question.
        result:   Execution result dict with keys ``status``, ``rows``, etc.
        model:    Optional model override (passed by run_step_with_fallback).

    Returns:
        ``(clean_answer, viz_dict)`` where ``viz_dict`` is the parsed
        ``VizRecommendation`` dict or ``None`` if the LLM omitted / corrupted it.
    """
    logger.debug(
        f"[Stage 4 - AnswerSynthesisAgent Input]: question='{question}', "
        f"result_status='{result.get('status')}'"
    )
    _init_env()

    # Build schema context for the viz recommendation decision
    rows = result.get("rows") or []
    from pwa.ui.viz_recommendation import format_schema_for_prompt
    schema_ctx = format_schema_for_prompt(rows)

    result_json = json.dumps(result, indent=2)
    user_prompt = (
        f"USER QUESTION: {question}\n\n"
        f"RESULT SCHEMA: {schema_ctx}\n\n"
        f"QUERY EXECUTION RESULT:\n{result_json}\n\n"
        "Please provide your concise natural language response followed by the "
        "VIZ_JSON block as instructed:"
    )

    agent = build_answer_agent(model=model)
    runner = InMemoryRunner(agent=agent, app_name="pwa_pipeline")

    async def _run() -> str:
        session = await runner.session_service.create_session(
            app_name="pwa_pipeline", user_id="pipeline_user"
        )
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

    raw_response = asyncio.run(_run())
    clean_answer, viz_dict = _extract_viz_json(raw_response)

    logger.debug(
        f"[Stage 4 - AnswerSynthesisAgent Output]: answer='{clean_answer[:80]}...', "
        f"viz_dict={'present' if viz_dict else 'absent/invalid'}"
    )
    return clean_answer, viz_dict

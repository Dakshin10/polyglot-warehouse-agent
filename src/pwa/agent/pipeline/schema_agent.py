"""Stage 1: SchemaGroundingAgent for selecting relevant mart views and columns."""

import asyncio
import json
import logging
from typing import Any

from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from pwa.agent.models import get_agent_model, get_model_for_stage
from pwa.agent.root_agent import _init_env
from pwa.agent.schema_cache import get_schema_snapshot as cached_schema_snapshot

logger = logging.getLogger("pwa.agent.pipeline.schema_agent")

SCHEMA_GROUNDING_INSTRUCTION = """You are a Schema Grounding Agent for a movie warehouse data system.
Your job is to read the user's natural language question and select ONLY the relevant 1 to 3 BigQuery mart views and their specific required columns.

=== AVAILABLE MART VIEWS & COLUMNS ===
{full_schema}

=== OUTPUT FORMAT ===
You MUST return a valid JSON object ONLY with the following structure:
{{
  "relevant_views": [
    {{
      "view_name": "mart.v_movie",
      "columns": ["movie_id", "title", "revenue_usd", "release_year"]
    }}
  ],
  "reasoning": "Brief explanation of why these views/columns were selected."
}}

Do NOT include markdown formatting or code blocks (no ```json). Return raw JSON text only.
"""


def build_schema_agent(model: Any = None) -> Agent:
    _init_env()
    selected_model = get_model_for_stage("schema") if model is None else get_agent_model(model)

    try:
        snapshot = cached_schema_snapshot()
        schema_lines = []
        for view_name, cols in snapshot.items():
            col_strs = [f"  - {c['name']} ({c['type']}): {c['description']}" for c in cols]
            schema_lines.append(f"View `{view_name}`:\n" + "\n".join(col_strs))
        full_schema = "\n\n".join(schema_lines)
    except Exception as e:
        logger.warning(f"Could not fetch schema snapshot: {e}")
        full_schema = "Allowed views: mart.v_movie, mart.v_movie_credits, mart.v_movie_keywords, mart.v_movie_full, mart.v_integrity_exceptions."

    instruction = SCHEMA_GROUNDING_INSTRUCTION.format(full_schema=full_schema)

    return Agent(
        name="SchemaGroundingAgent",
        model=selected_model,
        instruction=instruction,
    )


# Note: intentionally NOT building a module-level schema_agent singleton here.
# The old `schema_agent = build_schema_agent()` call triggered a live
# INFORMATION_SCHEMA fetch on every import, causing the duplicate
# "Fetching schema snapshot" log lines seen in production.


def ground_schema(question: str, model: Any = None) -> dict[str, Any]:
    """Run Stage 1: Analyze user question and return grounded schema context."""
    logger.debug(f"[Stage 1 - SchemaGroundingAgent Input]: question='{question}'")
    _init_env()

    agent = build_schema_agent(model=model)
    runner = InMemoryRunner(agent=agent, app_name="pwa_pipeline")

    async def _run() -> str:
        session = await runner.session_service.create_session(app_name="pwa_pipeline", user_id="pipeline_user")
        response_text = ""
        async for event in runner.run_async(
            user_id="pipeline_user",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=question)]),
        ):
            if hasattr(event, "content") and event.content:
                for part in getattr(event.content, "parts", []):
                    if getattr(part, "text", None):
                        response_text += part.text
        return response_text.strip()

    raw_response = asyncio.run(_run())

    clean_json = raw_response
    if clean_json.startswith("```"):
        clean_json = clean_json.strip("`").removeprefix("json").strip()

    try:
        parsed = json.loads(clean_json)
    except Exception as e:
        logger.warning(f"Failed to parse JSON schema grounding response: {e}. Raw response: {raw_response}")
        parsed = {
            "relevant_views": [{"view_name": "mart.v_movie_full", "columns": []}],
            "reasoning": "Fallback to mart.v_movie_full due to parsing error.",
        }

    logger.debug(f"[Stage 1 - SchemaGroundingAgent Output]: {parsed}")
    return parsed

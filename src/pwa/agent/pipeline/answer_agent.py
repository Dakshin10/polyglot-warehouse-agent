"""Stage 4: AnswerSynthesisAgent for formulating natural language answers."""

import asyncio
import json
import logging
from typing import Any

from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from pwa.agent.models import get_agent_model, get_model_for_stage
from pwa.agent.root_agent import _init_env

logger = logging.getLogger("pwa.agent.pipeline.answer_agent")

ANSWER_SYNTHESIS_INSTRUCTION = """You are an Answer Synthesis Agent for a data warehouse assistant.
Your job is to read the user's natural language question and the query execution results (or error explanation), and synthesize a clear, concise, and professional natural language answer.

=== RULES ===
1. NATURAL LANGUAGE ONLY: Synthesize the data into a helpful conversational response. Do NOT output raw JSON or unformatted rows.
2. ACCURACY: Base your facts strictly on the provided query result rows.
3. OUT OF SCOPE / UNANSWERABLE / ERRORS: If the query result status is 'ERROR' or 'EMPTY' or states that the question cannot be answered from the mart views, explain clearly to the user that the information is not available in the warehouse mart views. Do NOT hallucinate data.
"""


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


def synthesize_answer(question: str, result: dict[str, Any], model: Any = None) -> str:
    """Run Stage 4: Synthesize query result rows into a natural language response."""
    logger.debug(
        f"[Stage 4 - AnswerSynthesisAgent Input]: question='{question}', result_status='{result.get('status')}'"
    )
    _init_env()

    result_json = json.dumps(result, indent=2)
    user_prompt = (
        f"USER QUESTION: {question}\n\n"
        f"QUERY EXECUTION RESULT:\n{result_json}\n\n"
        "Please provide your concise natural language response:"
    )

    agent = build_answer_agent(model=model)
    runner = InMemoryRunner(agent=agent, app_name="pwa_pipeline")

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

    final_answer = asyncio.run(_run())
    logger.debug(f"[Stage 4 - AnswerSynthesisAgent Output]: '{final_answer}'")
    return final_answer

"""[DEPRECATED / SUPERSEDE NOTICE] Single-Agent NLP Query Agent.

This module has been superseded by the 4-agent pipeline in `pwa.agent.pipeline.orchestrator`.
It is retained for backward-compatibility and fallback benchmarking.
"""

import asyncio
import logging
import os
import sys

from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from pwa.agent.bq_tools import get_mart_toolset, schema_snapshot
from pwa.logging_setup import setup_logging
from pwa.settings import get_settings

logger = logging.getLogger("pwa.agent.root_agent")

SYSTEM_INSTRUCTION_TEMPLATE = """You are a specialized Data Analytics Assistant for the Nexora Enterprise Platform (Polyglot Warehouse Agent).
Your sole purpose is to answer natural-language questions about enterprise operations, sales, products, customers, orders, logistics, marketing leads, employees, suppliers, and data integrity by querying Google BigQuery views.

=== MART SCHEMA SURFACE ===
{schema_summary}

=== STRICT OPERATIONAL RULES ===
1. READ-ONLY SQL ONLY: You must ONLY generate and execute SELECT queries. You are STRICTLY FORBIDDEN from performing any DDL or DML operations (e.g. CREATE, DROP, ALTER, INSERT, UPDATE, DELETE).
2. USE MART VIEWS ONLY: You must ONLY query the allowed enterprise views in the `mart` dataset:
   - `mart.v_sales_order_line`: Sales orders with line item amounts, product and customer details.
   - `mart.v_product_catalog`: Product catalog with pricing, category, and vendor details.
   - `mart.v_customer_360`: Unified customer 360 overview across B2B enterprise and marketplace channels.
   - `mart.v_employee_directory`: Enterprise employee directory with organizational hierarchy and demographics.
   - `mart.v_supplier_performance`: Supplier purchasing volume, vendor evaluation, and lead times.
   - `mart.v_marketplace_order_summary`: Olist marketplace orders with payment totals and customer geography.
   - `mart.v_marketplace_delivery_performance`: Olist order delivery metrics and logistics SLA fulfillment.
   - `mart.v_marketplace_review_sentiment`: Olist product review feedback and star rating scores.
   - `mart.v_marketplace_marketing_funnel`: Olist seller qualified leads, origin channels, and conversion rates.
   - `mart.v_integrity_exceptions`: Warehouse cross-domain data quality exceptions table.
   DO NOT query staging tables or raw source tables (`raw_adventureworks`, `raw_olist`, `raw_olist_marketing`).
3. NATURAL LANGUAGE SYNTHESIS: Always synthesize query results into clear, concise, and professional natural language answers. Do NOT just output raw JSON or unformatted tabular data.
4. OUT-OF-SCOPE QUESTIONS: If a user asks a question that CANNOT be answered from the available mart views (e.g. movie box office, external news, personal addresses), clearly state that the question cannot be answered from the available enterprise warehouse mart views rather than guessing or hallucinating facts.
"""


def _init_env() -> None:
    """Ensure Vertex AI and GCP credentials/project settings are populated for Gemini model access."""
    from pwa.logging_setup import apply_ipv4_only_patch

    apply_ipv4_only_patch()

    if "GOOGLE_GENAI_USE_VERTEXAI" not in os.environ:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"

    try:
        settings = get_settings()
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.gcp_project)
    except Exception:
        # No hardcoded real-project fallback: fail visibly downstream rather
        # than silently pointing Vertex AI at a specific project nobody chose.
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT_NOT_CONFIGURED")

    # Always default to us-central1 for Vertex AI — override with
    # GOOGLE_CLOUD_LOCATION env var if you need a different AI Platform region.
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")


def build_system_instruction() -> str:
    """Build the system instruction with injected mart schema snapshot context."""
    try:
        snapshot = schema_snapshot()
        schema_lines = []
        for view_name, cols in snapshot.items():
            col_strs = [f"  - {c['name']} ({c['type']}): {c['description']}" for c in cols]
            schema_lines.append(f"View `{view_name}`:\n" + "\n".join(col_strs))
        schema_summary = "\n\n".join(schema_lines)
    except Exception as e:
        logger.warning(f"Could not fetch schema snapshot for prompt injection: {e}")
        schema_summary = (
            "Allowed views: mart.v_sales_order_line, mart.v_product_catalog, "
            "mart.v_customer_360, mart.v_employee_directory, mart.v_supplier_performance, "
            "mart.v_marketplace_order_summary, mart.v_marketplace_delivery_performance, "
            "mart.v_marketplace_review_sentiment, mart.v_marketplace_marketing_funnel, "
            "mart.v_integrity_exceptions."
        )

    return SYSTEM_INSTRUCTION_TEMPLATE.format(schema_summary=schema_summary)


# Recommended latest stable Gemini model
MODEL_NAME = "gemini-2.5-flash"

_agent: Agent | None = None


def _get_agent() -> Agent:
    """Lazily build the ADK Agent on first use.

    Deliberately not built at import time: constructing it makes a live
    BigQuery call (via `build_system_instruction`) and mutates process
    environment variables, which a merely-deprecated module should not do
    just by being imported.
    """
    global _agent
    if _agent is None:
        _init_env()
        _agent = Agent(
            name="polyglot_warehouse_agent",
            model=MODEL_NAME,
            instruction=build_system_instruction(),
            tools=[get_mart_toolset()],
        )
    return _agent


def run_query(question: str) -> str:
    """Run the NLP query agent synchronously for a single question and return the answer text."""
    if not question:
        raise ValueError("Question cannot be empty.")

    _init_env()
    runner = InMemoryRunner(agent=_get_agent(), app_name="pwa_agent")

    async def _async_run() -> str:
        session = await runner.session_service.create_session(app_name="pwa_agent", user_id="pwa_user")
        response_parts: list[str] = []

        async for event in runner.run_async(
            user_id="pwa_user",
            session_id=session.id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=question)],
            ),
        ):
            if hasattr(event, "content") and event.content:
                for part in getattr(event.content, "parts", []):
                    if getattr(part, "text", None):
                        response_parts.append(part.text)

        if not response_parts:
            return "No response text generated by agent."
        return "\n".join(response_parts).strip()

    return asyncio.run(_async_run())


if __name__ == "__main__":
    setup_logging()
    if len(sys.argv) < 2:
        print('Usage: python -m pwa.agent.root_agent "<question>"')
        sys.exit(1)

    question_arg = sys.argv[1]
    print(f"\nQuestion: {question_arg}\n")
    answer = run_query(question_arg)
    print(f"Answer:\n{answer}\n")

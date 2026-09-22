"""Stage 2: Agent 2 — Governed SQL Generation Agent.

Translates GroundedIntent into deterministic BigQuery standard SQL using
Phase 2A QueryPlanner and GovernedSqlGenerator.
"""

from __future__ import annotations

import logging
from typing import Any

from pwa.semantic.loader import get_semantic_catalog
from pwa.semantic.query_planner import AnalyticalIntent, QueryPlanner
from pwa.semantic.sql_generator import GovernedSqlGenerator, SqlSafetyValidator
from pwa.agent.errors import SqlValidationError

logger = logging.getLogger("pwa.agent.pipeline.sql_agent")


class SqlGenerationAgent:
    """Agent 2 SQL Generation engine integrating Phase 2A governed compiler."""

    def __init__(
        self,
        planner: QueryPlanner | None = None,
        generator: GovernedSqlGenerator | None = None,
        safety_validator: SqlSafetyValidator | None = None,
    ) -> None:
        self.catalog = get_semantic_catalog()
        self.planner = planner or QueryPlanner(self.catalog)
        self.generator = generator or GovernedSqlGenerator()
        self.safety_validator = safety_validator or SqlSafetyValidator()

    def generate_sql_from_intent(self, intent: AnalyticalIntent, prior_error: str | None = None) -> str:
        """Compile AnalyticalIntent into safe, governed BigQuery SQL."""
        if prior_error:
            logger.warning(f"Generating SQL with prior execution error context: {prior_error}")

        # 1. Plan query using Phase 2A planner
        plan = self.planner.plan_query(intent)

        # 2. Compile SQL using GovernedSqlGenerator
        sql = self.generator.compile_sql(plan)

        # 3. Safety validation
        self.safety_validator.validate_sql(sql)

        return sql


def generate_sql(
    question: str,
    schema_context: Any = None,
    retry_error: str | None = None,
    model: Any = None,
    **kwargs: Any,
) -> str:
    """Legacy interface adapter generating SQL query string from question/schema context."""
    from pwa.agent.pipeline.schema_agent import GroundingAgent

    grounder = GroundingAgent()
    grounded = grounder.ground_question(question)

    if grounded.clarification_required:
        raise SqlValidationError(f"Clarification required: {grounded.clarification_message}")

    agent = SqlGenerationAgent()
    return agent.generate_sql_from_intent(grounded.analytical_intent, prior_error=retry_error)

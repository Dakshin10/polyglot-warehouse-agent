"""PWA Governed Agent Toolset Abstraction.

Exposes controlled Python tools for analytical operations. Agents do NOT have
direct database credentials and must interact strictly through these PWA tools.
"""

from __future__ import annotations

from typing import Any

from pwa.semantic.loader import get_semantic_catalog
from pwa.semantic.query_planner import AnalyticalIntent, QueryPlanner
from pwa.semantic.sql_generator import GovernedSqlGenerator, SqlSafetyValidator
from pwa.semantic.result_contract import SemanticQueryEngine
from pwa.governance.freshness import FreshnessTracker


def semantic_search(query: str) -> dict[str, Any]:
    """Search semantic catalog entities, measures, and metrics."""
    catalog = get_semantic_catalog()
    q_lower = query.lower()

    matches = {
        "entities": [e for name, e in catalog.entities.items() if q_lower in name.lower()],
        "measures": [m for name, m in catalog.measures.items() if q_lower in name.lower()],
        "metrics": [m for name, m in catalog.metrics.items() if q_lower in name.lower()],
    }
    return matches


def get_entity(name: str) -> dict[str, Any] | None:
    """Retrieve semantic definition for an entity."""
    catalog = get_semantic_catalog()
    e = catalog.entities.get(name)
    return e.__dict__ if e else None


def get_metric(name: str) -> dict[str, Any] | None:
    """Retrieve definition for a measure or metric."""
    catalog = get_semantic_catalog()
    m = catalog.metrics.get(name) or catalog.measures.get(name)
    return m.__dict__ if m else None


def build_query_plan(intent_dict: dict[str, Any]) -> dict[str, Any]:
    """Build QueryPlan from AnalyticalIntent dictionary representation."""
    catalog = get_semantic_catalog()
    planner = QueryPlanner(catalog)
    intent = AnalyticalIntent(**intent_dict)
    plan = planner.plan_query(intent)
    return {
        "primary_entity": plan.primary_entity.name,
        "target_entities": [e.name for e in plan.target_entities],
        "joins": [rel.name for rel in plan.joined_relationships],
    }


def generate_sql(intent_dict: dict[str, Any]) -> str:
    """Compile AnalyticalIntent into BigQuery standard SQL."""
    catalog = get_semantic_catalog()
    planner = QueryPlanner(catalog)
    generator = GovernedSqlGenerator()
    intent = AnalyticalIntent(**intent_dict)
    plan = planner.plan_query(intent)
    return generator.compile_sql(plan)


def validate_sql(sql: str) -> bool:
    """Validate AST read-only safety of SQL query."""
    validator = SqlSafetyValidator()
    return validator.validate_sql(sql)


def execute_query(intent_dict: dict[str, Any]) -> dict[str, Any]:
    """Execute analytical intent and return result contract dictionary."""
    engine = SemanticQueryEngine()
    intent = AnalyticalIntent(**intent_dict)
    res = engine.execute_intent(intent)
    return res.__dict__


def get_freshness(table_name: str) -> dict[str, Any]:
    """Check dataset freshness SLA."""
    tracker = FreshnessTracker()
    res = tracker.evaluate_freshness("bq", table_name, "2026-09-13T10:00:00Z")
    return res.__dict__

"""Governed SQL Compiler & Safety Validator for Phase 2A Semantic Layer."""

from __future__ import annotations

import logging
import re

from pwa.semantic.query_planner import QueryPlan

logger = logging.getLogger("pwa.semantic.sql_generator")

_MUTATION_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)
_RAW_DATASET_PATTERN = re.compile(r"\b(nexora_raw|raw_adventureworks|raw_olist|raw_olist_marketing)\b", re.IGNORECASE)


class SqlSafetyError(ValueError):
    """Raised when generated or submitted SQL violates analytical safety rules."""

    pass


class SqlSafetyValidator:
    """Safety validator enforcing read-only SQL execution and curated dataset boundaries."""

    def validate_sql(self, sql: str, allow_raw: bool = False) -> bool:
        """Validate that SQL statement is strictly read-only and uses authorized datasets."""
        if not sql or not sql.strip():
            raise SqlSafetyError("SQL query is empty.")

        cleaned = sql.strip()

        # 1. Enforce SELECT starting verb
        if not cleaned.upper().startswith("SELECT") and not cleaned.upper().startswith("WITH"):
            raise SqlSafetyError("Analytical queries must start with SELECT or WITH statement.")

        # 2. Block Mutation Statements
        mutation_match = _MUTATION_KEYWORDS.search(cleaned)
        if mutation_match:
            raise SqlSafetyError(f"SQL mutation keyword forbidden in analytical query: '{mutation_match.group(0)}'.")

        # 3. Block RAW dataset access unless explicitly authorized
        if not allow_raw and _RAW_DATASET_PATTERN.search(cleaned):
            raise SqlSafetyError("Direct queries against nexora_raw dataset are forbidden for analytical queries.")

        return True


class GovernedSqlGenerator:
    """Compiler converting physical QueryPlan objects into governed BigQuery SQL."""

    def __init__(self) -> None:
        self.validator = SqlSafetyValidator()

    def compile_sql(self, plan: QueryPlan) -> str:
        """Compile a QueryPlan into a governed, read-only BigQuery SQL query string."""
        select_clause_items: list[str] = []

        # 1. Dimension Columns
        for alias, attr in plan.selected_dimensions:
            select_clause_items.append(f"{alias}.{attr.column} AS {attr.name}")

        # 2. Measures
        for alias, m in plan.selected_measures:
            select_clause_items.append(f"{m.aggregation}({alias}.{m.column}) AS {m.name}")

        # 3. Derived Metrics
        for metric in plan.selected_metrics:
            select_clause_items.append(f"{metric.formula} AS {metric.name}")

        if not select_clause_items:
            select_clause_items.append("*")

        select_str = ",\n  ".join(select_clause_items)

        # From Clause
        from_str = f"`{plan.primary_entity.physical_table}` AS {plan.primary_entity.name}"

        # Join Clauses
        joined_tables = {plan.primary_entity.name}
        join_items: list[str] = []
        for rel in plan.joined_relationships:
            if rel.target_entity not in joined_tables and rel.source_entity in joined_tables:
                new_table = rel.target_entity
            elif rel.source_entity not in joined_tables and rel.target_entity in joined_tables:
                new_table = rel.source_entity
            else:
                continue

            joined_tables.add(new_table)
            join_items.append(
                f"{rel.join_type} JOIN `{new_table}` AS {new_table} "
                f"ON {rel.source_entity}.{rel.source_key} = {rel.target_entity}.{rel.target_key}"
            )
        joins_str = "\n".join(join_items)

        # Where Clause
        where_str = f"WHERE {' AND '.join(plan.filter_expressions)}" if plan.filter_expressions else ""

        # Group By Clause
        group_str = f"GROUP BY {', '.join(plan.group_by_expressions)}" if plan.group_by_expressions else ""

        # Limit Clause
        limit_str = f"LIMIT {plan.limit}"

        sql_parts = [
            f"SELECT\n  {select_str}",
            f"FROM {from_str}",
        ]
        if joins_str:
            sql_parts.append(joins_str)
        if where_str:
            sql_parts.append(where_str)
        if group_str:
            sql_parts.append(group_str)
        sql_parts.append(limit_str)

        sql = "\n".join(sql_parts) + ";"

        # Validate SQL safety
        self.validator.validate_sql(sql)
        logger.info(f"[GovernedSqlGenerator] Compiled SQL for entity `{plan.primary_entity.name}`")
        return sql

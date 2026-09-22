"""Deterministic Fast Path Executor — Nexora Enterprise Platform.

Routes simple, deterministic analytical questions directly to Phase 2A templates
and QueryPlanner, skipping LLM loops for zero-cost, low-latency analytical execution.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from pwa.semantic.loader import get_semantic_catalog
from pwa.semantic.query_planner import AnalyticalIntent, QueryPlanner
from pwa.semantic.sql_generator import GovernedSqlGenerator
from pwa.semantic.result_contract import SemanticQueryEngine, QueryResult
from pwa.semantic.templates import (
    template_metric_by_dimension,
    template_top_n_entities,
    template_metric_over_time,
)

logger = logging.getLogger("pwa.agent.fast_path")


class FastPathExecutor:
    """Fast-path execution engine for common deterministic analytical query shapes."""

    def __init__(self, engine: SemanticQueryEngine | None = None) -> None:
        self.catalog = get_semantic_catalog()
        self.planner = QueryPlanner(self.catalog)
        self.generator = GovernedSqlGenerator()
        self.engine = engine or SemanticQueryEngine(self.planner, self.generator)

    def match_and_execute(self, question: str) -> Optional[QueryResult]:
        """Try matching natural language question against deterministic template shapes.

        Returns QueryResult if matched and executed successfully, or None if no match.
        """
        q_lower = question.lower().strip()

        # Rule 1: Customer count / "how many customers"
        if ("customer" in q_lower or "customers" in q_lower) and (
            "how many" in q_lower or "total" in q_lower or "count" in q_lower
        ):
            intent = AnalyticalIntent(entities=["dim_customer"], measures=["customer_count"])
            return self.engine.execute_intent(intent)

        # Rule 2: Revenue by product category
        if ("revenue" in q_lower or "sales" in q_lower) and ("category" in q_lower or "by category" in q_lower):
            intent = template_metric_by_dimension("revenue", "product_category", limit=10)
            return self.engine.execute_intent(intent)

        # Rule 3: Top N products by revenue
        if (
            ("top" in q_lower or "best" in q_lower)
            and ("product" in q_lower or "products" in q_lower)
            and ("revenue" in q_lower or "sales" in q_lower)
        ):
            m = re.search(r"top\s*(\d+)", q_lower)
            n = int(m.group(1)) if m else 10
            intent = template_top_n_entities("revenue", "product", n=n)
            return self.engine.execute_intent(intent)

        # Rule 4: Revenue over time / monthly revenue
        if ("revenue" in q_lower or "sales" in q_lower) and (
            "month" in q_lower or "monthly" in q_lower or "over time" in q_lower
        ):
            intent = template_metric_over_time("revenue", "order_date", granularity="month", limit=12)
            return self.engine.execute_intent(intent)

        # Rule 5: Supplier purchase volume / top suppliers
        if ("supplier" in q_lower or "suppliers" in q_lower or "vendor" in q_lower) and (
            "purchase" in q_lower or "spend" in q_lower or "highest" in q_lower or "top" in q_lower
        ):
            intent = template_top_n_entities("purchase_amount", "supplier", n=10)
            return self.engine.execute_intent(intent)

        # Rule 6: Order volume / order count
        if "order count" in q_lower or "how many orders" in q_lower or "total orders" in q_lower:
            intent = AnalyticalIntent(entities=["fact_sales_order"], measures=["order_count"])
            return self.engine.execute_intent(intent)

        return None

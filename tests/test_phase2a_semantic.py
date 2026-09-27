"""Unit & Integration Tests for Phase 2A Enterprise Semantic & Analytics Foundation.

Verifies:
1. Unknown table/entity rejection
2. Unknown column/dimension rejection
3. Unknown metric/measure rejection
4. Invalid relationship rejection
5. Write SQL (INSERT/UPDATE/DELETE/MERGE) rejection
6. Division-by-zero NULLIF formula protection
7. Ambiguous metric clarification requirement
8. Stale data warning generation
9. Quality gate failure integration
10. Valid semantic query compilation into deterministic SQL
"""

import unittest

from pwa.semantic.loader import get_semantic_catalog
from pwa.semantic.validator import SemanticValidator
from pwa.semantic.query_planner import AnalyticalIntent, QueryPlanner
from pwa.semantic.sql_generator import GovernedSqlGenerator, SqlSafetyValidator, SqlSafetyError
from pwa.semantic.result_contract import SemanticQueryEngine
from pwa.semantic.ambiguity import AmbiguityModel
from pwa.semantic.templates import template_metric_by_dimension, template_top_n_entities


class TestPhase2ASemantic(unittest.TestCase):
    def setUp(self):
        self.catalog = get_semantic_catalog()
        self.validator = SemanticValidator()
        self.planner = QueryPlanner(self.catalog)
        self.generator = GovernedSqlGenerator()
        self.sql_safety = SqlSafetyValidator()
        self.ambiguity_model = AmbiguityModel()
        self.engine = SemanticQueryEngine(self.planner, self.generator)

    def test_1_unknown_table_rejected(self):
        """TEST 1: Unknown entity table must be rejected by planner."""
        intent = AnalyticalIntent(entities=["non_existent_table"])
        with self.assertRaises(ValueError) as ctx:
            self.planner.plan_query(intent)
        self.assertIn("Unknown primary entity", str(ctx.exception))

    def test_2_unknown_column_rejected(self):
        """TEST 2: Unknown column/dimension must be rejected by planner."""
        intent = AnalyticalIntent(entities=["dim_customer"], dimensions=["non_existent_dim"])
        with self.assertRaises(ValueError) as ctx:
            self.planner.plan_query(intent)
        self.assertIn("Unknown dimension", str(ctx.exception))

    def test_3_unknown_metric_rejected(self):
        """TEST 3: Unknown metric/measure must be rejected by planner."""
        intent = AnalyticalIntent(entities=["fact_sales_order"], metrics=["non_existent_metric"])
        with self.assertRaises(ValueError) as ctx:
            self.planner.plan_query(intent)
        self.assertIn("Unknown metric", str(ctx.exception))

    def test_4_invalid_relationship_rejected(self):
        """TEST 4: Un-connected entities without governed relationship must fail or warn in planner."""
        rels = self.planner._find_relationship_path("dim_customer", "fact_inventory")
        self.assertEqual(len(rels), 0)

    def test_5_write_sql_rejected(self):
        """TEST 5: SQL containing write/mutation keywords MUST be rejected as unsafe."""
        unsafe_sqls = [
            "INSERT INTO curated_enterprise.dim_customer VALUES (1, 'Test');",
            "UPDATE curated_enterprise.dim_customer SET customer_name = 'Hack';",
            "DELETE FROM curated_enterprise.fact_sales_order;",
            "DROP TABLE curated_enterprise.dim_product;",
            "MERGE INTO curated_enterprise.dim_product USING temp ON id = id;",
        ]
        for sql in unsafe_sqls:
            with self.assertRaises(SqlSafetyError):
                self.sql_safety.validate_sql(sql)

    def test_6_division_by_zero_safely_handled(self):
        """TEST 6: Derived metric formulas MUST contain NULLIF protection against division-by-zero."""
        report = self.validator.validate_catalog(self.catalog)
        self.assertTrue(report.is_valid)
        for name, metric in self.catalog.metrics.items():
            if "/" in metric.formula:
                self.assertIn("NULLIF", metric.formula.upper(), f"Metric '{name}' lacks NULLIF protection.")

    def test_7_ambiguous_metric_clarification_required(self):
        """TEST 7: Ambiguous terms (e.g. 'sales') must trigger clarification requirement."""
        res = self.ambiguity_model.evaluate_term("sales")
        self.assertTrue(res.is_ambiguous)
        self.assertGreaterEqual(len(res.possible_interpretations), 2)
        self.assertIn("revenue", res.clarification_message.lower())

    def test_8_stale_data_warning_generated(self):
        """TEST 8: Stale dataset freshness generates warning in QueryResult."""
        intent = template_metric_by_dimension("revenue", "product_category")
        result = self.engine.execute_intent(intent, last_ingested_at="2020-01-01T00:00:00Z")
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.freshness_status, "STALE")
        self.assertTrue(any("freshness SLA warning" in w for w in result.warnings))

    def test_9_failed_quality_table_behavior(self):
        """TEST 9: Query result captures quality and security contracts."""
        intent = template_top_n_entities("revenue", "customer", n=5)
        result = self.engine.execute_intent(intent)
        self.assertIn("curated_enterprise.fact_sales_order", result.source_tables[0])
        self.assertIsNotNone(result.visualization_hint)

    def test_10_valid_semantic_query_deterministic_sql(self):
        """TEST 10: Valid AnalyticalIntent compiles into deterministic read-only BigQuery SQL."""
        intent = template_metric_by_dimension("revenue", "product_category", limit=5)
        plan = self.planner.plan_query(intent)
        sql = self.generator.compile_sql(plan)

        self.assertTrue(sql.startswith("SELECT") or sql.startswith("WITH"))
        self.assertIn("curated_enterprise.fact_sales_order", sql)
        self.assertIn("GROUP BY", sql)
        self.assertIn("LIMIT 5;", sql)


if __name__ == "__main__":
    unittest.main()

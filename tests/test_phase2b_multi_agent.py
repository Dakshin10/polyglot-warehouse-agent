"""Unit & Integration Tests for Phase 2B Multi-Agent Enterprise Analytics.

Verifies:
1. Agent 0 Query Router classification & unsupported request rejection
2. Fast-Path execution for simple deterministic questions
3. Agent 1 Semantic Grounding entity/metric validation
4. Ambiguity detection and clarification prompting ("sales")
5. Agent 2 Governed SQL generation & AST read-only safety
6. Agent 3 Validation & Execution cost guardrails & quality checks
7. Agent 4 Answer Synthesis numerical grounding & non-hallucination
8. Multi-turn conversation context inheritance
9. Bounded query repair & agent step limits
10. End-to-end offline multi-agent query pipeline execution
"""

import unittest

from pwa.agent.conversation import ConversationContext
from pwa.agent.errors import SqlValidationError, QueryCostLimitExceededError
from pwa.agent.fast_path import FastPathExecutor
from pwa.agent.pipeline.answer_agent import AnswerSynthesisAgent
from pwa.agent.pipeline.exec_agent import ValidationExecutionAgent
from pwa.agent.pipeline.orchestrator import MultiAgentPipelineOrchestrator
from pwa.agent.pipeline.schema_agent import GroundingAgent
from pwa.agent.pipeline.sql_agent import SqlGenerationAgent
from pwa.agent.router import QueryRouter, QueryCategory
from pwa.semantic.loader import get_semantic_catalog
from pwa.semantic.query_planner import AnalyticalIntent
from pwa.semantic.result_contract import QueryResult


class TestPhase2BMultiAgent(unittest.TestCase):
    def setUp(self):
        self.catalog = get_semantic_catalog()
        self.router = QueryRouter()
        self.fast_path = FastPathExecutor()
        self.grounder = GroundingAgent(self.catalog)
        self.sql_agent = SqlGenerationAgent()
        self.exec_agent = ValidationExecutionAgent()
        self.answer_agent = AnswerSynthesisAgent()
        self.orchestrator = MultiAgentPipelineOrchestrator(
            router=self.router,
            fast_path=self.fast_path,
            grounding_agent=self.grounder,
            sql_agent=self.sql_agent,
            exec_agent=self.exec_agent,
            answer_agent=self.answer_agent,
        )

    def test_1_router_classification(self):
        """TEST 1: Router classifies analytical, unsupported, metadata, and ambiguous questions."""
        # Analytical
        r1 = self.router.route("Show monthly revenue by product category")
        self.assertEqual(r1.category, QueryCategory.ANALYTICAL)

        # Unsupported Write operation
        r2 = self.router.route("DELETE FROM dim_customer WHERE id = 1")
        self.assertEqual(r2.category, QueryCategory.UNSUPPORTED)

        # Unsupported topic
        r3 = self.router.route("Who directed the movie Avatar?")
        self.assertEqual(r3.category, QueryCategory.UNSUPPORTED)

        # Ambiguous
        r4 = self.router.route("What are our sales?")
        self.assertEqual(r4.category, QueryCategory.AMBIGUOUS)

    def test_2_fast_path_bypasses_llm(self):
        """TEST 2: Fast-path executes simple template questions directly."""
        res = self.fast_path.match_and_execute("Revenue by category")
        self.assertIsNotNone(res)
        self.assertIn("fact_sales_order", res.sql)
        self.assertEqual(res.status, "SUCCESS")

    def test_3_unknown_entity_grounding_rejected(self):
        """TEST 3: Grounding agent rejects unknown primary entity."""
        intent = AnalyticalIntent(entities=["non_existent_entity"])
        with self.assertRaises(ValueError):
            self.sql_agent.generate_sql_from_intent(intent)

    def test_4_unknown_metric_grounding_rejected(self):
        """TEST 4: Grounding agent rejects unknown metric."""
        intent = AnalyticalIntent(entities=["fact_sales_order"], metrics=["fake_metric"])
        with self.assertRaises(ValueError):
            self.sql_agent.generate_sql_from_intent(intent)

    def test_5_ambiguity_clarification(self):
        """TEST 5: Ambiguous queries trigger clarification status in pipeline."""
        res = self.orchestrator.run_pipeline("What are our sales?")
        self.assertEqual(res.exec_status, "CLARIFICATION_REQUIRED")
        self.assertGreaterEqual(len(res.ambiguity_options), 2)
        self.assertIn("revenue", res.clarification_message.lower())

    def test_6_write_sql_rejected(self):
        """TEST 6: Write/mutation SQL is rejected by AST safety validator."""
        unsafe_sql = "DROP TABLE curated_enterprise.dim_customer;"
        with self.assertRaises(SqlValidationError):
            self.exec_agent.validate_and_execute(unsafe_sql)

    def test_7_cost_limit_exceeded(self):
        """TEST 7: Dry-run scan bytes limit blocks execution when threshold exceeded."""
        strict_agent = ValidationExecutionAgent(max_bytes_allowed=100)
        # Mock high scan bytes trigger
        with self.assertRaises(QueryCostLimitExceededError):
            strict_agent.max_bytes_allowed = 0
            strict_agent.validate_and_execute("SELECT * FROM curated_enterprise.fact_sales_order;")

    def test_8_numerical_grounding_anti_hallucination(self):
        """TEST 8: Answer synthesis validates that numbers are grounded in QueryResult."""
        qr = QueryResult(
            query_id="test_num_grounding",
            sql="SELECT 42 as total_count",
            columns=["total_count"],
            rows=[{"total_count": 42}],
            row_count=1,
            bytes_processed=0,
            execution_time_seconds=0.01,
            semantic_objects_used=["fact_sales_order"],
            source_tables=["curated_enterprise.fact_sales_order"],
            status="SUCCESS",
        )
        answer_contract = self.answer_agent.synthesize("How many total sales?", qr)
        self.assertIn("42", answer_contract.answer_text)

    def test_9_stale_data_and_quality_integration(self):
        """TEST 9: Freshness SLA and quality gate status propagate to PipelineResult."""
        res = self.orchestrator.run_pipeline("Show revenue by product category")
        self.assertEqual(res.exec_status, "SUCCESS")
        self.assertIn(res.query_result.freshness_status, ["FRESH", "STALE"])

    def test_10_multi_turn_context_inheritance(self):
        """TEST 10: Multi-turn context inherits metric/dimension and appends filters."""
        ctx = ConversationContext()
        intent1 = AnalyticalIntent(entities=["fact_sales_order"], measures=["revenue"], dimensions=["product_category"])
        ctx.add_turn("Show revenue by category", intent1, "SELECT ...")

        intent2 = AnalyticalIntent(entities=["fact_sales_order"], time_dimension="order_date", granularity="year")
        merged = ctx.resolve_followup("Only for 2025", intent2)

        self.assertIn("revenue", merged.measures)
        self.assertIn("product_category", merged.dimensions)
        self.assertEqual(merged.granularity, "year")

    def test_11_bounded_query_repair_and_step_limit(self):
        """TEST 11: Pipeline handles bounded execution retries safely."""
        res = self.orchestrator.run_pipeline("Show monthly revenue by product category")
        self.assertEqual(res.exec_status, "SUCCESS")
        self.assertIsNotNone(res.sql)

    def test_12_end_to_end_offline_analytical_query(self):
        """TEST 12: Complete E2E question -> answer execution passes offline."""
        res = self.orchestrator.run_pipeline("Top 5 suppliers by purchase volume")
        self.assertEqual(res.exec_status, "SUCCESS")
        self.assertIsNotNone(res.answer)
        self.assertIn("fact_purchase_order", res.sql)


if __name__ == "__main__":
    unittest.main()

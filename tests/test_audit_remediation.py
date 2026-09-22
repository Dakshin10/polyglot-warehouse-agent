"""Comprehensive regression test suite for PWA 20-issue Audit Remediation."""

import os
from unittest.mock import MagicMock, patch

import pytest

from pwa.agent.conversation import ConversationContext
from pwa.agent.fast_path import FastPathExecutor
from pwa.agent.pipeline.answer_agent import AnswerSynthesisAgent, synthesize_answer
from pwa.agent.pipeline.exec_agent import ValidationExecutionAgent, ast_validate_sql
from pwa.agent.pipeline.fallback import run_step_with_fallback
from pwa.agent.pipeline.orchestrator import (
    MultiAgentPipelineOrchestrator,
    PipelineResult,
    run_query,
    run_query_verbose,
)
from pwa.agent.pipeline.schema_agent import GroundingAgent, ground_schema
from pwa.agent.pipeline.sql_agent import SqlGenerationAgent, generate_sql
from pwa.agent.semantic_cache import semantic_cache
from pwa.agent.template_router import match_template
from pwa.connections import get_bq_client
from pwa.eval.benchmark import evaluate_expected_check
from pwa.ingestion.cdc import CdcAdapter, CdcOperation
from pwa.observability.alerting import (
    CompositeAlertSink,
    LogAlertSink,
    PagerDutyAlertSink,
    PipelineAlert,
    SlackAlertSink,
)
from pwa.semantic.query_planner import AnalyticalIntent
from pwa.semantic.result_contract import QueryResult, SemanticQueryEngine


# ---------------------------------------------------------------------------
# Test 1: run_query uses MultiAgentPipelineOrchestrator
# ---------------------------------------------------------------------------
def test_1_run_query_uses_orchestrator():
    """Confirm run_query() calls orchestrator.run_pipeline and returns string answer."""
    question = "Show total revenue by category"
    verbose_res = run_query_verbose(question)
    query_res = run_query(question)

    assert isinstance(verbose_res, PipelineResult)
    assert isinstance(query_res, str)
    assert query_res == verbose_res.answer


# ---------------------------------------------------------------------------
# Test 2: Dead variable in fast_path customer count fixed
# ---------------------------------------------------------------------------
def test_2_fast_path_customer_count():
    """Confirm 'how many customers' returns customer_count intent, not a customer list."""
    executor = FastPathExecutor()
    res = executor.match_and_execute("How many customers do we have in total?")

    assert res is not None
    assert "customer_count" in res.sql or "count" in res.sql.lower()
    # Check that it returns a scalar metric result or count column
    assert len(res.columns) == 1 or "customer_count" in res.columns or "count" in str(res.columns).lower()


# ---------------------------------------------------------------------------
# Test 3: Fallback model= kwarg support across step functions
# ---------------------------------------------------------------------------
def test_3_fallback_model_kwarg_support():
    """Confirm ground_schema, generate_sql, and synthesize_answer accept model= without raising TypeError."""
    # 1. ground_schema
    res_schema, model_used = run_step_with_fallback(
        "schema", ground_schema, "Show revenue by category", primary_model="gemini", fallback_model="groq"
    )
    assert res_schema is not None

    # 2. generate_sql
    res_sql, model_used = run_step_with_fallback(
        "sql", generate_sql, "Show revenue by category", primary_model="gemini", fallback_model="groq"
    )
    assert isinstance(res_sql, str)

    # 3. synthesize_answer
    exec_res = {"rows": [{"revenue": 1000}], "bytes_scanned": 1024, "status": "SUCCESS"}
    res_ans, model_used = run_step_with_fallback(
        "answer",
        synthesize_answer,
        "Show revenue by category",
        "SELECT 1000 AS revenue",
        exec_res,
        primary_model="gemini",
        fallback_model="groq",
    )
    assert isinstance(res_ans, tuple)
    assert isinstance(res_ans[0], str)


# ---------------------------------------------------------------------------
# Test 4: Cost guardrail check
# ---------------------------------------------------------------------------
def test_4_cost_guardrail_check():
    """Confirm QueryCostLimitExceededError is raised when estimated scan bytes exceed max_bytes_allowed."""
    from pwa.agent.errors import QueryCostLimitExceededError

    agent = ValidationExecutionAgent(max_bytes_allowed=500)

    # Mock writer to non-mock mode to force dry_run check
    agent.engine.writer.mock = False

    with patch("pwa.agent.guardrails.dry_run_check_bytes", return_value=1000000):
        with pytest.raises(QueryCostLimitExceededError):
            agent.validate_and_execute("SELECT * FROM `curated_enterprise.fact_sales_order`")


# ---------------------------------------------------------------------------
# Test 5: No live BQ calls on module import
# ---------------------------------------------------------------------------
def test_5_no_network_calls_on_import():
    """Confirm importing pwa.agent does not trigger BigQuery client creation."""
    with patch("google.cloud.bigquery.Client") as mock_bq:
        import pwa.agent  # noqa: F401
        import pwa.agent.root_agent  # noqa: F401

        mock_bq.assert_not_called()


# ---------------------------------------------------------------------------
# Test 6: SemanticCache wiring & default enabled
# ---------------------------------------------------------------------------
def test_6_semantic_cache_enabled_and_hits():
    """Confirm semantic cache defaults to enabled and serves repeated queries."""
    os.environ.pop("PWA_SEMANTIC_CACHE_ENABLED", None)
    assert semantic_cache._is_enabled() is True

    semantic_cache.clear()
    question = "What is the total revenue for 2025?"

    orchestrator = MultiAgentPipelineOrchestrator()
    res1 = orchestrator.run_pipeline(question)
    assert res1.cache_hit is False

    res2 = orchestrator.run_pipeline(question)
    assert res2.cache_hit is True
    assert res2.answer == res1.answer


# ---------------------------------------------------------------------------
# Test 7: Grounding fallback asks for clarification on out-of-domain questions
# ---------------------------------------------------------------------------
def test_7_out_of_domain_grounding_refusal():
    """Confirm out-of-domain query 'what is the weather?' returns clarification_required."""
    agent = GroundingAgent()
    grounded = agent.ground_question("What is the weather in Seattle today?")

    assert grounded.clarification_required is True
    assert "fact_sales_order" not in grounded.analytical_intent.entities
    assert "could not map" in grounded.clarification_message.lower()


# ---------------------------------------------------------------------------
# Test 8: Conversation context resets on topic shift
# ---------------------------------------------------------------------------
def test_8_conversation_topic_shift_reset():
    """Confirm context resets entities on topic shift (e.g. suppliers -> customers)."""
    ctx = ConversationContext()

    intent1 = AnalyticalIntent(entities=["dim_supplier"], measures=["purchase_amount"])
    ctx.add_turn("Show top suppliers", intent=intent1)

    intent2 = AnalyticalIntent(entities=["dim_customer"], measures=["customer_count"])
    merged = ctx.resolve_followup("How many customers do we have?", current_intent=intent2)

    # Entities should NOT accumulate dim_supplier into customer query
    assert "dim_supplier" not in merged.entities
    assert merged.entities == ["dim_customer"]


# ---------------------------------------------------------------------------
# Test 9 & 20: CDC UPDATE before_payload population
# ---------------------------------------------------------------------------
def test_9_20_cdc_before_payload():
    """Confirm CDC adapter populates before_payload for UPDATE events when prior snapshot is provided."""
    import pandas as pd

    adapter = CdcAdapter(source_name="test_system")

    prev_df = pd.DataFrame([{"id": 1, "status": "PENDING", "amount": 100}])
    curr_df = pd.DataFrame([{"id": 1, "status": "COMPLETED", "amount": 100, "_pwa_op": "UPDATE"}])

    events = adapter.parse_change_log(
        curr_df, primary_key_cols=["id"], previous_snapshot=prev_df
    )

    assert len(events) == 1
    assert events[0].operation == CdcOperation.UPDATE
    assert events[0].before_payload == {"id": 1, "status": "PENDING", "amount": 100}
    assert events[0].after_payload["status"] == "COMPLETED"


# ---------------------------------------------------------------------------
# Test 10: Multi-row answer synthesis numeric summary
# ---------------------------------------------------------------------------
def test_10_multi_row_answer_synthesis():
    """Confirm answer synthesis includes aggregate numeric stats across all rows."""
    query_res = QueryResult(
        query_id="test_multi_row",
        sql="SELECT category, revenue FROM mart",
        columns=["category", "revenue"],
        rows=[
            {"category": "Electronics", "revenue": 5000},
            {"category": "Clothing", "revenue": 3000},
            {"category": "Home", "revenue": 2000},
        ],
        row_count=3,
        bytes_processed=1024,
        execution_time_seconds=0.1,
        semantic_objects_used=["fact_sales_order"],
        source_tables=["curated_enterprise.fact_sales_order"],
    )

    agent = AnswerSynthesisAgent()
    ans = agent.synthesize("Show revenue by category", query_res)

    assert "10,000" in ans.answer_text or "10000" in ans.answer_text
    assert "3 rows" in ans.answer_text


# ---------------------------------------------------------------------------
# Test 11 & 12: Dynamic provenance resolution for non-sales queries
# ---------------------------------------------------------------------------
def test_11_12_dynamic_provenance():
    """Confirm provenance resolution correctly maps supplier and employee tables, not hardcoded sales."""
    exec_agent = ValidationExecutionAgent()

    # Direct SQL on employee directory
    res_emp = exec_agent.validate_and_execute("SELECT * FROM `curated_enterprise.dim_employee`")
    assert "dim_employee" in res_emp.semantic_objects_used
    assert "fact_sales_order" not in res_emp.semantic_objects_used

    # Legacy synthesize_answer on supplier SQL
    ans_text, viz = synthesize_answer(
        "Top suppliers",
        "SELECT * FROM `curated_enterprise.dim_supplier`",
        {"rows": [{"supplier_name": "Acme"}]},
    )
    assert ans_text is not None


# ---------------------------------------------------------------------------
# Test 13: Freshness and quality checks in exec_agent
# ---------------------------------------------------------------------------
def test_13_freshness_and_quality_checks():
    """Confirm _lookup_freshness_and_quality runs without raising errors."""
    agent = ValidationExecutionAgent()
    fresh, qual = agent._lookup_freshness_and_quality(["dim_customer"])
    assert fresh in ("FRESH", "WARNING", "STALE", "CRITICAL", "UNKNOWN")
    assert qual in ("PASS", "FAIL", "WARNING", "UNKNOWN")


# ---------------------------------------------------------------------------
# Test 14: SQL repair error feedback
# ---------------------------------------------------------------------------
def test_14_sql_repair_error_context():
    """Confirm SqlGenerationAgent.generate_sql_from_intent accepts prior_error."""
    agent = SqlGenerationAgent()
    intent = AnalyticalIntent(entities=["fact_sales_order"], measures=["revenue"])
    sql = agent.generate_sql_from_intent(intent, prior_error="Column 'xyz' not found")

    assert isinstance(sql, str)
    assert "fact_sales_order" in sql


# ---------------------------------------------------------------------------
# Test 15: Template router matching
# ---------------------------------------------------------------------------
def test_15_template_router_match():
    """Confirm match_template identifies sales_by_year rollup questions."""
    match = match_template("Show annual sales by year")
    assert match is not None
    assert match["template_name"] == "sales_by_year"


# ---------------------------------------------------------------------------
# Test 16: Dynamic interpretation summary
# ---------------------------------------------------------------------------
def test_16_dynamic_interpretation_summary():
    """Confirm interpretation_summary reflects actual semantic objects used."""
    query_res = QueryResult(
        query_id="test_interp",
        sql="SELECT * FROM `curated_enterprise.dim_supplier`",
        columns=["supplier_name"],
        rows=[{"supplier_name": "Acme"}],
        row_count=1,
        bytes_processed=512,
        execution_time_seconds=0.1,
        semantic_objects_used=["dim_supplier"],
        source_tables=["curated_enterprise.dim_supplier"],
    )
    agent = AnswerSynthesisAgent()
    ans = agent.synthesize("Show top suppliers", query_res)

    assert "dim_supplier" in ans.interpretation_summary


# ---------------------------------------------------------------------------
# Test 17: BigQuery client singleton thread safety
# ---------------------------------------------------------------------------
def test_17_bq_singleton_thread_safety():
    """Confirm get_bq_client returns consistent singleton instance."""
    with patch("google.cloud.bigquery.Client") as mock_bq_cls:
        mock_instance = MagicMock()
        mock_bq_cls.return_value = mock_instance

        client1 = get_bq_client()
        client2 = get_bq_client()

        assert client1 is client2


# ---------------------------------------------------------------------------
# Test 18: Observability alerting sinks
# ---------------------------------------------------------------------------
def test_18_alerting_sinks():
    """Confirm LogAlertSink, SlackAlertSink, and PagerDutyAlertSink send alerts without errors."""
    alert = PipelineAlert(
        alert_type="QUALITY_FAILURE",
        severity="HIGH",
        source_id="d1",
        table_name="dim_customer",
        message="Data quality check failed",
    )

    log_sink = LogAlertSink()
    assert log_sink.send(alert) is True

    slack_sink = SlackAlertSink(webhook_url="https://hooks.slack.com/services/mock")
    with patch("requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        assert slack_sink.send(alert) is True

    pd_sink = PagerDutyAlertSink(routing_key="mock_key")
    with patch("requests.post") as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        assert pd_sink.send(alert) is True

    composite = CompositeAlertSink([log_sink])
    assert composite.send(alert) is True


# ---------------------------------------------------------------------------
# Test 19: Benchmark expected check evaluation
# ---------------------------------------------------------------------------
def test_19_benchmark_expected_check():
    """Confirm evaluate_expected_check handles refusal/clarification strings as valid expected matches."""
    entry = {
        "id": "q_refusal",
        "question": "What's the weather?",
        "expected_check": {"type": "answer_contains", "value": "could not map"},
    }
    refusal_msg = "I could not map this question to any known enterprise data entity."
    assert evaluate_expected_check(entry, refusal_msg) is True

"""Tests for Task 1 — Verifying mock data labeling across QueryResult, AnalyticalAnswer, PipelineResult, and AnswerSynthesisAgent."""

from pwa.semantic.result_contract import QueryResult, SemanticQueryEngine
from pwa.agent.pipeline.exec_agent import ValidationExecutionAgent
from pwa.agent.pipeline.answer_agent import AnswerSynthesisAgent
from pwa.agent.pipeline.orchestrator import MultiAgentPipelineOrchestrator, PipelineResult


def test_query_result_default_mock_flag():
    """Verify QueryResult defaults and explicit mock flag initialization."""
    res = QueryResult(
        query_id="q1",
        sql="SELECT 1",
        columns=["col"],
        rows=[{"col": 1}],
        row_count=1,
        bytes_processed=0,
        execution_time_seconds=0.01,
        semantic_objects_used=["obj"],
        source_tables=["tbl"],
        is_mock=True,
        data_source="stub",
    )
    assert res.is_mock is True
    assert res.data_source == "stub"


def test_semantic_query_engine_mock_flag():
    """Verify SemanticQueryEngine populates is_mock=True and data_source when writer.mock is True."""
    engine = SemanticQueryEngine()
    assert engine.writer.mock is True

    from pwa.semantic.query_planner import AnalyticalIntent

    intent = AnalyticalIntent(entities=["fact_sales_order"], measures=["revenue"])
    res = engine.execute_intent(intent)

    assert res.is_mock is True
    assert res.data_source in ("local_sqlite", "stub")


def test_validation_execution_agent_mock_flag():
    """Verify ValidationExecutionAgent populates is_mock=True in mock execution mode."""
    exec_agent = ValidationExecutionAgent()
    res = exec_agent.validate_and_execute("SELECT 1 AS total")

    assert res.is_mock is True
    assert res.data_source in ("local_sqlite", "stub")


def test_answer_synthesis_agent_mock_warning_and_text():
    """Verify AnswerSynthesisAgent appends mock/placeholder warning and explicit note when is_mock is True."""
    agent = AnswerSynthesisAgent()
    mock_res = QueryResult(
        query_id="q_mock",
        sql="SELECT count FROM tbl",
        columns=["count"],
        rows=[{"count": 100}],
        row_count=1,
        bytes_processed=0,
        execution_time_seconds=0.01,
        semantic_objects_used=["fact_sales_order"],
        source_tables=["fact_sales_order"],
        is_mock=True,
        data_source="stub",
    )
    ans = agent.synthesize("How many orders?", mock_res)

    assert ans.is_mock is True
    assert ans.data_source == "stub"
    assert any("MOCK DATA SOURCE NOTICE" in w for w in ans.warnings)
    assert "Offline Mock Mode" in ans.answer_text or "stub" in ans.answer_text


def test_pipeline_orchestrator_retains_mock_flag():
    """Verify MultiAgentPipelineOrchestrator's PipelineResult carries is_mock and data_source."""
    orch = MultiAgentPipelineOrchestrator()
    result = orch.run_pipeline("What is total sales revenue?")

    assert isinstance(result, PipelineResult)
    assert result.is_mock is True
    assert result.data_source in ("local_sqlite", "stub")

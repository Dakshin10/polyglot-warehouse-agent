"""Integration tests for Phase 3 AnalyticalWorkflowOrchestrator pipeline wiring."""

from pwa.agent.pipeline.orchestrator import run_query, run_query_verbose


def test_analytical_workflow_wiring_end_to_end():
    # Diagnostic question matching intent router revenue_decline_analysis / diagnostic keywords
    question = "Decompose revenue decline diagnostic for product categories"
    res = run_query_verbose(question)

    assert res.exec_status == "SUCCESS"
    assert res.routing_category == "ANALYTICAL_WORKFLOW"
    assert "Multi-Step Analytical Workflow" in res.answer
    assert "Key Findings & Insights" in res.answer
    assert res.rows is not None
    assert len(res.rows) > 0


def test_public_run_query_analytical_workflow():
    answer = run_query("Decompose revenue decline across product categories")
    assert "Multi-Step Analytical Workflow" in answer

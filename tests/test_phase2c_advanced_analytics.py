"""
Phase 2C Advanced Enterprise Analytics & Data Science Foundation Tests
Verifies analytical workflow execution, period comparisons, contribution, RFM, cohorts, funnel, ABC classification,
descriptive anomaly detection, feature engineering, temporal leakage protection, workflow cost guardrails, and causal safety.
"""

import pytest
from pwa.analytics.models import AnalyticalWorkflow, WorkflowStep, StepOperation, AnalyticalOperator
from pwa.analytics.operators import (
    compute_period_comparison,
    compute_contribution,
    compute_rfm_segments,
    compute_funnel_metrics,
    compute_abc_classification,
)
from pwa.analytics.anomaly import DescriptiveAnomalyDetector
from pwa.analytics.orchestrator import AnalyticalWorkflowOrchestrator
from pwa.analytics.insight import AnalyticalInsight, InsightType
from pwa.analytics.domains import analyze_inventory_domain, analyze_variance_domain
from pwa.analytics.templates import get_workflow_template
from pwa.datascience.features.features import FeatureRegistry
from pwa.datascience.snapshots.snapshots import AnalyticalSnapshotEngine
from pwa.datascience.training_data.leakage import TemporalLeakageValidator, TemporalLeakageError
from pwa.agent.errors import QueryCostLimitExceededError, AgentStepLimitError


def test_1_analytical_workflow_orchestrator():
    workflow = get_workflow_template("revenue_decline_analysis")
    assert workflow is not None
    assert len(workflow.steps) == 5

    orchestrator = AnalyticalWorkflowOrchestrator()
    res = orchestrator.execute_workflow(workflow)

    assert res["status"] == "SUCCESS"
    assert len(res["completed_steps"]) == 5
    assert len(res["insights"]) == 1
    assert res["telemetry"]["total_bytes_processed"] > 0


def test_2_period_comparison_operator():
    res = compute_period_comparison(120000, 100000, "YoY")
    assert res["absolute_change"] == 20000.0
    assert res["percentage_change"] == 20.0

    # Safe division check (zero previous value)
    res_zero = compute_period_comparison(120000, 0, "YoY")
    assert res_zero["absolute_change"] == 120000.0
    assert res_zero["percentage_change"] is None


def test_3_contribution_operator():
    rows = [
        {"product_category": "Electronics", "revenue": 50000},
        {"product_category": "Apparel", "revenue": 30000},
        {"product_category": "Home Goods", "revenue": 20000},
    ]
    contrib = compute_contribution(rows, "product_category", "revenue")
    assert len(contrib) == 3
    assert contrib[0]["product_category"] == "Electronics"
    assert contrib[0]["contribution_percentage"] == 50.0
    assert contrib[1]["contribution_percentage"] == 30.0
    assert contrib[2]["contribution_percentage"] == 20.0


def test_4_customer_rfm_segmentation():
    rows = [
        {"customer_id": "C1", "recency_days": 10, "order_count": 25, "total_revenue": 10000},
        {"customer_id": "C2", "recency_days": 400, "order_count": 1, "total_revenue": 50},
    ]
    rfm = compute_rfm_segments(rows, "customer_id", "recency_days", "order_count", "total_revenue")
    assert len(rfm) == 2
    assert rfm[0]["segment"] == "Champions"
    assert rfm[1]["segment"] == "Lost"


def test_5_marketing_funnel_conversion():
    rows = [
        {"stage_name": "Lead", "lead_count": 1000},
        {"stage_name": "Qualified", "lead_count": 500},
        {"stage_name": "Closed", "lead_count": 100},
    ]
    funnel = compute_funnel_metrics(rows, "stage_name", "lead_count")
    assert len(funnel) == 3
    assert funnel[0]["overall_conversion_pct"] == 100.0
    assert funnel[1]["overall_conversion_pct"] == 50.0
    assert funnel[2]["overall_conversion_pct"] == 10.0
    assert funnel[2]["dropoff_pct"] == 80.0


def test_6_abc_pareto_classification():
    rows = [
        {"product_id": "P1", "revenue": 7000},
        {"product_id": "P2", "revenue": 1500},
        {"product_id": "P3", "revenue": 1000},
        {"product_id": "P4", "revenue": 500},
    ]
    abc = compute_abc_classification(rows, "product_id", "revenue")
    assert len(abc) == 4
    assert abc[0]["product_id"] == "P1"
    assert abc[0]["abc_class"] == "A"  # 70% <= 80%
    assert abc[-1]["abc_class"] == "C"


def test_7_descriptive_anomaly_detection():
    detector = DescriptiveAnomalyDetector()
    rows = [
        {"period": "2025-01", "revenue": 100},
        {"period": "2025-02", "revenue": 102},
        {"period": "2025-03", "revenue": 98},
        {"period": "2025-04", "revenue": 101},
        {"period": "2025-05", "revenue": 99},
        {"period": "2025-06", "revenue": 103},
        {"period": "2025-07", "revenue": 500},  # Anomaly
    ]
    anomalies = detector.detect_zscore(rows, "revenue", threshold=2.0)
    assert len(anomalies) >= 1
    assert anomalies[0]["row"]["period"] == "2025-07"
    assert anomalies[0]["observed"] == 500


def test_8_feature_registry_and_snapshot_engine():
    registry = FeatureRegistry()
    feats = registry.list_features()
    assert len(feats) >= 6
    assert registry.get("customer_total_revenue_v1") is not None

    engine = AnalyticalSnapshotEngine()
    data = [{"customer_id": 1, "revenue": 100}, {"customer_id": 2, "revenue": 200}]
    snap = engine.create_snapshot(data, dataset_version="1.0.0", features_used=["customer_total_revenue_v1"])
    assert snap.row_count == 2
    assert len(snap.checksum) == 64


def test_9_temporal_leakage_protection():
    validator = TemporalLeakageValidator()
    # Valid timestamp boundary
    assert validator.validate_temporal_boundary("2025-01-01", "2025-06-01") is True

    # Leaked future timestamp
    with pytest.raises(TemporalLeakageError):
        validator.validate_temporal_boundary("2025-07-01", "2025-06-01", record_id="REC_101")


def test_10_workflow_cost_limits_exceeded():
    workflow = get_workflow_template("revenue_decline_analysis")

    # Exceed max steps
    strict_steps_orchestrator = AnalyticalWorkflowOrchestrator(max_workflow_steps=2)
    with pytest.raises(AgentStepLimitError):
        strict_steps_orchestrator.execute_workflow(workflow)

    # Exceed max bytes
    strict_bytes_orchestrator = AnalyticalWorkflowOrchestrator(max_total_bytes=5_000_000)
    with pytest.raises(QueryCostLimitExceededError):
        strict_bytes_orchestrator.execute_workflow(workflow)


def test_11_partial_workflow_failure_handling():
    # Construct workflow with failing operation in step 2
    wf = AnalyticalWorkflow(
        workflow_id="wf_partial_fail",
        name="Failing Step Workflow",
        description="Test partial execution",
        steps=[
            WorkflowStep(
                step_id="step_1", description="Step 1", operation=StepOperation(AnalyticalOperator.TIME_SERIES, {})
            ),
            WorkflowStep(
                step_id="step_2_fail",
                description="Failing step",
                operation=StepOperation(AnalyticalOperator.PERIOD_COMPARISON, {}),
                input_step_ids=["step_1"],
            ),
        ],
    )
    orchestrator = AnalyticalWorkflowOrchestrator()
    # Mock data missing for step 2 calculation forcing failure
    res = orchestrator.execute_workflow(wf, mock_query_results={"step_1": []})
    assert res["status"] == "PARTIAL_SUCCESS"
    assert "step_1" in res["completed_steps"]
    assert res["failed_step"] is not None
    assert res["failed_step"]["failed_step_id"] == "step_2_fail"


def test_12_causal_safety_and_unsupported_data_rejection():
    # 1. Test causal safety validation
    insight = AnalyticalInsight(
        insight_id="ins_1",
        type=InsightType.CHANGE,
        title="Revenue Drop",
        observation="Revenue fell 10%.",
        causal_claim="Revenue fell because competitors reduced prices.",
        evidence={"causal_evidence_verified": False},
    )
    insight.validate_causal_safety()
    assert insight.causal_claim is None  # Unverified causal claim stripped
    assert len(insight.warnings) == 1

    # 2. Test inventory unpopulated data rejection
    inv_res = analyze_inventory_domain({})
    assert inv_res["status"] == "ANALYSIS_NOT_SUPPORTED_BY_AVAILABLE_DATA"

    # 3. Test target unavailable variance comparison
    var_res = analyze_variance_domain(100000, target_val=None)
    assert var_res["status"] == "TARGET_UNAVAILABLE"

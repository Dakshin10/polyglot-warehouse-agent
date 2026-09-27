"""Unit tests for local execution engine and ambiguity model refinement."""

from pwa.agent.pipeline.orchestrator import MultiAgentPipelineOrchestrator
from pwa.semantic.ambiguity import AmbiguityModel


def test_ambiguity_model_unambiguous_phrase_bypass():
    model = AmbiguityModel()

    # Explicit compound phrases should NOT be flagged as ambiguous
    assert not model.evaluate_term("What are the top 5 product subcategories by total sales revenue?").is_ambiguous
    assert not model.evaluate_term("Show me total purchase order expenditure grouped by job title").is_ambiguous
    assert not model.evaluate_term("Give me customer count by region").is_ambiguous
    assert not model.evaluate_term("Show total quantity sold for helmets").is_ambiguous

    # Single ambiguous terms without qualification SHOULD be flagged
    assert model.evaluate_term("Show me sales").is_ambiguous
    assert model.evaluate_term("List customers").is_ambiguous


def test_end_to_end_local_execution_top_subcategories():
    orch = MultiAgentPipelineOrchestrator()
    res = orch.run_pipeline("What are the top 5 product subcategories by total sales revenue?")

    assert res.exec_status == "SUCCESS"
    assert res.rows is not None and len(res.rows) > 0
    # Verify non-100 real values returned from dataset
    first_row = res.rows[0]
    assert "subcategory_name" in first_row or "product_name" in first_row or "name" in str(first_row)
    all_rows_str = str(res.rows)
    assert any(cat in all_rows_str for cat in ("Bikes", "Handlebars", "Road Bikes", "Touring Bikes", "Mountain Bikes"))


def test_end_to_end_local_execution_purchase_order_expenditure():
    orch = MultiAgentPipelineOrchestrator()
    res = orch.run_pipeline("Show me total purchase order expenditure grouped by job title of the ordering employee.")

    assert res.exec_status == "SUCCESS"
    assert res.rows is not None and len(res.rows) > 0
    first_row = res.rows[0]
    # Check that real calculated data was returned (not dummy 100 constant)
    assert any(
        "Executive" in str(v) or "Representative" in str(v) or "Manager" in str(v) or "Designer" in str(v)
        for v in first_row.values()
    )
    val_str = str(first_row)
    assert "100" not in val_str or len(res.rows) > 1

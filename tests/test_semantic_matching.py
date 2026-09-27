"""Tests for Task 2 — Confidence-scored semantic matching & ambiguity gating."""

import pytest
from pwa.agent.pipeline.schema_agent import GroundingAgent
from pwa.semantic.ambiguity import AmbiguityModel


def test_adversarial_paraphrases():
    """Verify semantic embedding matching catches paraphrased questions without exact keyword matches."""
    agent = GroundingAgent()

    paraphrases = [
        ("sales opportunities won", "fact_closed_deal"),
        ("warehouse availability", "fact_inventory"),
        ("vendor procurement expenditure", "fact_purchase_order"),
        ("incoming inquiries", "fact_marketing_lead"),
    ]

    for question, expected_entity in paraphrases:
        grounded = agent.ground_question(question)
        assert grounded.clarification_required is False, f"Question '{question}' unexpectedly requested clarification"
        assert expected_entity in grounded.analytical_intent.entities, (
            f"Question '{question}' grounded to {grounded.analytical_intent.entities}, expected '{expected_entity}'"
        )
        assert grounded.confidence_score > 0.3, f"Expected confidence > 0.3 for '{question}', got {grounded.confidence_score}"
        assert grounded.analytical_intent.confidence_score == grounded.confidence_score


def test_ambiguity_gating_triggers_clarification():
    """Verify genuinely ambiguous question triggers clarification request."""
    agent = GroundingAgent()
    ambiguous_q = "stock"

    grounded = agent.ground_question(ambiguous_q)
    assert grounded.clarification_required is True
    assert grounded.confidence == "LOW"
    assert "stock" in grounded.clarification_message.lower() or "ambiguous" in grounded.clarification_message.lower()


def test_ambiguity_model_evaluate_candidates():
    """Verify AmbiguityModel.evaluate_candidates triggers clarification when candidates are too close."""
    model = AmbiguityModel()

    # Close candidates (gap < 0.08)
    close_candidates = [("fact_sales_order", 0.65), ("fact_marketplace_order", 0.61)]
    res = model.evaluate_candidates(close_candidates)
    assert res.is_ambiguous is True
    assert "fact_sales_order vs fact_marketplace_order" in res.term or "could refer to either" in res.clarification_message

    # Low confidence candidate (< 0.25)
    low_candidates = [("dim_supplier", 0.15)]
    res_low = model.evaluate_candidates(low_candidates)
    assert res_low.is_ambiguous is True
    assert "Low confidence" in res_low.clarification_message or "unknown" in res_low.term

    # Clear winner (gap > 0.08, high confidence)
    clear_candidates = [("fact_closed_deal", 0.90), ("fact_marketing_lead", 0.30)]
    res_clear = model.evaluate_candidates(clear_candidates)
    assert res_clear.is_ambiguous is False

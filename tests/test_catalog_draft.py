"""Tests for automated catalog draft scaffolding generation and isolation safeguards."""

import yaml

from pwa.ingestion.connectors.base import TableSchema, SchemaColumn
from pwa.semantic.draft_generator import generate_catalog_draft, save_catalog_draft
from pwa.semantic.loader import get_semantic_catalog


def test_generate_catalog_draft_column_classification():
    """Confirm draft generation classifies numeric columns as measures and text/dates as dimensions."""
    fixture_schema = TableSchema(
        table_name="fact_sales_order",
        columns=[
            SchemaColumn(name="order_id", data_type="INTEGER", is_pk=True),
            SchemaColumn(name="customer_id", data_type="INTEGER", is_pk=False),
            SchemaColumn(name="order_status", data_type="VARCHAR(50)"),
            SchemaColumn(name="total_amount", data_type="NUMERIC(12,2)"),
            SchemaColumn(name="quantity", data_type="INT"),
            SchemaColumn(name="created_at", data_type="TIMESTAMP"),
        ],
        primary_key=["order_id"],
    )

    draft = generate_catalog_draft(fixture_schema)
    entity_data = draft["entity"]

    assert entity_data["name"] == "fact_sales_order"
    assert entity_data["physical_table"] == "fact_sales_order"
    assert entity_data["status"] == "DRAFT_NEEDS_REVIEW"
    assert "TODO: needs human review" in entity_data["description"]

    # Candidate Measures check: total_amount, quantity (order_id is PK, customer_id ends in _id -> key/relationship)
    measure_names = [m["name"] for m in entity_data["candidate_measures"]]
    assert "total_amount" in measure_names
    assert "quantity" in measure_names
    for m in entity_data["candidate_measures"]:
        assert m["aggregation"] == "SUM"
        assert m["description"] == "TODO: needs human review"

    # Candidate Dimensions check: order_status, created_at, customer_id, order_id
    dim_names = [d["name"] for d in entity_data["candidate_dimensions"]]
    assert "order_status" in dim_names
    assert "created_at" in dim_names
    for d in entity_data["candidate_dimensions"]:
        assert d["description"] == "TODO: needs human review"

    # Candidate Relationships check: customer_id -> dim_customer
    rel_sources = [r["source_column"] for r in entity_data["candidate_relationships"]]
    assert "customer_id" in rel_sources
    rel = next(r for r in entity_data["candidate_relationships"] if r["source_column"] == "customer_id")
    assert rel["target_entity"] == "dim_customer"
    assert rel["description"] == "TODO: needs human review"


def test_draft_saving_isolation_and_live_catalog_safety(tmp_path):
    """Confirm save_catalog_draft writes to target draft dir and never alters live catalog."""
    live_catalog_before = get_semantic_catalog()

    fixture_schema = TableSchema(
        table_name="fact_marketing_lead",
        columns=[
            SchemaColumn(name="lead_id", data_type="INTEGER", is_pk=True),
            SchemaColumn(name="declared_monthly_revenue", data_type="FLOAT"),
            SchemaColumn(name="lead_origin", data_type="TEXT"),
        ],
        primary_key=["lead_id"],
    )

    draft = generate_catalog_draft(fixture_schema)

    # Save to custom temporary draft folder
    draft_file = save_catalog_draft(draft, output_dir=tmp_path)

    assert draft_file.exists()
    assert draft_file.parent == tmp_path
    assert draft_file.name == "fact_marketing_lead_draft.yaml"

    with open(draft_file, "r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)

    assert loaded["entity"]["name"] == "fact_marketing_lead"
    assert loaded["entity"]["status"] == "DRAFT_NEEDS_REVIEW"

    # Verify live semantic catalog remains completely unchanged and un-overwritten
    live_catalog_after = get_semantic_catalog()
    assert len(live_catalog_before.entities) == len(live_catalog_after.entities)

    # Verify live catalog entity descriptions do not contain draft placeholders
    for entity_name, entity in live_catalog_after.entities.items():
        assert "TODO: needs human review" not in entity.description

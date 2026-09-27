"""Automated SemanticCatalog draft scaffolding generator from discovered TableSchema.

Generates draft entity catalog definitions with candidate measures, dimensions, and
relationships. All descriptions are explicitly marked 'TODO: needs human review'
to ensure structural scaffolding is never mistaken for human-verified business intent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
import yaml

from pwa.ingestion.connectors.base import TableSchema
from pwa.settings import REPO_ROOT

_NUMERIC_TYPES = {
    "int", "integer", "bigint", "smallint", "tinyint",
    "float", "double", "real", "numeric", "decimal", "number"
}

_TEXT_TYPES = {
    "varchar", "char", "text", "string", "nvarchar", "nchar",
    "date", "timestamp", "datetime", "boolean", "bool"
}


def _is_pk_or_fk_column(col_name: str, pk_cols: list[str]) -> bool:
    """Check if column name matches primary or foreign key naming patterns."""
    col_lower = col_name.lower().strip()
    if col_lower in [p.lower() for p in pk_cols]:
        return True
    if col_lower == "id" or col_lower.endswith("_id") or col_lower.endswith("_sk") or col_lower.endswith("_key"):
        return True
    return False


def generate_catalog_draft(
    table_schema: TableSchema,
    known_tables: Optional[list[TableSchema]] = None,
) -> dict[str, Any]:
    """Generate a draft SemanticCatalog dictionary from a discovered TableSchema.

    Args:
        table_schema: Discovered source table schema.
        known_tables: Optional list of other discovered schemas to infer relationships.

    Returns:
        Structured dictionary representing a candidate entity catalog draft.
    """
    table_name = table_schema.table_name.lower().strip()
    pk_cols = [p.lower() for p in table_schema.primary_key]

    # Categorize Entity Type
    if table_name.startswith("fact_") or table_name.startswith("f_") or any(
        kw in table_name for kw in ("sales", "order", "transaction", "payment", "review", "deal", "lead", "inventory", "header", "detail")
    ):
        entity_type = "fact"
    else:
        entity_type = "dimension"

    candidate_measures: list[dict[str, Any]] = []
    candidate_dimensions: list[dict[str, Any]] = []
    candidate_relationships: list[dict[str, Any]] = []

    for col in table_schema.columns:
        col_name = col.name.strip()
        dtype_clean = col.data_type.lower().split("(")[0].strip()

        # Check if primary key or foreign key candidate
        is_key = col.is_pk or _is_pk_or_fk_column(col_name, pk_cols)

        if dtype_clean in _NUMERIC_TYPES and not is_key:
            candidate_measures.append({
                "name": col_name.lower(),
                "column": col_name,
                "aggregation": "SUM",
                "description": "TODO: needs human review",
            })
        else:
            candidate_dimensions.append({
                "name": col_name.lower(),
                "column": col_name,
                "data_type": col.data_type,
                "description": "TODO: needs human review",
            })

        # Relationship inference for foreign keys matching target_id pattern
        if col_name.lower().endswith("_id") and not (col.is_pk or col_name.lower() in pk_cols):
            target_entity_name = col_name.lower()[:-3]
            candidate_relationships.append({
                "source_column": col_name,
                "target_entity": f"dim_{target_entity_name}",
                "target_column": col_name,
                "relationship_type": "MANY_TO_ONE",
                "description": "TODO: needs human review",
            })

    return {
        "entity": {
            "name": table_name,
            "physical_table": table_schema.table_name,
            "entity_type": entity_type,
            "primary_key": pk_cols or [c.name for c in table_schema.columns if c.is_pk],
            "description": f"TODO: needs human review — structural draft derived from discovered schema for `{table_schema.table_name}`",
            "candidate_measures": candidate_measures,
            "candidate_dimensions": candidate_dimensions,
            "candidate_relationships": candidate_relationships,
            "status": "DRAFT_NEEDS_REVIEW",
        }
    }


def save_catalog_draft(draft: dict[str, Any], output_dir: Optional[Path] = None) -> Path:
    """Save draft catalog entry to catalog_drafts/ directory without affecting live catalog."""
    target_dir = output_dir or (REPO_ROOT / "catalog_drafts")
    target_dir.mkdir(parents=True, exist_ok=True)

    entity_name = draft.get("entity", {}).get("name", "table_draft")
    file_path = target_dir / f"{entity_name}_draft.yaml"

    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(draft, f, default_flow_style=False, sort_keys=False)

    return file_path

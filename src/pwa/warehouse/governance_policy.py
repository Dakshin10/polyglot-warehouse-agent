"""Dataset governance policies and BigQuery partitioning & clustering configurations."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DatasetGovernancePolicy:
    """Policy definition for a BigQuery dataset layer."""

    dataset_id: str
    purpose: str
    ownership_team: str
    retention_days: int | None
    partition_field: str | None
    cluster_fields: list[str] = field(default_factory=list)


DATASET_POLICIES: dict[str, DatasetGovernancePolicy] = {
    "raw": DatasetGovernancePolicy(
        dataset_id="nexora_raw",
        purpose="Source-native ingested records with metadata provenance headers.",
        ownership_team="Data Engineering",
        retention_days=365,
        partition_field="_pwa_ingested_at",
        cluster_fields=["_pwa_source_system", "_pwa_source_table"],
    ),
    "staging": DatasetGovernancePolicy(
        dataset_id="nexora_staging",
        purpose="Standardized snake_case typed structures with deduplication.",
        ownership_team="Data Engineering",
        retention_days=180,
        partition_field="_pwa_ingested_at",
        cluster_fields=["source_system", "source_table"],
    ),
    "curated": DatasetGovernancePolicy(
        dataset_id="nexora_curated",
        purpose="Trusted enterprise domain models and contracts for downstream consumption.",
        ownership_team="Enterprise Architecture",
        retention_days=None,  # Permanent
        partition_field=None,
        cluster_fields=["entity_type"],
    ),
    "metadata": DatasetGovernancePolicy(
        dataset_id="pwa_metadata",
        purpose="Operational telemetry, runs, quality results, watermarks, and audit logs.",
        ownership_team="Platform Reliability Engineering",
        retention_days=90,
        partition_field="executed_at",
        cluster_fields=["run_id", "source_name"],
    ),
}


def get_governance_policy(layer: str) -> DatasetGovernancePolicy | None:
    """Retrieve governance policy definition for a given dataset layer."""
    return DATASET_POLICIES.get(layer.lower())

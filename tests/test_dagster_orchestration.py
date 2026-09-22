"""Unit tests for the Dagster asset graph wrapping the pwa CLI pipeline.

Assets are invoked directly (dagster's `build_asset_context()` pattern)
rather than through a real job run, so these tests exercise the same
success/failure logic without paying for the RetryPolicy backoff delay a
full job execution would incur on a mocked failure.
"""

from unittest.mock import patch

import pytest

dagster = pytest.importorskip("dagster", reason="dagster is an optional extra: pip install .[orchestration]")
from dagster import build_asset_context  # noqa: E402
from pwa.orchestration.dagster_defs import (  # noqa: E402
    defs,
    periodic_reconciliation,
    rollup_refresh,
    source_ingestion,
    source_quality_gates,
    warehouse_build,
    warehouse_quality_gates,
)


def test_definitions_load_without_error():
    """The whole Definitions object (assets, job, schedule, sensor) must be
    constructible — this is what `dagster dev -m pwa.orchestration.dagster_defs`
    depends on."""
    assert defs is not None


def test_source_ingestion_success():
    with patch("pwa.run_source.run_source_pipeline", return_value=True):
        assert source_ingestion(build_asset_context()) is True


def test_source_ingestion_raises_on_failure():
    with patch("pwa.run_source.run_source_pipeline", return_value=False):
        with pytest.raises(RuntimeError, match="Source ingestion"):
            source_ingestion(build_asset_context())


def test_source_quality_gates_raises_on_failure():
    with patch("pwa.gates_source.run_all_gates", return_value=False):
        with pytest.raises(RuntimeError, match="quality gates"):
            source_quality_gates(build_asset_context())


def test_warehouse_build_raises_on_failure():
    with patch("pwa.run_bigquery.run_warehouse_pipeline", return_value=False):
        with pytest.raises(RuntimeError, match="Warehouse build"):
            warehouse_build(build_asset_context())


def test_warehouse_quality_gates_raises_on_failure():
    with patch("pwa.gates_bigquery.run_all_bq_gates", return_value=False):
        with pytest.raises(RuntimeError, match="quality gates"):
            warehouse_quality_gates(build_asset_context())


def test_rollup_refresh_raises_on_failure():
    with patch("pwa.rollups.refresh_rollups", return_value=False):
        with pytest.raises(RuntimeError, match="Rollup"):
            rollup_refresh(build_asset_context())


def test_periodic_reconciliation_raises_on_failure():
    with patch("pwa.quality.reconciliation.run_full_reconciliation", return_value=False):
        with pytest.raises(RuntimeError, match="reconciliation"):
            periodic_reconciliation(build_asset_context())


def test_full_asset_graph_materializes_in_dependency_order():
    """End-to-end (through the real Dagster executor, not direct invocation)
    with every underlying pipeline function mocked to succeed — proves the
    dependency graph (source -> gates -> warehouse -> gates -> rollup -> reconciliation) is
    wired correctly, not just that each asset works in isolation."""
    from dagster import materialize

    with (
        patch("pwa.run_source.run_source_pipeline", return_value=True),
        patch("pwa.gates_source.run_all_gates", return_value=True),
        patch("pwa.run_bigquery.run_warehouse_pipeline", return_value=True),
        patch("pwa.gates_bigquery.run_all_bq_gates", return_value=True),
        patch("pwa.rollups.refresh_rollups", return_value=True),
        patch("pwa.quality.reconciliation.run_full_reconciliation", return_value=True),
    ):
        result = materialize(
            [
                source_ingestion,
                source_quality_gates,
                warehouse_build,
                warehouse_quality_gates,
                rollup_refresh,
                periodic_reconciliation,
            ]
        )

    assert result.success
    materialized = [e.asset_key.to_user_string() for e in result.get_asset_materialization_events()]
    assert materialized == [
        "source_ingestion",
        "source_quality_gates",
        "warehouse_build",
        "warehouse_quality_gates",
        "rollup_refresh",
        "periodic_reconciliation",
    ]


def test_rollup_refresh_asset_dependency():
    """Assert rollup_refresh explicitly depends on warehouse_quality_gates in asset graph."""
    dep_keys = [k.to_user_string() for k in rollup_refresh.keys_by_input.values()]
    assert "warehouse_quality_gates" in dep_keys



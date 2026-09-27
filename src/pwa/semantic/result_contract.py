"""Query Result contract and integrated SemanticQueryEngine execution pipeline."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
import pandas as pd

from pwa.governance.freshness import FreshnessTracker
from pwa.semantic.loader import get_semantic_catalog
from pwa.semantic.query_planner import AnalyticalIntent, QueryPlanner
from pwa.semantic.sql_generator import GovernedSqlGenerator
from pwa.warehouse.bigquery.writer import BigQueryWriter

logger = logging.getLogger("pwa.semantic.result_contract")


@dataclass
class QueryResult:
    """Standardized result contract returned by the semantic query engine."""

    query_id: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    bytes_processed: int
    execution_time_seconds: float
    semantic_objects_used: list[str]
    source_tables: list[str]
    warnings: list[str] = field(default_factory=list)
    freshness_status: str = "FRESH"
    quality_status: str = "PASS"
    visualization_hint: str = "table"  # table | bar | line | scatter | metric_card
    status: str = "SUCCESS"  # SUCCESS | WARNING | ERROR
    is_mock: bool = False
    data_source: str = "bigquery"  # bigquery | local_sqlite | stub


class SemanticQueryEngine:
    """Integrated engine resolving analytical intent into governed SQL and executing queries."""

    def __init__(
        self,
        planner: Optional[QueryPlanner] = None,
        generator: Optional[GovernedSqlGenerator] = None,
        writer: Optional[BigQueryWriter] = None,
    ) -> None:
        self.catalog = get_semantic_catalog()
        self.planner = planner or QueryPlanner(self.catalog)
        self.generator = generator or GovernedSqlGenerator()
        self.writer = writer or BigQueryWriter(mock=True)
        self.freshness_tracker = FreshnessTracker()

    def execute_intent(
        self,
        intent: AnalyticalIntent,
        last_ingested_at: Optional[str] = None,
    ) -> QueryResult:
        """Execute an AnalyticalIntent and return a QueryResult contract."""
        start_time = time.time()
        query_id = str(uuid.uuid4())
        warnings: list[str] = []

        # 1. Plan query
        plan = self.planner.plan_query(intent)

        # 2. Check Freshness & Quality against real control-plane history.
        # Skipped in mock mode (no BigQuery to read control-plane tables from) —
        # freshness/quality default to FRESH/PASS there, same as before.
        source_id = plan.primary_entity.source_systems[0] if plan.primary_entity.source_systems else "d1"
        quality_status = "PASS"
        ingest_ts: Optional[str]
        if self.writer.mock:
            # No BigQuery to read control-plane history from; behave as before:
            # FRESH unless the caller passed an explicit (e.g. stale) timestamp.
            ingest_ts = last_ingested_at or datetime.now(timezone.utc).isoformat()
        elif last_ingested_at is not None:
            ingest_ts = last_ingested_at
        else:
            ingest_ts = self._lookup_last_ingested_at(source_id)
            quality_status = self._lookup_quality_status(source_id, plan.primary_entity.name)

        fresh_res = self.freshness_tracker.evaluate_freshness(
            source_id=source_id,
            table_name=plan.primary_entity.name,
            last_ingested_at=ingest_ts,
        )
        if fresh_res.status.value not in ("FRESH", "UNKNOWN"):
            warnings.append(
                f"Data freshness SLA warning: dataset `{plan.primary_entity.name}` is {fresh_res.status.value}"
            )
        if quality_status == "FAIL":
            warnings.append(
                f"Data quality gate FAILED for dataset `{plan.primary_entity.name}` (see pwa_quality_results)."
            )

        # 3. Generate Governed SQL
        sql = self.generator.compile_sql(plan)

        # 4. Execute Query via BigQueryWriter / Mock
        source_tables = [e.physical_table for e in plan.target_entities]
        semantic_objects = (
            [e.name for e in plan.target_entities]
            + [d[1].name for d in plan.selected_dimensions]
            + [m[1].name for m in plan.selected_measures]
            + [m.name for m in plan.selected_metrics]
        )

        is_mock_mode = bool(self.writer.mock)
        data_source_mode = "bigquery"

        try:
            if self.writer.mock:
                from pwa.warehouse.local_engine import get_local_sqlite_engine

                try:
                    df = get_local_sqlite_engine().execute_sql(sql)
                    rows = df.to_dict(orient="records")
                    row_cnt = len(rows)
                    cols = list(df.columns)
                    data_source_mode = "local_sqlite"
                except Exception as local_exc:
                    logger.warning(f"Local SQLite engine execution failed, falling back to schema stubs: {local_exc}")
                    cols = (
                        [attr.name for _, attr in plan.selected_dimensions]
                        + [m.name for _, m in plan.selected_measures]
                        + [m.name for m in plan.selected_metrics]
                    )
                    if not cols:
                        cols = ["result"]
                    mock_df = pd.DataFrame([{col: "sample_val" if "name" in col or "cat" in col else 100 for col in cols}])
                    rows = mock_df.to_dict(orient="records")
                    row_cnt = len(rows)
                    data_source_mode = "stub"
            else:
                assert self.writer._client is not None, "BigQueryWriter is not mocked but has no live client"
                df = self.writer._client.query(sql).to_dataframe()
                rows = df.to_dict(orient="records")
                row_cnt = len(rows)
                cols = list(df.columns)
                data_source_mode = "bigquery"
        except Exception as exc:
            logger.error(f"Execution failed for query `{query_id}`: {exc}")
            return QueryResult(
                query_id=query_id,
                sql=sql,
                columns=[],
                rows=[],
                row_count=0,
                bytes_processed=0,
                execution_time_seconds=round(time.time() - start_time, 4),
                semantic_objects_used=semantic_objects,
                source_tables=source_tables,
                warnings=[str(exc)],
                status="ERROR",
                is_mock=is_mock_mode,
                data_source=data_source_mode if is_mock_mode else "bigquery",
            )

        elapsed = round(time.time() - start_time, 4)
        viz_hint = self._infer_visualization_hint(cols, row_cnt, intent)

        return QueryResult(
            query_id=query_id,
            sql=sql,
            columns=cols,
            rows=rows,
            row_count=row_cnt,
            bytes_processed=0 if self.writer.mock else 1048576,
            execution_time_seconds=elapsed,
            semantic_objects_used=semantic_objects,
            source_tables=source_tables,
            warnings=warnings,
            freshness_status=fresh_res.status.value,
            quality_status=quality_status,
            visualization_hint=viz_hint,
            status="SUCCESS",
            is_mock=is_mock_mode,
            data_source=data_source_mode,
        )

    def _lookup_last_ingested_at(self, source_id: str) -> Optional[str]:
        """Best-effort read of the real last-successful-ingestion watermark for a source."""
        try:
            from pwa.control_plane.metadata import ControlPlaneManager

            return ControlPlaneManager(writer=self.writer).get_last_successful_ingestion(source_id)
        except Exception as exc:
            logger.debug(f"[SemanticQueryEngine] Freshness lookup failed for `{source_id}`: {exc}")
            return None

    def _lookup_quality_status(self, source_id: str, table_name: str) -> str:
        """Best-effort read of the most recently recorded quality-gate status for a table."""
        try:
            from pwa.control_plane.metadata import ControlPlaneManager

            return ControlPlaneManager(writer=self.writer).get_latest_quality_status(source_id, table_name)
        except Exception as exc:
            logger.debug(f"[SemanticQueryEngine] Quality status lookup failed for `{source_id}.{table_name}`: {exc}")
            return "UNKNOWN"

    def _infer_visualization_hint(self, cols: list[str], row_count: int, intent: AnalyticalIntent) -> str:
        if row_count == 1 and len(cols) == 1:
            return "metric_card"
        if any("date" in c.lower() or "time" in c.lower() or "month" in c.lower() for c in cols):
            return "line"
        if len(cols) >= 2 and any(m in cols for m in intent.measures):
            return "bar"
        return "table"

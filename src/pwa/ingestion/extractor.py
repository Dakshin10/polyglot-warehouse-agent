"""Table extraction engine for memory-safe bounded batching."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Generator, Optional
import pandas as pd

from pwa.ingestion.connectors.base import SourceConnector
from pwa.ingestion.payload import add_provenance_metadata

logger = logging.getLogger("pwa.ingestion.extractor")


def compute_effective_watermark(
    previous_watermark: Optional[Any],
    lookback_minutes: int = 5,
) -> Optional[Any]:
    """Calculate effective extraction boundary incorporating a lookback window for late-arriving records."""
    if previous_watermark is None or previous_watermark == "":
        return None
    try:
        dt = pd.to_datetime(previous_watermark)
        effective_dt = dt - pd.Timedelta(minutes=lookback_minutes)
        return effective_dt.isoformat()
    except Exception:
        return previous_watermark


class TableExtractor:
    """Extraction engine executing bounded batch iteration from source connectors."""

    def __init__(self, connector: SourceConnector) -> None:
        self.connector = connector

    def extract_table(
        self,
        table_name: str,
        run_id: Optional[str] = None,
        batch_size: int = 5000,
        watermark_col: Optional[str] = None,
        watermark_val: Optional[Any] = None,
        lookback_minutes: int = 5,
    ) -> Generator[dict[str, Any], None, None]:
        """Extract a source table in bounded batches, injecting provenance metadata."""
        if run_id is None:
            run_id = str(uuid.uuid4())

        effective_watermark = compute_effective_watermark(watermark_val, lookback_minutes) if watermark_val else None

        logger.info(
            f"[{self.connector.source_name}] Extracting `{table_name}` "
            f"(run_id={run_id}, batch_size={batch_size}, watermark_col={watermark_col}, effective_watermark={effective_watermark})"
        )

        total_extracted = 0
        batch_count = 0

        for batch in self.connector.extract(
            table_name=table_name,
            batch_size=batch_size,
            watermark_col=watermark_col,
            watermark_val=effective_watermark,
        ):
            df = batch.df
            if df.empty:
                continue

            # Inject provenance metadata
            df = add_provenance_metadata(
                df=df,
                run_id=run_id,
                source_system=self.connector.source_name,
                source_table=table_name,
                batch_id=batch.batch_index,
            )

            total_extracted += len(df)
            batch_count += 1

            yield {
                "run_id": run_id,
                "source_system": self.connector.source_name,
                "table_name": table_name,
                "batch_index": batch.batch_index,
                "record_count": len(df),
                "df": df,
                "has_more": batch.has_more,
            }

        logger.info(
            f"[{self.connector.source_name}] Extracted `{table_name}` complete: {total_extracted:,} rows across {batch_count} batch(es)."
        )

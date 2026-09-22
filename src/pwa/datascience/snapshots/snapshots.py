"""
Reproducible Dataset Snapshot Engine (Phase 2C)
"""

import datetime
import hashlib
import json
import uuid
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class DatasetSnapshot:
    snapshot_id: str
    snapshot_date: str
    dataset_version: str
    semantic_version: str
    feature_version: str
    row_count: int
    checksum: str
    features_used: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AnalyticalSnapshotEngine:
    def create_snapshot(
        self,
        rows: List[Dict[str, Any]],
        dataset_version: str = "1.0.0",
        semantic_version: str = "2.0.0",
        feature_version: str = "v1",
        features_used: Optional[List[str]] = None,
    ) -> DatasetSnapshot:
        snapshot_id = f"snap_{uuid.uuid4().hex[:8]}"
        today_str = datetime.date.today().isoformat()
        serialized = json.dumps(rows, sort_keys=True, default=str)
        checksum = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

        return DatasetSnapshot(
            snapshot_id=snapshot_id,
            snapshot_date=today_str,
            dataset_version=dataset_version,
            semantic_version=semantic_version,
            feature_version=feature_version,
            row_count=len(rows),
            checksum=checksum,
            features_used=features_used or [],
            metadata={"created_at": datetime.datetime.now().isoformat()},
        )

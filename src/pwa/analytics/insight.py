"""
Analytical Insight Contract and Confidence Classification (Phase 2C)
"""

from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


class InsightType(str, Enum):
    TREND = "TREND"
    CHANGE = "CHANGE"
    CONTRIBUTION = "CONTRIBUTION"
    ANOMALY = "ANOMALY"
    COHORT = "COHORT"
    SEGMENT = "SEGMENT"
    FUNNEL = "FUNNEL"
    RETENTION = "RETENTION"
    VARIANCE = "VARIANCE"


class InsightConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class AnalyticalInsight:
    insight_id: str
    type: InsightType
    title: str
    observation: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    interpretation: Optional[str] = None
    causal_claim: Optional[str] = None
    confidence: InsightConfidence = InsightConfidence.MEDIUM
    supporting_query_ids: List[str] = field(default_factory=list)
    supporting_metrics: List[str] = field(default_factory=list)
    supporting_dimensions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def validate_causal_safety(self) -> None:
        """
        Validates that causal claims are not asserted without explicit evidence.
        If a causal claim is made without evidence indicating statistical significance or
        explicit causal analysis, a warning is attached or causal_claim is marked unverified.
        """
        if self.causal_claim:
            has_causal_evidence = self.evidence.get("causal_evidence_verified", False)
            if not has_causal_evidence:
                self.warnings.append(
                    "Causal assertion removed: Observational evidence demonstrates correlation/contribution, not direct causality."
                )
                self.causal_claim = None

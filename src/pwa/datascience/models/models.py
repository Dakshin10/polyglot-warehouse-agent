"""
Data Science Model Readiness Interfaces (Phase 2C Preparation)
Defines model metadata contracts. Model training is NOT implemented in Phase 2C.
"""

from typing import Dict, Any, List
from dataclasses import dataclass, field


@dataclass
class TrainingDataset:
    dataset_id: str
    entity_id: str
    feature_timestamp: str
    feature_values: Dict[str, Any]
    label: str
    label_timestamp: str


@dataclass
class ModelVersion:
    model_version_id: str
    model_name: str
    version_tag: str
    trained_at: str
    evaluation_metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class ModelDefinition:
    model_name: str
    target_label: str
    algorithm_family: str
    features: List[str] = field(default_factory=list)
    versions: List[ModelVersion] = field(default_factory=list)


@dataclass
class EvaluationResult:
    eval_id: str
    metrics: Dict[str, float]
    evaluated_at: str

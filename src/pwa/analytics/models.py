"""
Analytical Workflow Dataclasses and Operator Definitions (Phase 2C)
"""

from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


class AnalyticalOperator(str, Enum):
    AGGREGATE = "AGGREGATE"
    GROUP_BY = "GROUP_BY"
    FILTER = "FILTER"
    SORT = "SORT"
    TOP_N = "TOP_N"
    BOTTOM_N = "BOTTOM_N"
    TIME_SERIES = "TIME_SERIES"
    PERIOD_COMPARISON = "PERIOD_COMPARISON"
    GROWTH_RATE = "GROWTH_RATE"
    PERCENT_CHANGE = "PERCENT_CHANGE"
    RANK = "RANK"
    CONTRIBUTION = "CONTRIBUTION"
    ROLLING_METRIC = "ROLLING_METRIC"
    COHORT = "COHORT"
    SEGMENT = "SEGMENT"
    FUNNEL = "FUNNEL"
    RETENTION = "RETENTION"
    VARIANCE = "VARIANCE"


@dataclass
class StepOperation:
    operator: AnalyticalOperator
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowStep:
    step_id: str
    description: str
    operation: StepOperation
    input_step_ids: List[str] = field(default_factory=list)
    semantic_objects: Dict[str, Any] = field(default_factory=dict)
    sql_strategy: Optional[str] = None
    output_key: str = "result"


@dataclass
class AnalyticalWorkflow:
    workflow_id: str
    name: str
    description: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    steps: List[WorkflowStep] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    limits: Dict[str, Any] = field(default_factory=dict)

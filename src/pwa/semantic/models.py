"""Dataclass models for Phase 2A Enterprise Semantic Layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SemanticEntity:
    """Canonical enterprise entity model."""

    name: str
    entity_name: str
    description: str
    dataset: str
    physical_table: str
    grain: str
    primary_key: list[str]
    source_systems: list[str] = field(default_factory=list)
    timestamp_column: Optional[str] = None


@dataclass
class DimensionAttribute:
    """Attribute within an analytical dimension."""

    name: str
    type: str
    column: str


@dataclass
class Dimension:
    """Analytical dimension model."""

    name: str
    display_name: str
    description: str
    entity: str
    key_column: str
    attributes: list[DimensionAttribute] = field(default_factory=list)


@dataclass
class Measure:
    """Governed raw measure model."""

    name: str
    display_name: str
    description: str
    entity: str
    column: str
    aggregation: str  # SUM | COUNT | AVG | MIN | MAX
    data_type: str
    currency: Optional[str] = None
    unit: Optional[str] = None


@dataclass
class Metric:
    """Governed derived business metric model."""

    name: str
    display_name: str
    description: str
    formula: str
    measures_used: list[str] = field(default_factory=list)
    data_type: str = "NUMERIC"
    format: str = "NUMBER"


@dataclass
class Relationship:
    """Governed join graph relationship model."""

    name: str
    source_entity: str
    target_entity: str
    join_type: str  # INNER | LEFT | RIGHT | FULL
    cardinality: str  # ONE_TO_MANY | MANY_TO_ONE | ONE_TO_ONE
    source_key: str
    target_key: str
    description: str = ""


@dataclass
class TimeDimension:
    """Standardized time dimension model."""

    name: str
    display_name: str
    description: str
    type: str  # TIMESTAMP | DATE
    default_granularity: str
    supported_granularities: list[str]
    entity: str
    column: str


@dataclass
class GlossaryTerm:
    """Governed business glossary term."""

    name: str
    definition: str
    synonyms: list[str] = field(default_factory=list)
    related_entities: list[str] = field(default_factory=list)
    related_measures: list[str] = field(default_factory=list)
    related_dimensions: list[str] = field(default_factory=list)


@dataclass
class SemanticCatalog:
    """In-memory representation of the complete enterprise semantic catalog."""

    entities: dict[str, SemanticEntity] = field(default_factory=dict)
    dimensions: dict[str, Dimension] = field(default_factory=dict)
    measures: dict[str, Measure] = field(default_factory=dict)
    metrics: dict[str, Metric] = field(default_factory=dict)
    relationships: dict[str, Relationship] = field(default_factory=dict)
    time_dimensions: dict[str, TimeDimension] = field(default_factory=dict)
    glossary: dict[str, GlossaryTerm] = field(default_factory=dict)

    def get_entity(self, name: str) -> Optional[SemanticEntity]:
        return self.entities.get(name.lower())

    def get_dimension(self, name: str) -> Optional[Dimension]:
        return self.dimensions.get(name.lower())

    def get_measure(self, name: str) -> Optional[Measure]:
        return self.measures.get(name.lower())

    def get_metric(self, name: str) -> Optional[Metric]:
        return self.metrics.get(name.lower())

    def get_relationship(self, name: str) -> Optional[Relationship]:
        return self.relationships.get(name.lower())

    def get_time_dimension(self, name: str) -> Optional[TimeDimension]:
        return self.time_dimensions.get(name.lower())

    def get_glossary_term(self, name: str) -> Optional[GlossaryTerm]:
        return self.glossary.get(name.lower())

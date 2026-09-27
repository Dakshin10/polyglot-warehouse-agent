"""Analytical Query Planner and Intent abstraction for Phase 2A Enterprise Semantic Layer."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from pwa.semantic.loader import get_semantic_catalog
from pwa.semantic.models import (
    DimensionAttribute,
    Measure,
    Metric,
    Relationship,
    SemanticCatalog,
    SemanticEntity,
)

logger = logging.getLogger("pwa.semantic.query_planner")


@dataclass
class AnalyticalIntent:
    """Structured representation of analytical question intent."""

    entities: list[str] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    measures: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    filters: list[dict[str, Any]] = field(default_factory=list)
    time_dimension: Optional[str] = None
    granularity: Optional[str] = None
    time_range: Optional[dict[str, Any]] = None
    group_by: list[str] = field(default_factory=list)
    order_by: list[str] = field(default_factory=list)
    limit: int = 100
    confidence_score: float = 1.0


@dataclass
class QueryPlan:
    """Resolved physical query plan ready for SQL compilation."""

    primary_entity: SemanticEntity
    target_entities: list[SemanticEntity]
    joined_relationships: list[Relationship]
    selected_dimensions: list[tuple[str, DimensionAttribute]]  # (table_alias, attr)
    selected_measures: list[tuple[str, Measure]]  # (table_alias, measure)
    selected_metrics: list[Metric]
    group_by_expressions: list[str]
    filter_expressions: list[str]
    limit: int
    fanout_risk: bool = False
    fanout_details: list[dict[str, Any]] = field(default_factory=list)


class QueryPlanner:
    """Planner resolving AnalyticalIntent against SemanticCatalog into a physical QueryPlan."""

    def __init__(self, catalog: Optional[SemanticCatalog] = None) -> None:
        self.catalog = catalog or get_semantic_catalog()

    def _determine_primary_entity(self, intent: AnalyticalIntent) -> SemanticEntity:
        primary_entity_name = "fact_sales_order"
        if intent.entities:
            primary_entity_name = intent.entities[0].lower()
        elif intent.measures:
            m = self.catalog.get_measure(intent.measures[0])
            if m and m.entity:
                primary_entity_name = m.entity.lower()
        elif intent.metrics:
            m_or_metric = self.catalog.get_metric(intent.metrics[0]) or self.catalog.get_measure(intent.metrics[0])
            if m_or_metric and hasattr(m_or_metric, "entity") and m_or_metric.entity:
                primary_entity_name = m_or_metric.entity.lower()
        elif intent.dimensions:
            d = self.catalog.get_dimension(intent.dimensions[0])
            if d and d.entity:
                primary_entity_name = d.entity.lower()

        primary_entity = self.catalog.get_entity(primary_entity_name)
        if not primary_entity:
            raise ValueError(f"Unknown primary entity: '{primary_entity_name}'")
        return primary_entity

    def _add_entity_joins(
        self,
        target_entity_name: str,
        primary_entity_name: str,
        joined_relationships: list[Relationship],
        target_entities: list[SemanticEntity],
    ) -> None:
        if target_entity_name != primary_entity_name:
            rels = self._find_relationship_path(primary_entity_name, target_entity_name)
            for rel in rels:
                if rel not in joined_relationships:
                    joined_relationships.append(rel)
                for e_name in (rel.source_entity, rel.target_entity):
                    ent = self.catalog.get_entity(e_name)
                    if ent and ent not in target_entities:
                        target_entities.append(ent)

    def plan_query(self, intent: AnalyticalIntent, strict_grain_validation: bool = False) -> QueryPlan:
        """Resolve analytical intent into a structured query plan using governed relationships."""
        primary_entity = self._determine_primary_entity(intent)

        target_entities = [primary_entity]
        joined_relationships: list[Relationship] = []
        selected_dimensions: list[tuple[str, DimensionAttribute]] = []
        selected_measures: list[tuple[str, Measure]] = []
        selected_metrics: list[Metric] = []
        group_by_expressions: list[str] = []
        filter_expressions: list[str] = []

        # 2. Resolve Dimensions
        for dim_name in intent.dimensions:
            dim = self.catalog.get_dimension(dim_name)
            if not dim:
                if self.catalog.get_time_dimension(dim_name):
                    continue
                raise ValueError(f"Unknown dimension: '{dim_name}'")

            dim_entity = self.catalog.get_entity(dim.entity)
            if dim_entity:
                self._add_entity_joins(dim_entity.name, primary_entity.name, joined_relationships, target_entities)

            alias = dim_entity.name if dim_entity else primary_entity.name
            for attr in dim.attributes:
                selected_dimensions.append((alias, attr))
                group_by_expressions.append(f"{alias}.{attr.column}")

        # 3. Resolve Measures
        for m_name in intent.measures:
            m = self.catalog.get_measure(m_name)
            if not m:
                raise ValueError(f"Unknown measure: '{m_name}'")
            m_entity = self.catalog.get_entity(m.entity) or primary_entity
            selected_measures.append((m_entity.name, m))
            self._add_entity_joins(m_entity.name, primary_entity.name, joined_relationships, target_entities)

        # 4. Resolve Metrics (or fallback to measure if passed in metrics list)
        for metric_name in intent.metrics:
            metric = self.catalog.get_metric(metric_name)
            if metric:
                selected_metrics.append(metric)
            else:
                m = self.catalog.get_measure(metric_name)
                if m:
                    m_entity = self.catalog.get_entity(m.entity) or primary_entity
                    selected_measures.append((m_entity.name, m))
                    self._add_entity_joins(m_entity.name, primary_entity.name, joined_relationships, target_entities)
                else:
                    raise ValueError(f"Unknown metric: '{metric_name}'")

        # 5. Resolve Filters
        for f in intent.filters:
            col = f.get("column")
            op = f.get("op", "=")
            val = f.get("val")
            if col and val is not None:
                filter_expressions.append(f"{primary_entity.name}.{col} {op} '{val}'")

        # 6. Detect Grain Mismatch / Fan-Out Risk
        fanout_risk, fanout_details = self._detect_fanout_risk(
            joined_relationships, selected_measures, target_entities
        )

        if strict_grain_validation and fanout_risk:
            from pwa.agent.errors import SemanticGrainValidationError

            measure_entity_names = {alias for alias, _ in selected_measures}
            msg = (
                f"Grain validation error: Query combines measures across entities with different grains "
                f"({', '.join(measure_entity_names)}). Direct joining would cause row multiplication / fan-out."
            )
            raise SemanticGrainValidationError(msg, fanout_details=fanout_details)

        return QueryPlan(
            primary_entity=primary_entity,
            target_entities=target_entities,
            joined_relationships=joined_relationships,
            selected_dimensions=selected_dimensions,
            selected_measures=selected_measures,
            selected_metrics=selected_metrics,
            group_by_expressions=group_by_expressions,
            filter_expressions=filter_expressions,
            limit=intent.limit,
            fanout_risk=fanout_risk,
            fanout_details=fanout_details,
        )

    @staticmethod
    def _detect_fanout_risk(
        joined_relationships: list[Relationship],
        selected_measures: list[tuple[str, Measure]],
        target_entities: list[SemanticEntity],
    ) -> tuple[bool, list[dict[str, Any]]]:
        fanout_risk = False
        fanout_details: list[dict[str, Any]] = []

        measure_entity_names = {alias for alias, _ in selected_measures}
        target_entity_names = {e.name for e in target_entities}

        for rel in joined_relationships:
            card = (rel.cardinality or "").upper()
            if card in ("ONE_TO_MANY", "MANY_TO_MANY"):
                if rel.source_entity in measure_entity_names and rel.target_entity in target_entity_names:
                    fanout_risk = True
                    fanout_details.append({
                        "relationship": rel.name,
                        "source_entity": rel.source_entity,
                        "target_entity": rel.target_entity,
                        "cardinality": card,
                        "reason": f"Measure from '{rel.source_entity}' will multiply when joined across '{card}' relationship to '{rel.target_entity}'."
                    })
                elif len(measure_entity_names) > 1 and (rel.source_entity in measure_entity_names or rel.target_entity in measure_entity_names):
                    fanout_risk = True
                    fanout_details.append({
                        "relationship": rel.name,
                        "source_entity": rel.source_entity,
                        "target_entity": rel.target_entity,
                        "cardinality": card,
                        "reason": f"Multi-fact measure calculation across '{card}' relationship '{rel.name}'."
                    })
        return fanout_risk, fanout_details

    def _find_relationship_path(self, source_name: str, target_name: str) -> list[Relationship]:
        """BFS search returning shortest sequence of Relationships linking source_name to target_name."""
        if source_name == target_name:
            return []

        visited = {source_name}
        queue = [(source_name, [])]
        while queue:
            curr, path = queue.pop(0)
            if curr == target_name:
                return path
            for rel in self.catalog.relationships.values():
                next_node = None
                if rel.source_entity == curr:
                    next_node = rel.target_entity
                elif rel.target_entity == curr:
                    next_node = rel.source_entity

                if next_node and next_node not in visited:
                    visited.add(next_node)
                    queue.append((next_node, path + [rel]))
        return []


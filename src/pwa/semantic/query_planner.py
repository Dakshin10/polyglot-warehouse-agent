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


class QueryPlanner:
    """Planner resolving AnalyticalIntent against SemanticCatalog into a physical QueryPlan."""

    def __init__(self, catalog: Optional[SemanticCatalog] = None) -> None:
        self.catalog = catalog or get_semantic_catalog()

    def plan_query(self, intent: AnalyticalIntent) -> QueryPlan:
        """Resolve analytical intent into a structured query plan using governed relationships."""
        # 1. Determine primary entity
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

            # Check if dimension entity requires a join
            dim_entity = self.catalog.get_entity(dim.entity)
            if dim_entity and dim_entity.name != primary_entity.name:
                rels = self._find_relationship_path(primary_entity.name, dim_entity.name)
                for rel in rels:
                    if rel not in joined_relationships:
                        joined_relationships.append(rel)
                    for e_name in (rel.source_entity, rel.target_entity):
                        ent = self.catalog.get_entity(e_name)
                        if ent and ent not in target_entities:
                            target_entities.append(ent)

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
            if m_entity.name != primary_entity.name:
                rels = self._find_relationship_path(primary_entity.name, m_entity.name)
                for rel in rels:
                    if rel not in joined_relationships:
                        joined_relationships.append(rel)
                    for e_name in (rel.source_entity, rel.target_entity):
                        ent = self.catalog.get_entity(e_name)
                        if ent and ent not in target_entities:
                            target_entities.append(ent)

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
                    if m_entity.name != primary_entity.name:
                        rels = self._find_relationship_path(primary_entity.name, m_entity.name)
                        for rel in rels:
                            if rel not in joined_relationships:
                                joined_relationships.append(rel)
                            for e_name in (rel.source_entity, rel.target_entity):
                                ent = self.catalog.get_entity(e_name)
                                if ent and ent not in target_entities:
                                    target_entities.append(ent)
                else:
                    raise ValueError(f"Unknown metric: '{metric_name}'")

        # 5. Resolve Filters
        for f in intent.filters:
            col = f.get("column")
            op = f.get("op", "=")
            val = f.get("val")
            if col and val is not None:
                filter_expressions.append(f"{primary_entity.name}.{col} {op} '{val}'")

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
        )

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


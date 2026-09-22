"""Loader for configuration-driven YAML semantic catalog files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional
import yaml

from pwa.settings import REPO_ROOT
from pwa.semantic.models import (
    Dimension,
    DimensionAttribute,
    GlossaryTerm,
    Measure,
    Metric,
    Relationship,
    SemanticCatalog,
    SemanticEntity,
    TimeDimension,
)

logger = logging.getLogger("pwa.semantic.loader")

DEFAULT_SEMANTIC_DIR = REPO_ROOT / "config" / "semantic"


class SemanticCatalogLoader:
    """Loader reading YAML semantic definitions into an in-memory SemanticCatalog."""

    def __init__(self, semantic_dir: Optional[Path] = None) -> None:
        self.semantic_dir = Path(semantic_dir) if semantic_dir else DEFAULT_SEMANTIC_DIR

    def _read_yaml(self, filename: str) -> dict[str, Any]:
        filepath = self.semantic_dir / filename
        if not filepath.exists():
            logger.warning(f"Semantic configuration file not found: {filepath}")
            return {}
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as exc:
            logger.error(f"Failed to parse YAML file `{filepath}`: {exc}")
            return {}

    def load_catalog(self) -> SemanticCatalog:
        """Load all semantic catalog YAML files and return a unified SemanticCatalog instance."""
        catalog = SemanticCatalog()

        # 1. Entities
        raw_entities = self._read_yaml("entities.yaml").get("entities", {})
        for name, data in raw_entities.items():
            catalog.entities[name.lower()] = SemanticEntity(
                name=name.lower(),
                entity_name=data.get("entity_name", name),
                description=data.get("description", ""),
                dataset=data.get("dataset", "curated_enterprise"),
                physical_table=data.get("physical_table", f"curated_enterprise.{name}"),
                grain=data.get("grain", "one row per record"),
                primary_key=data.get("primary_key", []),
                source_systems=data.get("source_systems", []),
                timestamp_column=data.get("timestamp_column"),
            )

        # 2. Dimensions
        raw_dims = self._read_yaml("dimensions.yaml").get("dimensions", {})
        for name, data in raw_dims.items():
            attrs = [
                DimensionAttribute(
                    name=a.get("name", ""),
                    type=a.get("type", "STRING"),
                    column=a.get("column", a.get("name", "")),
                )
                for a in data.get("attributes", [])
            ]
            catalog.dimensions[name.lower()] = Dimension(
                name=name.lower(),
                display_name=data.get("display_name", name),
                description=data.get("description", ""),
                entity=data.get("entity", "").lower(),
                key_column=data.get("key_column", ""),
                attributes=attrs,
            )

        # 3. Measures
        raw_measures = self._read_yaml("measures.yaml").get("measures", {})
        for name, data in raw_measures.items():
            catalog.measures[name.lower()] = Measure(
                name=name.lower(),
                display_name=data.get("display_name", name),
                description=data.get("description", ""),
                entity=data.get("entity", "").lower(),
                column=data.get("column", ""),
                aggregation=data.get("aggregation", "SUM").upper(),
                data_type=data.get("data_type", "NUMERIC"),
                currency=data.get("currency"),
                unit=data.get("unit"),
            )

        # 4. Metrics
        raw_metrics = self._read_yaml("metrics.yaml").get("metrics", {})
        for name, data in raw_metrics.items():
            catalog.metrics[name.lower()] = Metric(
                name=name.lower(),
                display_name=data.get("display_name", name),
                description=data.get("description", ""),
                formula=data.get("formula", ""),
                measures_used=data.get("measures_used", []),
                data_type=data.get("data_type", "NUMERIC"),
                format=data.get("format", "NUMBER"),
            )

        # 5. Relationships
        raw_rels = self._read_yaml("relationships.yaml").get("relationships", {})
        for name, data in raw_rels.items():
            catalog.relationships[name.lower()] = Relationship(
                name=name.lower(),
                source_entity=data.get("source_entity", "").lower(),
                target_entity=data.get("target_entity", "").lower(),
                join_type=data.get("join_type", "LEFT").upper(),
                cardinality=data.get("cardinality", "ONE_TO_MANY").upper(),
                source_key=data.get("source_key", ""),
                target_key=data.get("target_key", ""),
                description=data.get("description", ""),
            )

        # 6. Time Dimensions
        raw_time = self._read_yaml("time.yaml").get("time_dimensions", {})
        for name, data in raw_time.items():
            catalog.time_dimensions[name.lower()] = TimeDimension(
                name=name.lower(),
                display_name=data.get("display_name", name),
                description=data.get("description", ""),
                type=data.get("type", "TIMESTAMP"),
                default_granularity=data.get("default_granularity", "DAY"),
                supported_granularities=data.get("supported_granularities", ["DAY", "MONTH", "YEAR"]),
                entity=data.get("entity", "").lower(),
                column=data.get("column", ""),
            )

        # 7. Glossary
        raw_glossary = self._read_yaml("glossary.yaml").get("glossary", {})
        for name, data in raw_glossary.items():
            catalog.glossary[name.lower()] = GlossaryTerm(
                name=data.get("name", name),
                definition=data.get("definition", ""),
                synonyms=data.get("synonyms", []),
                related_entities=data.get("related_entities", []),
                related_measures=data.get("related_measures", []),
                related_dimensions=data.get("related_dimensions", []),
            )

        logger.info(
            f"Loaded SemanticCatalog: {len(catalog.entities)} entities, "
            f"{len(catalog.dimensions)} dimensions, {len(catalog.measures)} measures, "
            f"{len(catalog.metrics)} metrics, {len(catalog.relationships)} relationships, "
            f"{len(catalog.time_dimensions)} time dimensions, {len(catalog.glossary)} glossary terms."
        )
        return catalog


_cached_catalog: Optional[SemanticCatalog] = None


def get_semantic_catalog() -> SemanticCatalog:
    """Singleton getter returning the loaded SemanticCatalog instance."""
    global _cached_catalog
    if _cached_catalog is None:
        loader = SemanticCatalogLoader()
        _cached_catalog = loader.load_catalog()
    return _cached_catalog


def invalidate_catalog_cache() -> None:
    """Reset the in-memory cached SemanticCatalog instance."""
    global _cached_catalog
    _cached_catalog = None
    logger.info("[Catalog Cache] Invalidated in-memory semantic catalog.")

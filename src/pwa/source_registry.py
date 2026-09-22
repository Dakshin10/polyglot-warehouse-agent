"""Source registry for the Nexora Technologies enterprise data platform.

Reads source definitions from config/sources.yaml and provides a typed
interface for discovering, testing, and iterating over registered sources.

Usage:
    from pwa.source_registry import get_registry, list_source_names

    registry = get_registry()
    for source in registry.sources:
        print(source.name, source.bq_raw_dataset)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger("pwa.source_registry")

# Path to the sources configuration file
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCES_CONFIG = REPO_ROOT / "config" / "sources.yaml"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SourceTableConfig:
    """Configuration for a single source table within a source system."""

    name: str
    source_file_pattern: str
    primary_key: Optional[str] = None
    watermark_column: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class CrossDatasetLink:
    """A declared FK relationship between two source systems."""

    target_source: str
    join_key: str
    join_target_table: str


@dataclass
class SourceConfig:
    """Configuration for a single registered source system."""

    name: str
    type: str  # "file" | "database"
    provider: str  # "kaggle" | "mysql" | "postgres"
    slug: str  # Kaggle dataset slug
    source_url: str
    domain: str  # "enterprise" | "marketplace" | "marketing"
    description: str
    ingestion_mode: str  # "snapshot" | "incremental"
    local_path: str
    bq_raw_dataset: str
    license: str
    tables: list[SourceTableConfig] = field(default_factory=list)
    cross_dataset_links: list[CrossDatasetLink] = field(default_factory=list)

    @property
    def local_dir(self) -> Path:
        """Absolute path to local source data directory."""
        return (REPO_ROOT / self.local_path).resolve()

    @property
    def table_names(self) -> list[str]:
        return [t.name for t in self.tables]

    def get_table(self, name: str) -> Optional[SourceTableConfig]:
        for t in self.tables:
            if t.name == name:
                return t
        return None


@dataclass
class SourceRegistry:
    """In-memory registry of all configured source systems."""

    sources: list[SourceConfig]

    def get(self, name: str) -> Optional[SourceConfig]:
        """Get a source by name (case-insensitive)."""
        for s in self.sources:
            if s.name.lower() == name.lower():
                return s
        return None

    def names(self) -> list[str]:
        """Return all registered source names."""
        return [s.name for s in self.sources]

    def by_domain(self, domain: str) -> list[SourceConfig]:
        """Return sources filtered by domain."""
        return [s for s in self.sources if s.domain == domain]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _parse_table(raw: dict) -> SourceTableConfig:
    return SourceTableConfig(
        name=raw["name"],
        source_file_pattern=raw.get("source_file_pattern", "*"),
        primary_key=raw.get("primary_key"),
        watermark_column=raw.get("watermark_column"),
        notes=raw.get("notes"),
    )


def _parse_cross_link(raw: dict) -> CrossDatasetLink:
    return CrossDatasetLink(
        target_source=raw["target_source"],
        join_key=raw["join_key"],
        join_target_table=raw["join_target_table"],
    )


def _parse_source(raw: dict) -> SourceConfig:
    tables = [_parse_table(t) for t in raw.get("tables", [])]
    links = [_parse_cross_link(lnk) for lnk in raw.get("cross_dataset_links", [])]
    return SourceConfig(
        name=raw["name"],
        type=raw.get("type", "file"),
        provider=raw.get("provider", "kaggle"),
        slug=raw.get("slug", ""),
        source_url=raw.get("source_url", ""),
        domain=raw.get("domain", ""),
        description=raw.get("description", ""),
        ingestion_mode=raw.get("ingestion_mode", "snapshot"),
        local_path=raw.get("local_path", f"data/source/{raw['name']}/"),
        bq_raw_dataset=raw.get("bq_raw_dataset", f"raw_{raw['name']}"),
        license=raw.get("license", "unknown"),
        tables=tables,
        cross_dataset_links=links,
    )


def load_registry(config_path: Path = SOURCES_CONFIG) -> SourceRegistry:
    """Load and parse the source registry from config/sources.yaml."""
    if not config_path.exists():
        raise FileNotFoundError(f"Source registry config not found: {config_path}\nExpected at: {SOURCES_CONFIG}")

    with open(config_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    sources_raw = raw.get("sources", [])
    if not sources_raw:
        raise ValueError(f"No sources defined in {config_path}")

    sources = [_parse_source(s) for s in sources_raw]
    logger.info(f"Loaded {len(sources)} source(s) from registry: {[s.name for s in sources]}")
    return SourceRegistry(sources=sources)


# Singleton for convenience
_registry: Optional[SourceRegistry] = None


def get_registry() -> SourceRegistry:
    """Return the singleton source registry, loading it on first call."""
    global _registry
    if _registry is None:
        _registry = load_registry()
    return _registry


def list_source_names() -> list[str]:
    """Return all registered source names."""
    return get_registry().names()


# ---------------------------------------------------------------------------
# Source testing utilities
# ---------------------------------------------------------------------------


def test_source_connectivity(source: SourceConfig) -> dict:
    """Test whether a source's data files or database instance are present and readable."""
    result: dict[str, Any] = {
        "name": source.name,
        "status": "unknown",
        "local_dir": str(source.local_dir),
        "files_found": [],
        "missing_patterns": [],
        "errors": [],
    }

    if not source.local_dir.exists():
        result["status"] = "missing_dir"
        result["errors"].append(f"Location not found: {source.local_dir}")
        return result

    # Single-file database source (e.g. SQLite database file)
    if source.type == "database" or source.local_dir.is_file():
        if source.local_dir.stat().st_size > 0:
            result["status"] = "ok"
            result["files_found"].append({"file": source.local_dir.name, "size": source.local_dir.stat().st_size})
        else:
            result["status"] = "empty_file"
            result["errors"].append(f"Database file is empty: {source.local_dir}")
        return result

    import glob

    files_found = []
    missing_patterns = []

    for table_cfg in source.tables:
        pattern = str(source.local_dir / table_cfg.source_file_pattern)
        matches = glob.glob(pattern)
        if matches:
            for m in matches:
                p = Path(m)
                files_found.append({"table": table_cfg.name, "file": p.name, "size": p.stat().st_size})
        else:
            missing_patterns.append({"table": table_cfg.name, "pattern": table_cfg.source_file_pattern})

    result["files_found"] = files_found
    result["missing_patterns"] = missing_patterns

    if not files_found:
        result["status"] = "no_files"
        result["errors"].append(f"No source files found in {source.local_dir}.")
    elif missing_patterns:
        result["status"] = "partial"
    else:
        result["status"] = "ok"

    return result

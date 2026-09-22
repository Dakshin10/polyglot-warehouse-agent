"""Unit tests for enterprise source registry and dataset integrity verification."""

from pwa.source_registry import get_registry, list_source_names


def test_registry_contains_three_enterprise_sources():
    """Verify registry loads all 3 enterprise sources: adventureworks, olist, olist_marketing."""
    names = list_source_names()
    assert "adventureworks" in names
    assert "olist" in names
    assert "olist_marketing" in names


def test_registry_sources_have_valid_domains():
    """Verify sources belong to enterprise, marketplace, or marketing domains."""
    registry = get_registry()
    domains = {s.domain for s in registry.sources}
    assert "enterprise" in domains
    assert "marketplace" in domains
    assert "marketing" in domains

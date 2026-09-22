"""Deterministic analytical query templates for Phase 2A Semantic Layer."""

from __future__ import annotations

from pwa.semantic.query_planner import AnalyticalIntent


def template_metric_by_dimension(metric_name: str, dimension_name: str, limit: int = 100) -> AnalyticalIntent:
    """Build an AnalyticalIntent for aggregating a metric by a single dimension."""
    return AnalyticalIntent(
        metrics=[metric_name],
        dimensions=[dimension_name],
        group_by=[dimension_name],
        order_by=[metric_name],
        limit=limit,
    )


def template_metric_over_time(
    metric_name: str,
    time_dimension_name: str = "order_date",
    granularity: str | None = None,
    limit: int = 100,
) -> AnalyticalIntent:
    """Build an AnalyticalIntent for aggregating a metric over time."""
    return AnalyticalIntent(
        metrics=[metric_name],
        dimensions=[time_dimension_name],
        time_dimension=time_dimension_name,
        granularity=granularity,
        group_by=[time_dimension_name],
        order_by=[time_dimension_name],
        limit=limit,
    )


def template_top_n_entities(metric_name: str, dimension_name: str, n: int = 10) -> AnalyticalIntent:
    """Build an AnalyticalIntent for retrieving Top-N entities by metric value."""
    return AnalyticalIntent(
        metrics=[metric_name],
        dimensions=[dimension_name],
        group_by=[dimension_name],
        order_by=[metric_name],
        limit=n,
    )

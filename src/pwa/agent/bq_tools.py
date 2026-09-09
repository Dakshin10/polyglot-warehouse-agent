"""ADK BigQueryToolset for Polyglot Warehouse Agent scoped to mart views."""

from __future__ import annotations

import logging
from typing import Any, Optional

import google.auth
from google.cloud import bigquery

try:
    from google.adk.integrations.bigquery import BigQueryCredentialsConfig, BigQueryToolset
    from google.adk.integrations.bigquery.config import BigQueryToolConfig, WriteMode
except ImportError:  # pragma: no cover
    from google.adk.tools.bigquery import BigQueryCredentialsConfig, BigQueryToolset
    from google.adk.tools.bigquery.config import BigQueryToolConfig, WriteMode

from pwa.connections import get_bq_client
from pwa.settings import get_settings

logger = logging.getLogger("pwa.agent.bq_tools")

# Strict surface of allowed read-only mart views
ALLOWED_MART_VIEWS: set[str] = {
    "mart.v_movie",
    "mart.v_movie_credits",
    "mart.v_movie_keywords",
    "mart.v_movie_full",
    "mart.v_integrity_exceptions",
}


def validate_mart_table(table_name: str) -> str:
    """Validate that a requested table/view is strictly within the allowed mart surface.

    Raises:
        ValueError: If table_name is empty or not in ALLOWED_MART_VIEWS.
    """
    if not table_name:
        raise ValueError("Table name cannot be empty.")

    clean_name = table_name.strip().strip("`").lower()
    parts = clean_name.split(".")
    if len(parts) >= 2:
        canonical_name = f"{parts[-2]}.{parts[-1]}"
    else:
        canonical_name = clean_name

    if canonical_name not in ALLOWED_MART_VIEWS:
        raise ValueError(
            f"Access denied: '{table_name}' is not in the allowed mart view surface: {sorted(ALLOWED_MART_VIEWS)}"
        )
    return canonical_name


def get_mart_credentials_config() -> BigQueryCredentialsConfig:
    """Create ADK BigQueryCredentialsConfig using ADC matching PWA auth path."""
    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/bigquery"])
    except Exception as err:
        logger.warning(f"Could not load Google default credentials: {err}")
        credentials = None
    return BigQueryCredentialsConfig(credentials=credentials)


def get_mart_tool_config() -> BigQueryToolConfig:
    """Create ADK BigQueryToolConfig with WriteMode.BLOCKED strictly enforced."""
    project_id = "salitsteel-502008"
    location = "EU"
    try:
        settings = get_settings()
        project_id = settings.gcp_project or project_id
        location = settings.bq_location or location
    except Exception:
        pass

    return BigQueryToolConfig(
        write_mode=WriteMode.BLOCKED,
        compute_project_id=project_id,
        location=location,
    )


def get_mart_toolset() -> BigQueryToolset:
    """Instantiate and return a read-only ADK BigQueryToolset for mart views."""
    credentials_config = get_mart_credentials_config()
    tool_config = get_mart_tool_config()
    return BigQueryToolset(
        credentials_config=credentials_config,
        bigquery_tool_config=tool_config,
    )


def schema_snapshot(
    client: Optional[bigquery.Client] = None,
    project_id: Optional[str] = None,
    dataset: Optional[str] = None,
) -> dict[str, list[dict[str, Any]]]:
    """Query INFORMATION_SCHEMA for mart views and return column names, types, and descriptions."""
    if client is None:
        client = get_bq_client()

    if not project_id or not dataset:
        try:
            settings = get_settings()
            project_id = project_id or settings.gcp_project
            dataset = dataset or settings.bq_ds_mart
        except Exception:
            project_id = project_id or getattr(client, "project", "salitsteel-502008")
            dataset = dataset or "mart"

    mart_view_names = ["v_movie", "v_movie_credits", "v_movie_keywords", "v_movie_full", "v_integrity_exceptions"]

    view_list_str = ", ".join(repr(v) for v in mart_view_names)
    # Use INFORMATION_SCHEMA.COLUMNS which is standard across all BigQuery datasets
    query = f"""
    SELECT
        table_name,
        column_name,
        data_type
    FROM `{project_id}.{dataset}.INFORMATION_SCHEMA.COLUMNS`
    WHERE table_name IN ({view_list_str})
    ORDER BY table_name, ordinal_position
    """

    logger.info(f"Fetching schema snapshot for mart views in project '{project_id}'...")
    query_job = client.query(query)
    results = query_job.result()

    snapshot: dict[str, list[dict[str, Any]]] = {f"mart.{v}": [] for v in mart_view_names}

    for row in results:
        view_key = f"mart.{row.table_name}"
        if view_key not in snapshot:
            snapshot[view_key] = []
        snapshot[view_key].append(
            {
                "name": row.column_name,
                "type": row.data_type,
                "description": getattr(row, "description", "") or "",
            }
        )

    return snapshot

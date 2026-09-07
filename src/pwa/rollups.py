"""Rollup table materialization and refresh service for BigQuery analytical queries."""

import logging

from google.cloud import bigquery

from pwa.connections import get_bq_client
from pwa.settings import get_settings

logger = logging.getLogger("pwa.rollups")


def ensure_rollup_dataset(client: bigquery.Client, project_id: str) -> str:
    """Ensure that the 'rollup' dataset exists in BigQuery."""
    dataset_id = f"{project_id}.rollup"
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = "EU"  # Match BQ location of mart views
    try:
        client.create_dataset(dataset, exists_ok=True)
        logger.info(f"Ensured dataset '{dataset_id}' exists.")
    except Exception as e:
        logger.warning(f"Could not create dataset '{dataset_id}': {e}")
    return dataset_id


def refresh_rollups() -> bool:
    """Recompute and materialize BigQuery rollup tables from mart views.

    Returns True if all rollup tables were refreshed successfully.
    """
    settings = get_settings()
    project = settings.gcp_project
    client = get_bq_client()

    logger.info(f"Starting rollup tables refresh for project '{project}'...")
    ensure_rollup_dataset(client, project)

    queries = {
        "avg_roi_by_director": f"""
            CREATE OR REPLACE TABLE `{project}.rollup.avg_roi_by_director` AS
            SELECT
                director_name,
                ROUND(AVG(roi), 2) AS avg_roi,
                COUNT(*) AS movie_count,
                CURRENT_TIMESTAMP() AS last_refreshed
            FROM `{project}.mart.v_movie_full`
            WHERE director_name IS NOT NULL
              AND roi IS NOT NULL
              AND budget_usd > 1000
            GROUP BY director_name
            ORDER BY avg_roi DESC
        """,
        "avg_cast_size_by_revenue_threshold": f"""
            CREATE OR REPLACE TABLE `{project}.rollup.avg_cast_size_by_revenue_threshold` AS
            SELECT
                revenue_threshold,
                ROUND(AVG(cast_size), 2) AS avg_cast_size,
                COUNT(*) AS movie_count,
                CURRENT_TIMESTAMP() AS last_refreshed
            FROM (
                SELECT 100000000 AS revenue_threshold, cast_size FROM `{project}.mart.v_movie_full` WHERE revenue_usd >= 100000000 AND cast_size IS NOT NULL
                UNION ALL
                SELECT 250000000 AS revenue_threshold, cast_size FROM `{project}.mart.v_movie_full` WHERE revenue_usd >= 250000000 AND cast_size IS NOT NULL
                UNION ALL
                SELECT 500000000 AS revenue_threshold, cast_size FROM `{project}.mart.v_movie_full` WHERE revenue_usd >= 500000000 AND cast_size IS NOT NULL
                UNION ALL
                SELECT 1000000000 AS revenue_threshold, cast_size FROM `{project}.mart.v_movie_full` WHERE revenue_usd >= 1000000000 AND cast_size IS NOT NULL
            )
            GROUP BY revenue_threshold
            ORDER BY revenue_threshold ASC
        """,
        "top_grossing_movies": f"""
            CREATE OR REPLACE TABLE `{project}.rollup.top_grossing_movies` AS
            SELECT
                title,
                revenue_usd AS revenue,
                director_name,
                ROW_NUMBER() OVER (ORDER BY revenue_usd DESC) AS rank,
                CURRENT_TIMESTAMP() AS last_refreshed
            FROM `{project}.mart.v_movie_full`
            WHERE revenue_usd IS NOT NULL AND title IS NOT NULL
        """,
    }

    success = True
    for name, sql in queries.items():
        try:
            logger.info(f"Materializing rollup table '{project}.rollup.{name}'...")
            query_job = client.query(sql)
            query_job.result()  # Wait for completion
            logger.info(f"Successfully refreshed 'rollup.{name}'.")
        except Exception as e:
            logger.error(f"Failed to refresh 'rollup.{name}': {e}")
            success = False

    if success:
        logger.info("All rollup tables refreshed successfully.")
    else:
        logger.error("One or more rollup table refreshes failed.")

    return success

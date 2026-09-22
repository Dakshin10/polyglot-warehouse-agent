"""BigQuery infrastructure setup for the Nexora Technologies enterprise platform.

Creates all 9 BigQuery datasets idempotently:
  - raw_adventureworks       (raw enterprise ERP data)
  - raw_olist                (raw marketplace data)
  - raw_olist_marketing      (raw marketing funnel data)
  - staging_enterprise       (normalized enterprise staging)
  - staging_marketplace      (normalized marketplace staging)
  - curated_enterprise       (canonical enterprise model)
  - curated_marketplace      (canonical marketplace model)
  - pwa_metadata             (control plane / audit log)
  - rollup                   (materialized fast-path tables)

Also sets up the warehouse-agent service account with least-privilege access
(read-only on curated datasets only).

Note: Cloud SQL PostgreSQL federation (EXTERNAL_QUERY) is removed from the
primary pipeline. MySQL and PostgreSQL connections are preserved in
connections.py for optional future use.
"""

import logging
import subprocess

from google.cloud import bigquery
from google.api_core.exceptions import NotFound

from pwa.connections import get_bq_client
from pwa.settings import get_settings

logger = logging.getLogger("pwa.bigquery_setup")


# ---------------------------------------------------------------------------
# Dataset creation
# ---------------------------------------------------------------------------


def create_datasets(client: bigquery.Client, project: str, location: str) -> list[str]:
    """Create all 9 Nexora enterprise BigQuery datasets idempotently."""
    s = get_settings()
    dataset_ids = s.all_bq_datasets()

    for ds_id in dataset_ids:
        dataset_ref = bigquery.Dataset(f"{project}.{ds_id}")
        dataset_ref.location = location
        try:
            client.create_dataset(dataset_ref, exists_ok=True)
            logger.info(f"Dataset `{project}.{ds_id}` ready (location={location})")
        except Exception as e:
            logger.error(f"Failed to create dataset `{ds_id}`: {e}")
            raise

    logger.info(f"All {len(dataset_ids)} datasets confirmed: {dataset_ids}")
    return dataset_ids


# ---------------------------------------------------------------------------
# Service account setup
# ---------------------------------------------------------------------------


def setup_warehouse_agent_sa(project: str) -> str:
    """Create warehouse-agent service account and grant least-privilege access.

    The agent SA gets:
    - roles/bigquery.jobUser on the project (to run queries)
    - roles/bigquery.dataViewer on curated datasets only (not raw/staging)
    """
    s = get_settings()
    sa_name = "warehouse-agent"
    sa_email = f"{sa_name}@{project}.iam.gserviceaccount.com"

    try:
        subprocess.run(
            [
                "gcloud",
                "iam",
                "service-accounts",
                "create",
                sa_name,
                f"--project={project}",
                "--display-name=Nexora Warehouse Agent SA",
                "--quiet",
            ],
            check=True,
            capture_output=True,
            text=True,
            shell=True,
        )
        logger.info(f"Created service account: {sa_email}")
    except subprocess.CalledProcessError as e:
        if "already exists" in e.stderr.lower():
            logger.info(f"Service account already exists: {sa_email}")
        else:
            logger.warning(f"SA creation warning: {e.stderr}")

    # Grant bigquery.jobUser at project level
    try:
        subprocess.run(
            [
                "gcloud",
                "projects",
                "add-iam-policy-binding",
                project,
                f"--member=serviceAccount:{sa_email}",
                "--role=roles/bigquery.jobUser",
                "--condition=None",
                "--quiet",
            ],
            check=True,
            capture_output=True,
            text=True,
            shell=True,
        )
        logger.info(f"Granted roles/bigquery.jobUser to {sa_email}")
    except subprocess.CalledProcessError as e:
        logger.warning(f"IAM binding warning: {e.stderr}")

    # Grant dataViewer only on curated datasets (not raw or staging)
    client = get_bq_client()
    for ds_id in s.curated_datasets():
        _grant_dataset_viewer(client, project, ds_id, sa_email)

    return sa_email


def _grant_dataset_viewer(client: bigquery.Client, project: str, ds_id: str, sa_email: str) -> None:
    """Grant bigquery.dataViewer role on one dataset to a service account email."""
    try:
        dataset_ref = client.get_dataset(f"{project}.{ds_id}")
        access_entries = list(dataset_ref.access_entries)
        exists = any(e.role == "roles/bigquery.dataViewer" and e.entity_id == sa_email for e in access_entries)
        if not exists:
            access_entries.append(
                bigquery.AccessEntry(
                    role="roles/bigquery.dataViewer",
                    entity_type="userByEmail",
                    entity_id=sa_email,
                )
            )
            dataset_ref.access_entries = access_entries
            client.update_dataset(dataset_ref, ["access_entries"])
            logger.info(f"Granted roles/bigquery.dataViewer on `{ds_id}` to {sa_email}")
        else:
            logger.info(f"dataViewer already granted on `{ds_id}` to {sa_email}")
    except Exception as e:
        logger.warning(f"Dataset IAM binding warning for `{ds_id}`: {e}")


# ---------------------------------------------------------------------------
# View authorization (curated views reading from raw/staging)
# ---------------------------------------------------------------------------


def authorize_curated_views(client: bigquery.Client, project: str) -> None:
    """Authorize curated views to read from raw and staging datasets.

    BigQuery requires explicit view authorization when a view in dataset A
    queries tables in dataset B that belong to a different dataset.
    """
    s = get_settings()
    ds_curated_ent = s.bq_ds_curated_ent
    ds_curated_mkt = s.bq_ds_curated_mkt

    # Enterprise curated views need to read from raw_adventureworks + staging_enterprise
    enterprise_source_datasets = [s.bq_ds_raw_aw, s.bq_ds_staging_ent]
    # Marketplace curated views need to read from raw_olist + raw_olist_marketing + staging_marketplace
    marketplace_source_datasets = [s.bq_ds_raw_olist, s.bq_ds_raw_marketing, s.bq_ds_staging_mkt]

    view_dataset_pairs = [
        (ds_curated_ent, enterprise_source_datasets),
        (ds_curated_mkt, marketplace_source_datasets),
    ]

    for view_ds_id, source_ds_ids in view_dataset_pairs:
        # Get all views in this curated dataset
        try:
            tables = list(client.list_tables(f"{project}.{view_ds_id}"))
            view_names = [t.table_id for t in tables if t.table_type == "VIEW"]
        except Exception as e:
            logger.warning(f"Could not list views in `{view_ds_id}`: {e}")
            view_names = []

        if not view_names:
            logger.info(f"No views found in `{view_ds_id}` yet — skipping authorization.")
            continue

        for src_ds_id in source_ds_ids:
            _authorize_views_on_dataset(client, project, view_ds_id, view_names, src_ds_id)


def _authorize_views_on_dataset(
    client: bigquery.Client,
    project: str,
    view_ds_id: str,
    view_names: list[str],
    source_ds_id: str,
) -> None:
    """Authorize a list of views from view_ds_id to read source_ds_id."""
    try:
        dataset_ref = client.get_dataset(f"{project}.{source_ds_id}")
    except NotFound:
        logger.warning(f"Source dataset `{source_ds_id}` not found; skipping authorization.")
        return

    access_entries = list(dataset_ref.access_entries)
    existing_views = {
        (e.entity_id.get("projectId"), e.entity_id.get("datasetId"), e.entity_id.get("tableId"))
        for e in access_entries
        if e.entity_type == "view" and e.entity_id
    }

    added = 0
    for view_name in view_names:
        try:
            client.get_table(f"{project}.{view_ds_id}.{view_name}")
        except NotFound:
            logger.info(f"Skipping authorization for `{view_ds_id}.{view_name}` (not created yet)")
            continue

        key = (project, view_ds_id, view_name)
        if key not in existing_views:
            access_entries.append(
                bigquery.AccessEntry(
                    role=None,
                    entity_type="view",
                    entity_id={"projectId": project, "datasetId": view_ds_id, "tableId": view_name},
                )
            )
            added += 1

    if added > 0:
        dataset_ref.access_entries = access_entries
        client.update_dataset(dataset_ref, ["access_entries"])
        logger.info(f"Authorized {added} curated view(s) on `{source_ds_id}`")
    else:
        logger.info(f"All curated views already authorized on `{source_ds_id}`")


# ---------------------------------------------------------------------------
# Main setup entry point
# ---------------------------------------------------------------------------


def run_setup() -> bool:
    """Run the full BigQuery infrastructure setup for Nexora enterprise platform."""
    s = get_settings()
    project = s.gcp_project
    location = s.bq_location

    client = get_bq_client()

    logger.info("=== STEP 1: CREATE ALL BIGQUERY DATASETS ===")
    create_datasets(client, project, location)

    logger.info("=== STEP 2: SETUP WAREHOUSE AGENT SERVICE ACCOUNT ===")
    setup_warehouse_agent_sa(project)

    logger.info("=== STEP 3: AUTHORIZE CURATED VIEWS ON SOURCE DATASETS ===")
    authorize_curated_views(client, project)

    logger.info("=== BIGQUERY INFRASTRUCTURE SETUP COMPLETE ===")
    return True


if __name__ == "__main__":
    from pwa.logging_setup import setup_logging

    setup_logging()
    raise SystemExit(0 if run_setup() else 1)

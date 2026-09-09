import sys
import logging
import subprocess

from google.cloud import bigquery
from google.cloud.bigquery_connection_v1 import ConnectionServiceClient
from google.cloud.bigquery_connection_v1.types import (
    Connection,
    CloudSqlProperties,
    CloudSqlCredential,
    CreateConnectionRequest,
    GetConnectionRequest,
)
from google.api_core.exceptions import NotFound, AlreadyExists

from pwa.connections import get_bq_client
from pwa.settings import get_settings

logger = logging.getLogger("pwa.bigquery_setup")


def create_datasets(client, project, location):
    """Create the 4 BQ datasets idempotently."""
    s = get_settings()
    dataset_ids = [s.bq_ds_registry, s.bq_ds_credits, s.bq_ds_files, s.bq_ds_mart]
    for ds_id in dataset_ids:
        dataset_ref = bigquery.Dataset(f"{project}.{ds_id}")
        dataset_ref.location = location
        try:
            client.create_dataset(dataset_ref, exists_ok=True)
            logger.info(f"Dataset `{project}.{ds_id}` ready (location={location})")
        except Exception as e:
            logger.error(f"Failed to create dataset `{ds_id}`: {e}")
            raise
    return dataset_ids


def create_connection(project, location, connection_id, instance_conn_name, pg_db, pg_user, pg_password):
    """Create a BigQuery connection to Cloud SQL PostgreSQL, or return existing."""
    conn_client = ConnectionServiceClient()
    parent = f"projects/{project}/locations/{location}"
    full_name = f"{parent}/connections/{connection_id}"

    try:
        existing = conn_client.get_connection(GetConnectionRequest(name=full_name))
        logger.info(f"BigQuery connection already exists: {full_name}")
        return existing
    except NotFound:
        logger.info(f"No BigQuery connection at {full_name} yet; creating it.")

    cloud_sql_props = CloudSqlProperties(
        instance_id=instance_conn_name,
        database=pg_db,
        type_=CloudSqlProperties.DatabaseType.POSTGRES,
        credential=CloudSqlCredential(username=pg_user, password=pg_password),
    )
    connection = Connection(cloud_sql=cloud_sql_props)

    try:
        created = conn_client.create_connection(
            CreateConnectionRequest(
                parent=parent,
                connection_id=connection_id,
                connection=connection,
            )
        )
        logger.info(f"Created BigQuery connection: {created.name}")
        return created
    except AlreadyExists:
        existing = conn_client.get_connection(GetConnectionRequest(name=full_name))
        logger.info(f"BigQuery connection already exists: {full_name}")
        return existing


def grant_connection_service_agent(project, connection):
    """Grant the connection's service agent roles/cloudsql.client on the project."""
    sa_email = connection.cloud_sql.service_account_id
    if not sa_email:
        logger.warning("No service account found on connection; skipping IAM grant.")
        return

    logger.info(f"Connection service agent: {sa_email}")
    logger.info(f"Granting roles/cloudsql.client to {sa_email} on project {project}...")

    try:
        subprocess.run(
            [
                "gcloud",
                "projects",
                "add-iam-policy-binding",
                project,
                f"--member=serviceAccount:{sa_email}",
                "--role=roles/cloudsql.client",
                "--condition=None",
                "--quiet",
            ],
            check=True,
            capture_output=True,
            text=True,
            shell=True,
        )
        logger.info(f"Granted roles/cloudsql.client to {sa_email}")
    except subprocess.CalledProcessError as e:
        logger.warning(f"IAM grant via gcloud failed (may already exist): {e.stderr}")
    except FileNotFoundError:
        logger.warning("gcloud CLI not found. Please grant roles/cloudsql.client manually:")
        logger.warning(
            f"  gcloud projects add-iam-policy-binding {project} "
            f"--member=serviceAccount:{sa_email} --role=roles/cloudsql.client"
        )


def verify_connection(client, project, location, connection_id):
    """Verify the BigQuery connection by running EXTERNAL_QUERY SELECT 1."""
    conn_resource = f"{project}.{location}.{connection_id}"
    query = f"""SELECT * FROM EXTERNAL_QUERY('{conn_resource}', 'SELECT 1 AS ok');"""

    logger.info(f"Verifying connection with EXTERNAL_QUERY via {conn_resource}...")
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=100_000_000)
    try:
        result = client.query(query, job_config=job_config).result()
        rows = list(result)
        if len(rows) == 0 or rows[0]["ok"] != 1:
            logger.error("Connection verification failed: EXTERNAL_QUERY returned no rows or unexpected result.")
            sys.exit(1)
        logger.info("Connection verification PASSED: EXTERNAL_QUERY returned ok=1")
    except Exception as e:
        logger.error(f"Connection verification FAILED: {e}")
        sys.exit(1)


def create_federated_view(client, project, location, connection_id):
    """Create the federated view for raw_credits.movie_credits."""
    ds_credits = get_settings().bq_ds_credits
    conn_resource = f"{project}.{location}.{connection_id}"

    view_sql = f"""
CREATE OR REPLACE VIEW `{project}.{ds_credits}.movie_credits` AS
SELECT * FROM EXTERNAL_QUERY(
  '{conn_resource}',
  '''SELECT credit_id, movie_id, director_name, director_gender,
            lead_actor_name, second_actor_name, lead_actor_gender,
            cast_size, crew_size, producer_name
     FROM movie_credits'''
);
"""
    logger.info(f"Creating federated view `{ds_credits}.movie_credits`...")
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=100_000_000)
    client.query(view_sql, job_config=job_config).result()
    logger.info(f"Federated view `{ds_credits}.movie_credits` created.")


def setup_warehouse_agent_sa(project):
    """Create warehouse-agent service account and grant minimal permissions."""
    sa_name = "warehouse-agent"
    sa_email = f"{sa_name}@{project}.iam.gserviceaccount.com"
    ds_mart = get_settings().bq_ds_mart

    try:
        subprocess.run(
            [
                "gcloud",
                "iam",
                "service-accounts",
                "create",
                sa_name,
                f"--project={project}",
                "--display-name=Warehouse Agent SA",
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

    try:
        client = get_bq_client()
        dataset_ref = client.get_dataset(f"{project}.{ds_mart}")
        access_entries = list(dataset_ref.access_entries)
        exists = any(
            e.role == "roles/bigquery.dataViewer" and e.entity_id == sa_email
            for e in access_entries
        )
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
        logger.info(f"Granted roles/bigquery.dataViewer on {ds_mart} to {sa_email}")
    except Exception as e:
        logger.warning(f"Dataset IAM binding warning: {e}")

    return sa_email


def authorize_mart_views(client, project):
    """Authorize each mart view on each raw_* dataset so cross-dataset queries work."""
    s = get_settings()
    ds_mart = s.bq_ds_mart
    raw_datasets = [s.bq_ds_registry, s.bq_ds_credits, s.bq_ds_files]
    mart_views = [
        "v_movie",
        "v_movie_credits",
        "v_movie_full",
        "v_movie_keywords",
        "v_integrity_exceptions",
    ]

    for raw_ds_id in raw_datasets:
        dataset_ref = client.get_dataset(f"{project}.{raw_ds_id}")
        access_entries = list(dataset_ref.access_entries)
        existing_views = {
            (e.entity_id.get("projectId"), e.entity_id.get("datasetId"), e.entity_id.get("tableId"))
            for e in access_entries
            if e.entity_type == "view" and e.entity_id
        }

        added = 0
        for view_name in mart_views:
            try:
                client.get_table(f"{project}.{ds_mart}.{view_name}")
            except NotFound:
                logger.info(f"Skipping authorization for `{ds_mart}.{view_name}` (view not created yet)")
                continue

            view_ref = {"projectId": project, "datasetId": ds_mart, "tableId": view_name}
            key = (project, ds_mart, view_name)
            if key not in existing_views:
                access_entries.append(
                    bigquery.AccessEntry(
                        role=None,
                        entity_type="view",
                        entity_id=view_ref,
                    )
                )
                added += 1

        if added > 0:
            dataset_ref.access_entries = access_entries
            client.update_dataset(dataset_ref, ["access_entries"])
            logger.info(f"Authorized {added} mart views on `{raw_ds_id}`")
        else:
            logger.info(f"All existing mart views already authorized on `{raw_ds_id}`")


def run_setup():
    """Run the full BigQuery setup: datasets, connection, IAM, federated view, authorized views."""
    s = get_settings()
    project = s.gcp_project
    location = s.bq_location
    connection_id = s.bq_connection_id
    instance_conn_name = s.pg_instance_connection_name
    pg_db = s.pg_db
    pg_bq_user = s.pg_bq_reader_user
    pg_bq_password = s.pg_bq_reader_password

    client = get_bq_client()

    logger.info("=== STEP 1: CREATE BIGQUERY DATASETS ===")
    create_datasets(client, project, location)

    logger.info("=== STEP 1: CREATE BIGQUERY CONNECTION ===")
    connection = create_connection(
        project, location, connection_id, instance_conn_name, pg_db, pg_bq_user, pg_bq_password
    )

    logger.info("=== STEP 1: GRANT CONNECTION SERVICE AGENT IAM ===")
    grant_connection_service_agent(project, connection)

    logger.info("=== STEP 1: VERIFY CONNECTION ===")
    verify_connection(client, project, location, connection_id)

    logger.info("=== STEP 1: CREATE FEDERATED VIEW ===")
    create_federated_view(client, project, location, connection_id)

    logger.info("=== STEP 4: SETUP WAREHOUSE AGENT SERVICE ACCOUNT ===")
    setup_warehouse_agent_sa(project)

    logger.info("=== STEP 4: AUTHORIZE MART VIEWS ON RAW DATASETS ===")
    authorize_mart_views(client, project)

    logger.info("=== BIGQUERY SETUP COMPLETE ===")
    return True


if __name__ == "__main__":
    run_setup()

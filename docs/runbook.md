# Polyglot Warehouse Agent — Operations & Troubleshooting Runbook

This runbook documents every known failure mode, root cause, and exact remedy for issues encountered during pipeline setup and execution.

---

## Failure Modes & Remedies

### 1. Location Mismatch presenting as "Not Found" (`404 Dataset Not Found`)
- **Symptom**: BigQuery `EXTERNAL_QUERY` throws `Dataset not found` or `Table not found` during connection or federated query execution.
- **Root Cause**: The BigQuery dataset (`BQ_LOCATION`), the BigQuery Connection, and the Cloud SQL PostgreSQL instance belong to different region families (e.g., dataset in `US` while Cloud SQL is in `europe-west1`).
- **Diagnosis**: Compare `gcloud sql instances describe <instance>` region against `BQ_LOCATION`.
- **Remedy**: Ensure `BQ_LOCATION` is set to `EU` when Cloud SQL is in `europe-west1` (or `US` when in `us-*`). `pwa config` automatically validates region compatibility.

---

### 2. BigQuery Connection Service Agent Missing `roles/cloudsql.client`
- **Symptom**: `EXTERNAL_QUERY` fails with `Access Denied` or connection timeout during query execution, even though `gcloud connection create` reported success.
- **Root Cause**: BigQuery connection creation generates a unique service account (`service-ACCOUNT_NUMBER@gcp-sa-bigqueryconnection.iam.gserviceaccount.com`), but creation does **not** grant Cloud SQL IAM client permissions.
- **Diagnosis**: Check IAM policy on GCP project for the connection service account.
- **Remedy**:
  ```bash
  gcloud projects add-iam-policy-binding YOUR_PROJECT \
    --member=serviceAccount:service-ACCOUNT_NUMBER@gcp-sa-bigqueryconnection.iam.gserviceaccount.com \
    --role=roles/cloudsql.client
  ```

---

### 3. Permission Denied on Postgres Table `movie_credits`
- **Symptom**: BigQuery `EXTERNAL_QUERY` fails with `ERROR: permission denied for table movie_credits`.
- **Root Cause**: The Cloud SQL connection user (`bqreader`) lacks `SELECT` privileges on the `movie_credits` table (often occurs after DDL recreation by the `loader` user).
- **Remedy**: Run `GRANT SELECT ON movie_credits TO bqreader;` in the `movie_credits` database as the `loader` user or database owner.

---

### 4. Aiven MySQL Idle Power-Down (Slow First Connect)
- **Symptom**: `get_mysql_engine()` times out or takes 15–20 seconds on first execution.
- **Root Cause**: Aiven free/hobby tier instances enter standby after inactivity and spin up on incoming connections.
- **Remedy**: `connect_timeout` is set to 30s in `pwa.db.mysql` with `pool_pre_ping=True` retry logic.

---

### 5. Windows File Locks on Output CSV Files
- **Symptom**: `PermissionError: [Errno 13] Permission denied: 'data/out/movie_keywords.csv'`.
- **Root Cause**: Excel, VS Code CSV viewer extension, or another process holding an open file handle on output CSVs.
- **Remedy**: Close external spreadsheet viewers before running `pwa source run`.

---

### 6. Unclosed String Semicolon Splitting Error in SQL Execution
- **Symptom**: `400 Syntax error: Unclosed string literal` when executing `descriptions.sql`.
- **Root Cause**: Simple string splitting (`sql.split(";")`) breaks when descriptions contain embedded semicolons inside single quotes (e.g. `'... changes over time; higher is more popular'`).
- **Remedy**: `_split_sql_statements()` in `pwa.warehouse.mart` uses a quote-aware parser that ignores semicolons inside single quotes `'...'`.

## `pwa config` fails with "MYSQL_SSL_CA does not exist on disk"

- **Cause**: `certs/ca.pem` is missing. `certs/` is gitignored, so a fresh
  clone never has it.
- **Remedy**: Aiven console → your MySQL service → Overview → download the CA
  certificate, and save it as `certs/ca.pem`.
- **Why this blocks everything**: without the CA the driver cannot verify the
  server's identity. The connection would still be encrypted, which is exactly
  why this used to pass unnoticed — encryption without verification looks
  identical in the logs. Validation now refuses to start rather than
  downgrading silently, and there is no flag to skip it.

## `pwa audit` reports "agent service account read path unverified"

- **Cause**: `iamcredentials.googleapis.com` is disabled on the project, so the
  audit cannot impersonate `warehouse-agent@<project>.iam.gserviceaccount.com`
  to prove that the agent — and only the agent's own permissions — can read
  `mart.v_movie_full`.
- **Remedy**: enable the IAM Service Account Credentials API on the project,
  then re-run `pwa audit`.
- **Note**: gate B11 does *not* cover this. B11 asserts the mart view is
  readable and complete with the pipeline's own credentials; it is named that
  way deliberately, because the impersonated read is a different claim.

## Aiven's free plan powers off when idle

- The first MySQL connect after an idle period can take 30 seconds or more.
  `connect_timeout` is 45 seconds. A slow first connection is not a failure.

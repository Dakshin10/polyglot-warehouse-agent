# BigQuery Landing + Mart Layer

Stage 2–3 of `polyglot-warehouse-agent`. Lands all four source datasets into
BigQuery using three different ingestion patterns, then builds a curated `mart`
layer for downstream agent consumption.

---

## Architecture

```
┌─────────────────────┐     ┌───────────────────────┐
│  Aiven MySQL        │     │  Cloud SQL PostgreSQL  │
│  movie_registry     │     │  movie_credits         │
│  .movie (1000 rows) │     │  .movie_credits (1000) │
└────────┬────────────┘     └───────────┬────────────┘
         │ Python batch                 │ EXTERNAL_QUERY
         │ (replicate_mysql.py)         │ (federated, live)
         ▼                             ▼
┌────────────────┐          ┌────────────────────────┐
│ raw_registry   │          │ raw_credits            │
│ .movie         │          │ .movie_credits (VIEW)  │
└────────┬───────┘          └───────────┬────────────┘
         │                              │
         ├──────────┬───────────────────┤
         ▼          ▼                   ▼
    ┌──────────────────────────────────────────────┐
    │  mart                                        │
    │  .v_movie         (MySQL financials + ROI)   │
    │  .v_movie_credits (PG credits, federated)    │
    │  .v_movie_full    (cross-engine JOIN)         │
    │  .v_movie_keywords (CSV keywords)            │
    │  .v_integrity_exceptions (monitor)           │
    └──────────────────────────────────────────────┘
         ▲          ▲
         │          │
┌────────┴───┐  ┌───┴────────────────────┐
│ raw_files  │  │ Agent SA               │
│ .movie_    │  │ (mart only, via IAM)   │
│  keywords  │  └────────────────────────┘
│ .movie_    │
│  ratings   │
└────────────┘
```

### Ingestion Patterns

| Source | Engine | Pattern | Why |
|---|---|---|---|
| Cloud SQL PG | PostgreSQL | **Federated** (`EXTERNAL_QUERY`) | Proves live federation; queries hit Postgres directly |
| Aiven MySQL | MySQL | **Replicated** (Python batch) | Aiven can't be federated; `EXTERNAL_QUERY` only reaches Cloud SQL |
| CSVs | File | **Batch load** | Standard file ingestion with explicit schemas |

---

## Prerequisites

1. **GCP Setup**:
   - Enable BigQuery API and BigQuery Connection API
   - Run `gcloud auth application-default login`
   - Never put a service account key file in the repo

2. **Cloud SQL `bqreader` user**:
   ```sql
   CREATE USER bqreader WITH PASSWORD '...';
   GRANT CONNECT ON DATABASE movie_credits TO bqreader;
   GRANT USAGE ON SCHEMA public TO bqreader;
   GRANT SELECT ON movie_credits TO bqreader;
   ```

3. **Region alignment**: BigQuery datasets, the BQ connection, and Cloud SQL
   must all be in the same region family (e.g., `EU` for `europe-west1`).

---

## Environment Configuration

Add to `.env`:

```ini
GCP_PROJECT=your-gcp-project-id
BQ_LOCATION=EU
BQ_CONNECTION_ID=movie-credits-conn

PG_BQ_READER_USER=bqreader
PG_BQ_READER_PASSWORD=your_bqreader_password

BQ_DS_REGISTRY=raw_registry
BQ_DS_CREDITS=raw_credits
BQ_DS_FILES=raw_files
BQ_DS_MART=mart
```

Install dependencies:
```bash
pip install -r requirements.txt
```

---

## Execution

```bash
python -m src.bq_pipeline
```

Pipeline stages:
1. **Setup** (`src/bq_setup.py`): Create 4 datasets, BigQuery connection to Cloud SQL, grant IAM, verify connection, create federated view, setup agent SA, authorize mart views
2. **Replicate MySQL** (`src/replicate_mysql.py`): Aiven MySQL → `raw_registry.movie` (WRITE_TRUNCATE)
3. **Load CSVs** (`src/load_csv_bq.py`): CSVs → `raw_files.movie_keywords` and `raw_files.movie_ratings_agg`
4. **Build Mart** (`src/build_mart.py`): Execute `sql/bq_mart.sql` (5 views) then `sql/bq_descriptions.sql` (all descriptions)
5. **Verify** (`src/verify_bq.py`): 15 verification gates

---

## Verification Gates

| Gate | Description | Condition |
|---|---|---|
| B1 | `raw_registry.movie` row count | == 1000 |
| B2 | `raw_credits.movie_credits` (federated) | == 1000 |
| B3 | `raw_files.movie_keywords` distinct movie_ids | == 1000 |
| B4 | `raw_files.movie_ratings_agg` row count | == 1000 |
| B5 | `mart.v_movie_full` row count | == 1000 |
| B6 | `mart.v_integrity_exceptions` | == 0 rows |
| B7 | NULL director_name in v_movie_full | == 0 |
| B8 | NULL avg_rating in v_movie_full | == 0 |
| B9 | Every mart view has a description | true |
| B10 | Every mart column has a description | true |
| B11 | Agent SA CAN query mart.v_movie_full | true |
| B12 | Agent SA CANNOT query raw_registry.movie | true (negative) |
| B13 | selected_movie_ids.csv SHA-256 stable | matches fixture |
| B14 | Federation liveness (mutate PG, observe in BQ) | count changes |
| B15 | Cross-engine proof (top 10 directors by ROI) | >= 10 rows |

---

## Troubleshooting

- **"Dataset not found" on EXTERNAL_QUERY**: Location mismatch. The BQ dataset,
  connection, and Cloud SQL instance must be in the same region family. Check
  `BQ_LOCATION` matches your Cloud SQL region.
- **Connection appears healthy but queries fail**: The connection's service
  agent needs `roles/cloudsql.client`. This fails at query time, not at
  connection creation.
- **Permission denied on mart views**: Mart views need to be authorized on each
  `raw_*` dataset. Run `authorize_mart_views()` in `bq_setup.py`.
- **Budget/revenue as FLOAT64**: Ensure `replicate_mysql.py` uses the explicit
  BQ schema with INT64, not autodetect.
- **Postgres lowercase columns**: `EXTERNAL_QUERY` returns lowercase column
  names regardless of DDL casing. This is expected Postgres behavior.

---

## Files

```
src/bq_setup.py           Datasets + connection + IAM + authorized views
src/replicate_mysql.py     Aiven MySQL → raw_registry (batch replicate)
src/load_csv_bq.py         CSVs → raw_files (batch load)
src/build_mart.py          Executes bq_mart.sql + bq_descriptions.sql
src/verify_bq.py           15 verification gates (B1–B15)
src/bq_pipeline.py         Entry point, stops on first failure
sql/bq_mart.sql            5 mart view definitions
sql/bq_descriptions.sql    View and column descriptions for ADK agent
sql/agent_demo_queries.sql 8 escalating demo queries
```

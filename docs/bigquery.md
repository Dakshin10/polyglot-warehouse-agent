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
         │ (replicate_mysql)            │ (federated, live)
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

---

## Execution

```bash
pwa warehouse run
```

Pipeline stages:
1. **Setup** (`pwa.warehouse.setup`): Create 4 datasets, BigQuery connection to Cloud SQL, grant IAM, verify connection, create federated view, setup agent SA, authorize mart views
2. **Replicate MySQL** (`pwa.ingest.replicate`): Aiven MySQL → `raw_registry.movie` (WRITE_TRUNCATE)
3. **Load CSVs** (`pwa.ingest.csv_to_bq`): CSVs → `raw_files.movie_keywords` and `raw_files.movie_ratings_agg`
4. **Build Mart** (`pwa.warehouse.mart`): Execute `views.sql` (5 views) then `descriptions.sql` (all descriptions)
5. **Verify** (`pwa.gates.warehouse`): 15 verification gates

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

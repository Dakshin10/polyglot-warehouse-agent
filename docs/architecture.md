# Polyglot Warehouse Agent — Architecture

## Layer Overview

```
                          [ Kaggle API ]
                                │
                         [ data/raw/ ]
                                │
                   ┌────────────┴────────────┐
                   ▼                         ▼
             [ Aiven MySQL ]      [ Cloud SQL Postgres ]
            (movie_registry)          (movie_credits)
                   │                         │
            replicated batch         federated live query
                   │                         │
                   ▼                         ▼
            [ raw_registry ]          [ raw_credits ]
                   │                         │
                   └────────────┬────────────┘
                                ▼
                       [ BigQuery Mart ]
                    (mart.v_movie_full)
                                │
                                ▼
                   [ ADK Warehouse Agent ]
```

### 1. Source Layer
- **Aiven MySQL**: Managed cloud MySQL instance hosting film financials (`movie` table, 1,000 rows).
- **Cloud SQL PostgreSQL**: Managed GCP PostgreSQL instance hosting credit data (`movie_credits` table, 1,000 rows).
- **Raw CSV Files**: Keywords (`movie_keywords.csv`) and MovieLens ratings (`movie_ratings_agg.csv`).

### 2. Why Replication vs. Federation?
- **Aiven MySQL is Replicated**: Aiven MySQL is hosted outside GCP. Batch replication into BigQuery `raw_registry` isolates query load and ensures ultra-fast analytical execution.
- **Cloud SQL PostgreSQL is Federated**: Cloud SQL resides in the same GCP project (`salitsteel-502008`) and region (`europe-west1`). A BigQuery Cloud SQL Connection enables live, zero-copy federation via `EXTERNAL_QUERY`.

### 3. Cross-Engine Foreign Key Design
- Across Aiven MySQL and Cloud SQL PostgreSQL, `movie_id` serves as the logical join key.
- The cross-engine foreign key is **deliberately unenforced at the DDL level** across distinct database management systems. Referential integrity is continuously validated at query runtime via `mart.v_integrity_exceptions`.

### 4. Mart Layer Governance
- All downstream consumers (including the Google Agentic SDK ADK Agent) query **only** the `mart` dataset (`mart.v_movie_full`).
- Raw datasets (`raw_registry`, `raw_credits`, `raw_files`) are protected by IAM dataset permissions and authorized views.

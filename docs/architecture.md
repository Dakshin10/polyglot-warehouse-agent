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

## Repository Layout

Maximum depth of two. One package level under `src/`, no subpackages: every
module sits exactly one level deep and is named by subsystem, so related files
sort together.

```
polyglot-warehouse-agent/
├── README.md  pyproject.toml  Makefile  .env.example  .gitignore
├── src/pwa/
│   ├── settings.py          the only module that reads the environment
│   ├── connections.py       MySQL / Postgres / BigQuery factories, no fallback
│   ├── logging_setup.py     structured logging with credential redaction
│   ├── sql_files.py         resolves sql/ against the repository root
│   ├── kaggle_download.py   movie_transform.py   source_db_load.py
│   ├── bigquery_setup.py    bigquery_replicate.py
│   ├── bigquery_load_csv.py bigquery_mart.py
│   ├── gates_source.py      gates 1-13, run at pipeline time
│   ├── gates_bigquery.py    gates B1-B15, run at pipeline time
│   ├── gates_runner.py      shared gate scaffolding (no SKIP status)
│   ├── run_source.py        run_bigquery.py    audit.py
│   └── cli.py               the `pwa` console script
├── sql/    mysql_movie_ddl, postgres_credits_ddl, mart_views,
│           mart_descriptions, example_cross_db, example_agent_demo
├── tests/  pytest: unit tests plus @pytest.mark.integration
├── docs/   architecture.md  bigquery.md  runbook.md  audit_report.md
├── certs/  gitignored - Aiven service CA
└── data/   gitignored - raw Kaggle cache and generated CSVs
```

### Verification gates are not tests

`gates_source.py` and `gates_bigquery.py` assert data quality against live
cloud resources at pipeline runtime and block on failure, so they live in
`src/` and run as part of `pwa source run` / `pwa warehouse run`. `tests/` is
pytest: unit tests of pure logic plus integration tests that are deselected by
default. A gate that only runs when someone remembers to run pytest is not a
gate.

`gates_runner.GateResult` has no SKIP status. A gate that cannot execute
returns `passed=False` with `detail="CANNOT VERIFY: <error>"`, which is what
keeps an unverifiable gate from reading as a pass. Mutating gates (B14) carry
`mutating=True` and restore their change in a `finally` block.

# Movie-to-Enterprise Migration Audit

**Polyglot Warehouse Agent — Milestone 1 Repository Audit**
**Date:** 2026-09-13
**Status:** Completed — Pre-migration snapshot

---

## 1. Executive Summary

The existing repository was built entirely around a movie analytics prototype
dataset (`rounakbanik/the-movies-dataset`). The migration objective is to
transform the project into **Nexora Technologies' enterprise data integration
and warehouse foundation platform**, using AdventureWorks 2022 and the Olist
e-commerce datasets as primary sources. The movie dataset and all
movie-specific code will be removed.

This document is a complete inventory of the repository before any deletions
are made.

---

## 2. Current Architecture

### 2.1 Source Systems

| Source | Type | Technology | Movie-Specific? |
|---|---|---|---|
| `rounakbanik/the-movies-dataset` | Kaggle CSV | File download | **YES — DELETE** |
| Aiven MySQL (`movie_registry.movie`) | Cloud MySQL | Managed DB | **YES — REPLACE** |
| Cloud SQL PostgreSQL (`movie_credits.movie_credits`) | Cloud PG | Managed DB | **YES — REPLACE** |

### 2.2 BigQuery Dataset Structure

| Dataset | Purpose | Movie-Specific? |
|---|---|---|
| `raw_registry` | MySQL replicated movie table | **YES — REPLACE** |
| `raw_credits` | PostgreSQL federated credits | **YES — REPLACE** |
| `raw_files` | CSV keywords + ratings | **YES — REPLACE** |
| `mart` | Mart views (v_movie_*) | **YES — REPLACE** |
| `rollup` | Materialized rollup tables | **YES — REPLACE** |

### 2.3 Pipeline Flow

```
Kaggle (rounakbanik/the-movies-dataset)
        ↓
kaggle_download.py         [REPLACE — point to new datasets]
        ↓
movie_transform.py         [DELETE — movie-specific transform]
        ↓
source_db_load.py          [REPLACE — new DDL and load logic]
        ↓
Aiven MySQL (movie)        [REPLACE — new table/schema]
Cloud SQL PG (movie_credits) [REPLACE — new table/schema]
        ↓
bigquery_setup.py          [PARTIAL REPLACE — generic infra, movie SQL to remove]
bigquery_mart.py           [REPLACE — mart views now enterprise-domain]
bigquery_replicate.py      [PRESERVE — generic CSV load, rename target tables]
bigquery_load_csv.py       [PRESERVE — generic BigQuery load utility]
        ↓
gates_source.py            [REPLACE — movie-specific gate assertions]
gates_bigquery.py          [REPLACE — movie-specific BigQuery gates]
        ↓
mart views: v_movie_*      [DELETE — replace with enterprise views]
rollup tables              [REPLACE — movie rollups → enterprise rollups]
```

---

## 3. File-by-File Inventory

### 3.1 Files to DELETE

These files contain exclusively movie-domain logic and have no reusable generic
infrastructure content.

| File | Reason |
|---|---|
| `src/pwa/preprocessing/movie_transform.py` | 365 lines of movie-specific ETL: genres, credits, cast, keywords, ratings, ROI |
| `sql/mysql_movie_ddl.sql` | DDL for `movie` table (budget_usd, revenue_usd, runtime_min, title, primary_genre) |
| `sql/postgres_credits_ddl.sql` | DDL for `movie_credits` table (director_name, lead_actor_name, cast_size) |
| `sql/mart_views.sql` | v_movie, v_movie_credits, v_movie_full, v_movie_keywords, v_integrity_exceptions |
| `sql/mart_descriptions.sql` | Column descriptions for movie mart views |
| `sql/example_agent_demo.sql` | Demo SQL: genre distribution, director ROI, cast size, movie keywords |
| `sql/example_cross_db.sql` | Cross-DB join examples: MySQL × PG director analytics |
| `data/raw/credits.csv` | Raw Kaggle TMDB credits (movie cast/crew JSON) |
| `data/raw/keywords.csv` | Raw Kaggle TMDB keywords |
| `data/raw/links.csv` | Raw Kaggle MovieLens ↔ TMDB links |
| `data/raw/links_small.csv` | Smaller links subset |
| `data/raw/movies_metadata.csv` | Raw Kaggle TMDB movie metadata |
| `data/raw/ratings.csv` | Raw Kaggle MovieLens ratings (709 MB) |
| `data/raw/ratings_small.csv` | Smaller ratings subset |
| `data/out/movie_keywords.csv` | Processed movie keywords output |
| `data/out/movie_ratings_agg.csv` | Aggregated movie ratings output |
| `data/out/selected_movie_ids.csv` | Selected 1000 movie IDs |
| `data/out/.selected_movie_ids_sha256` | SHA-256 pin for selected_movie_ids |
| `tests/fixtures/credits_sample.csv` | Sample movie credits fixture (TMDB cast JSON) |
| `tests/fixtures/movies_metadata_sample.csv` | Sample movie metadata fixture |
| `tests/fixtures/selected_movie_ids.sha256` | SHA-256 pin in fixture dir |
| `src/pwa/eval/golden_set.json` | 20 golden NLP questions all movie-domain |
| `src/pwa/eval/benchmark_queries.json` | 50 benchmark queries all movie-domain |

### 3.2 Files to REPLACE (movie-specific, but logic pattern is reusable)

These files contain reusable patterns but the specific content is movie-domain
and must be rewritten for the enterprise domain.

| File | What to Replace |
|---|---|
| `src/pwa/preprocessing/kaggle_download.py` | Dataset slug `rounakbanik/the-movies-dataset` → `tituspr/adventureworks2022-excel-format`, `olistbr/brazilian-ecommerce`, `olistbr/marketing-funnel-olist`; expected file list |
| `src/pwa/preprocessing/bigquery_setup.py` | `create_federated_view()` creates `movie_credits` view; `authorize_mart_views()` references `v_movie*`; dataset names `raw_registry`, `raw_credits`, `raw_files`, `mart` → enterprise datasets |
| `src/pwa/preprocessing/source_db_load.py` | Loads `movie` → MySQL and `movie_credits` → PG; new DDL file references; new table names |
| `src/pwa/preprocessing/bigquery_mart.py` | Mart view creation — all view SQL is movie-specific |
| `src/pwa/gates_source.py` | All 13 gates check `movie` / `movie_credits` row counts, director_name nulls, budget/revenue > 0, cross-engine join with ROI |
| `src/pwa/gates_bigquery.py` | All 15 gates check v_movie_* counts, mart view names, director_name nulls, GATE B13 selected_movie_ids SHA, GATE B15 top directors by ROI |
| `src/pwa/rollups.py` | Rollup tables: `avg_roi_by_director`, `avg_cast_size_by_revenue_threshold`, `top_grossing_movies`, `avg_roi_by_genre` — all movie-specific |
| `src/pwa/agent/pipeline/examples/sql_fewshot.json` | All 15 few-shot examples reference movie tables, director ROI, movie revenue |
| `src/pwa/agent/root_agent.py` | May contain movie-specific system prompt / domain references |
| `src/pwa/agent/template_router.py` | Fast-path rollup router routes `avg_roi_by_director`, `avg_cast_size_by_threshold`, `top_grossing_movies`, `avg_roi_by_genre` — all movie rollups |
| `src/pwa/settings.py` | DB names `movie_registry`, `movie_credits`; BQ dataset vars `bq_ds_registry`, `bq_ds_credits`, `bq_ds_files`, `bq_ds_mart`; connection_id `movie-credits-conn` |
| `.env.example` | `MYSQL_DB=movie_registry`, `PG_DB=movie_credits`, `BQ_CONNECTION_ID=movie-credits-conn`, `BQ_DS_REGISTRY=raw_registry`, `BQ_DS_CREDITS=raw_credits`, `BQ_DS_FILES=raw_files` |
| `README.md` | Entire description is movie analytics; all commands reference movie queries; architecture section is movie-specific |
| `docs/architecture.md` | Architecture document describes movie-domain system |
| `docs/bigquery.md` | BigQuery warehouse guide is movie-domain |
| `docs/runbook.md` | Runbook references movie data operations |
| `docs/audit_report.md` | Audit report is movie-data reconciliation |
| `app.py` | Streamlit UI (query interface) — may contain movie-specific prompt examples or help text |

### 3.3 Files to MODIFY (partially movie-specific)

These files have generic infrastructure mixed with movie-specific details that
need surgical replacement.

| File | Movie-Specific Parts | Generic Parts to Preserve |
|---|---|---|
| `src/pwa/audit.py` | References to movie tables / paths in audit checks | Generic connectivity audit logic, path scanner |
| `src/pwa/connections.py` | Connection logic for MySQL/PG — generic, but DB names are movie-specific | Engine factories, SSL handling, BQ client |
| `src/pwa/agent/schema_cache.py` | Schema cache may be keyed on movie mart view names | Generic BigQuery INFORMATION_SCHEMA caching |
| `src/pwa/agent/bq_tools.py` | Table references in tools — generic | BQ query execution tool |
| `src/pwa/agent/guardrails.py` | May reference movie tables in allow-lists | Read-only enforcement, cost guardrails |
| `tests/test_pipeline.py` | Tests reference movie data files and row counts | Pipeline execution test structure |
| `tests/test_transform_clean.py` | Tests movie_transform functions | Test infrastructure |
| `tests/test_transform_select.py` | Tests movie selection logic | Test structure |
| `tests/test_settings.py` | Tests movie-specific defaults (`movie_registry`, `movie_credits`) | Settings validation test structure |
| `tests/test_bq_tools.py` | May reference v_movie mart views | BQ tool test infra |
| `tests/test_template_router.py` | Tests movie-specific rollup routing | Template router test framework |
| `tests/conftest.py` | May mock movie tables | Fixture configuration |
| `pyproject.toml` | Project description may reference movies | Package configuration, dependencies |
| `.gitignore` | May include movie data file patterns | Generic patterns |
| `Makefile` | Commands may reference movie pipelines | Generic make targets |

### 3.4 Files to PRESERVE (generic, zero movie-domain content)

These files are fully generic infrastructure with no movie-domain content.
They require NO changes (unless the migration introduces new generic patterns).

| File | Content |
|---|---|
| `src/pwa/logging_setup.py` | Generic structured logging setup |
| `src/pwa/gates_runner.py` | Generic gate runner: `GateResult`, `run_gates`, `cannot_verify` |
| `src/pwa/sql_files.py` | Generic SQL file reader |
| `src/pwa/preprocessing/__init__.py` | Package exports |
| `src/pwa/preprocessing/bigquery_load_csv.py` | Generic BigQuery CSV loader |
| `src/pwa/preprocessing/bigquery_replicate.py` | Generic MySQL → BigQuery replication |
| `src/pwa/agent/pipeline/orchestrator.py` | NLP query orchestration — generic pipeline |
| `src/pwa/agent/pipeline/answer_agent.py` | Answer synthesis agent — generic |
| `src/pwa/agent/pipeline/exec_agent.py` | BQ execution + dry-run validation — generic |
| `src/pwa/agent/pipeline/fallback.py` | Fallback logic — generic |
| `src/pwa/agent/pipeline/__init__.py` | Package exports |
| `src/pwa/agent/models.py` | LLM model selection — generic |
| `src/pwa/agent/semantic_cache.py` | Semantic cache for queries — generic |
| `src/pwa/ui/styles.py` | UI design system — generic |
| `src/pwa/ui/viz_recommendation.py` | Visualization recommendations — generic |
| `src/pwa/ui/viz_router.py` | Chart type routing — generic |
| `src/pwa/ui/components/*.py` | UI panels — generic |
| `src/pwa/ui/pdf_export.py` | PDF export — generic |
| `src/pwa/eval/benchmark.py` | Benchmark harness — generic (queries will be replaced) |
| `src/pwa/eval/performance.py` | Performance profiler — generic |
| `src/pwa/eval/run_eval.py` | Eval runner — generic |
| `tests/test_ast_sql_validation.py` | SQL AST validation tests — generic |
| `tests/test_benchmark_and_perf.py` | Benchmark test harness — generic |
| `tests/test_cli_query.py` | CLI query tests — generic (test content TBD) |
| `tests/test_connections.py` | Connection tests — generic |
| `tests/test_guardrails.py` | Guardrails tests — generic |
| `tests/test_guardrails_provenance.py` | Provenance guardrails — generic |
| `tests/test_models_and_fallback.py` | Model fallback tests — generic |
| `tests/test_report_view.py` | Report view tests — generic |
| `tests/test_retry_logic.py` | Retry logic tests — generic |
| `tests/test_root_agent.py` | Root agent tests — generic |
| `tests/test_schema_cache.py` | Schema cache tests — generic |
| `tests/test_semantic_cache.py` | Semantic cache tests — generic |
| `tests/test_ui_imports.py` | UI import tests — generic |
| `tests/test_viz_recommendation.py` | Viz recommendation tests — generic |
| `tests/test_viz_router.py` | Viz router tests — generic |
| `.streamlit/config.toml` | Streamlit configuration — generic |
| `certs/` | TLS certificate storage — generic |
| `assets/` | Image assets — generic |

---

## 4. Movie-Domain Terminology Inventory

The following terms appear in the codebase in movie-specific contexts.
Terms marked **[GENERIC]** appear in both movie and generic infrastructure —
must be reviewed on a per-occurrence basis before removal.

| Term | Occurrences | Decision |
|---|---|---|
| `movie` | ~200+ | DELETE where table/column name; PRESERVE where part of generic narrative |
| `movie_id` | ~80+ | DELETE — movie PK |
| `movie_credits` | ~30+ | DELETE |
| `movie_registry` | ~15+ | DELETE |
| `movie_keywords` | ~15+ | DELETE |
| `movie_ratings_agg` | ~10+ | DELETE |
| `movies_metadata` | ~10+ | DELETE |
| `director` | ~40+ | DELETE |
| `director_name` | ~25+ | DELETE |
| `cast` | ~20+ | DELETE where movie-specific |
| `cast_size` | ~15+ | DELETE |
| `crew_size` | ~10+ | DELETE |
| `actor` | ~20+ | DELETE |
| `lead_actor_name` | ~10+ | DELETE |
| `genre` | ~30+ | DELETE (movie genre) |
| `primary_genre` | ~20+ | DELETE |
| `budget_usd` | ~20+ | DELETE (movie budget) |
| `revenue_usd` | ~25+ | DELETE |
| `roi` | ~25+ | DELETE (movie ROI) |
| `runtime_min` | ~10+ | DELETE |
| `vote_average` | ~10+ | DELETE |
| `vote_count` | ~10+ | DELETE |
| `imdb` | ~5+ | DELETE |
| `tmdb` | ~5+ | DELETE |
| `movielens` | ~5+ | DELETE |
| `rounakbanik` | ~5+ | DELETE (Kaggle dataset slug) |
| `Avatar` | ~5+ | DELETE (specific movie reference) |
| `Inception` | ~3+ | DELETE |
| `James Cameron` | ~2+ | DELETE |
| `Christopher Nolan` | ~3+ | DELETE |
| `Leonardo DiCaprio` | ~2+ | DELETE |
| `title` | ~20+ | **[GENERIC]** — review each; SQL column `title` in movie context → DELETE; generic word → PRESERVE |
| `producer_name` | ~10+ | DELETE |
| `production_country` | ~5+ | DELETE |
| `popularity` | ~10+ | DELETE (TMDB popularity) |

---

## 5. Current BigQuery Dataset Architecture

```
GCP Project
├── raw_registry          ← MySQL movie table (batch replicated)
│   └── movie             ← 1,000 rows, financial/metadata
├── raw_credits           ← PG movie_credits (EXTERNAL_QUERY federated)
│   └── movie_credits     ← 1,000 rows, director/cast
├── raw_files             ← CSV batch load
│   ├── movie_keywords    ← ~11,800 rows (exploded tags)
│   └── movie_ratings_agg ← 1,000 rows (aggregated ratings)
├── mart                  ← Consumer-facing mart views
│   ├── v_movie           ← from raw_registry.movie
│   ├── v_movie_credits   ← from raw_credits.movie_credits
│   ├── v_movie_full      ← cross-engine join
│   ├── v_movie_keywords  ← from raw_files.movie_keywords
│   └── v_integrity_exceptions ← referential integrity monitor
└── rollup                ← Materialized rollup tables
    ├── avg_roi_by_director
    ├── avg_cast_size_by_revenue_threshold
    ├── top_grossing_movies
    └── avg_roi_by_genre
```

---

## 6. Target Enterprise BigQuery Architecture

```
GCP Project (Nexora Technologies)
│
├── RAW LAYER
│   ├── raw_adventureworks        ← AdventureWorks 2022 source tables
│   │   ├── sales_order_header
│   │   ├── sales_order_detail
│   │   ├── product
│   │   ├── product_category
│   │   ├── product_subcategory
│   │   ├── customer
│   │   ├── person
│   │   ├── employee
│   │   ├── department
│   │   ├── vendor
│   │   ├── purchase_order_header
│   │   └── purchase_order_detail
│   ├── raw_olist                 ← Olist e-commerce source tables
│   │   ├── olist_orders
│   │   ├── olist_customers
│   │   ├── olist_order_items
│   │   ├── olist_order_payments
│   │   ├── olist_order_reviews
│   │   ├── olist_products
│   │   ├── olist_sellers
│   │   ├── olist_geolocation
│   │   └── olist_product_category_translation
│   └── raw_olist_marketing       ← Olist Marketing Funnel
│       ├── olist_marketing_qualified_leads
│       └── olist_closed_deals
│
├── STAGING LAYER
│   ├── staging_enterprise        ← Normalized AdventureWorks data
│   └── staging_marketplace       ← Normalized Olist data
│
├── CURATED LAYER (canonical enterprise model)
│   ├── curated_enterprise
│   │   ├── dim_employee
│   │   ├── dim_department
│   │   ├── dim_customer
│   │   ├── dim_product
│   │   ├── dim_product_category
│   │   ├── dim_supplier
│   │   ├── fact_sales_order
│   │   ├── fact_sales_order_item
│   │   ├── fact_purchase_order
│   │   └── fact_purchase_order_item
│   └── curated_marketplace
│       ├── dim_marketplace_customer
│       ├── dim_marketplace_seller
│       ├── dim_marketplace_product
│       ├── fact_marketplace_order
│       ├── fact_marketplace_order_item
│       ├── fact_marketplace_payment
│       └── fact_marketing_lead
│
└── CONTROL PLANE
    └── pwa_metadata
        ├── pwa_sources
        ├── pwa_source_tables
        ├── pwa_pipeline_runs
        ├── pwa_watermarks
        ├── pwa_schema_versions
        ├── pwa_quality_results
        └── pwa_audit_log
```

---

## 7. Current CLI Architecture

```
pwa config              → validates Settings (movie DB names in defaults)
pwa audit               → read-only audit (some movie-specific paths)
pwa source run          → download kaggle → movie_transform → source_db_load
pwa source verify       → gates_source (13 movie-specific gates)
pwa warehouse run       → bigquery_setup → bigquery_mart → bigquery_gates
pwa warehouse verify    → gates_bigquery (15 movie-specific gates)
pwa all                 → source run → warehouse run
pwa refresh-rollups     → movie rollup tables (director ROI, genre ROI)
pwa query               → NLP agent (currently movie-domain examples)
pwa eval                → golden_set.json (all movie questions)
pwa benchmark           → benchmark_queries.json (all movie questions)
pwa perf                → performance profiler
```

**Target CLI additions** (preserve all existing commands, add new enterprise ones):
```
pwa source list         → list registered source systems
pwa source inspect <name> → inspect source schema/config
pwa source test <name>  → test source connectivity
pwa source discover <name> → run schema discovery
pwa ingest run <name>   → run ingestion for one source
pwa ingest status       → show ingestion run history
pwa quality run <name>  → run quality gates for source
pwa warehouse validate  → validate warehouse structure
pwa audit --days N      → audit N-day window
```

---

## 8. Current Source Gateway / Settings Architecture

Settings are loaded from `.env` via `src/pwa/settings.py`.

Movie-specific defaults that must change:

| Setting | Current Default | New Default |
|---|---|---|
| `MYSQL_DB` | `movie_registry` | `nexora_erp` (or remove if MySQL not used) |
| `PG_DB` | `movie_credits` | `nexora_marketplace` (or remove if PG not used) |
| `BQ_CONNECTION_ID` | `movie-credits-conn` | `nexora-source-conn` |
| `BQ_DS_REGISTRY` | `raw_registry` | `raw_adventureworks` |
| `BQ_DS_CREDITS` | `raw_credits` | `raw_olist` |
| `BQ_DS_FILES` | `raw_files` | `raw_olist_marketing` |
| `BQ_DS_MART` | `mart` | `curated_enterprise` |

New settings to add:
```
BQ_DS_RAW_AW=raw_adventureworks
BQ_DS_RAW_OLIST=raw_olist
BQ_DS_RAW_MARKETING=raw_olist_marketing
BQ_DS_STAGING_ENT=staging_enterprise
BQ_DS_STAGING_MKT=staging_marketplace
BQ_DS_CURATED_ENT=curated_enterprise
BQ_DS_CURATED_MKT=curated_marketplace
BQ_DS_METADATA=pwa_metadata
```

---

## 9. Key Infrastructure Invariants to Preserve

These components are the PWA's core value and must be preserved and enhanced:

1. **`gates_runner.py`** — `GateResult`, `run_gates`, `cannot_verify` — generic quality gate runner
2. **`logging_setup.py`** — structured logging
3. **`connections.py`** — engine factories (BigQuery, MySQL, PostgreSQL)
4. **`sql_files.py`** — SQL file loader
5. **`bigquery_load_csv.py`** — generic BQ CSV load utility
6. **`bigquery_replicate.py`** — generic MySQL → BQ table replication
7. **Agent pipeline** — orchestrator, schema_agent, sql_agent, exec_agent, answer_agent — all generic
8. **UI components** — all generic, zero movie-domain content
9. **Eval harness** — generic framework, only question files need replacement
10. **Retry / error handling** — generic throughout pipeline

---

## 10. Migration Milestones

| Milestone | Status |
|---|---|
| M1: Repository Audit | ✅ COMPLETE (this document) |
| M2: Dataset Acquisition (AdventureWorks, Olist, Olist Marketing) | ⬜ PENDING |
| M3: Movie Removal (delete/migrate movie artifacts) | ⬜ PENDING |
| M4: Source Registry (register new sources) | ⬜ PENDING |
| M5: Raw Ingestion (BigQuery raw layer) | ⬜ PENDING |
| M6: Staging (normalize schemas and types) | ⬜ PENDING |
| M7: Canonical Enterprise Model (Nexora mappings) | ⬜ PENDING |
| M8: Curated Layer (trusted tables) | ⬜ PENDING |
| M9: Quality / Reconciliation | ⬜ PENDING |
| M10: Documentation | ⬜ PENDING |

---

## 11. Risk Notes

1. **Aiven MySQL and Cloud SQL PostgreSQL** — the existing platform uses real
   cloud managed databases. The migration must decide whether to re-use these
   for the new domain or whether new database instances are required. This
   audit recommends **replacing the database schemas** (new tables, same engines)
   rather than provisioning new cloud DB instances, since the connection
   infrastructure (SSL, Cloud SQL connector) is already working.

2. **BigQuery Federation** — the existing `EXTERNAL_QUERY` federation to Cloud
   SQL PostgreSQL is movie-specific (`movie_credits`). The new platform will
   use BigQuery native tables (CSV load and batch replication) as the primary
   raw layer, with federation only if a live-query source is genuinely required.

3. **Kaggle dataset sizes** — the Olist dataset is approximately 100,000 orders
   across 9 CSV files (~35 MB total). AdventureWorks Excel files are moderate
   size. Neither requires streaming ingestion — batch snapshot loading is correct.

4. **Kaggle credentials** — the existing `KAGGLE_USERNAME` / `KAGGLE_KEY` env
   vars are already supported in `settings.py`. These will be reused.

5. **License compliance** — Olist uses CC BY-NC-SA 4.0. AdventureWorks is
   Microsoft's public sample database. Northwind is public domain (if used).
   License metadata must be recorded before any data is incorporated.

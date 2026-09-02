# Audit Report — `polyglot-warehouse-agent`

**Read-only audit run:** 2026-09-02T15:34:49Z (UTC)
**Repository state audited:** commit `4e5ce92`, branch `main`, working tree clean
**Auditor:** automated audit pass (`pwa audit`), all probes read-only

Every figure below was read from the live database or the filesystem at the time
stamped above. No cloud resource was created, altered or deleted during the
read-only pass. Gate B14 (federation liveness) is the only mutating check in the
codebase; it was exercised once as part of the pre-change baseline and restored
its own row.

---

## Executive summary

| Area | Verdict |
|---|---|
| Cloud connections (MySQL, Postgres/connector, BigQuery, federation) | **All live and green** |
| Record inventory | **Complete** — 11 cloud objects + 3 local CSVs, all accounted for |
| Cross-store reconciliation (Parts 5.1–5.6) | **Exact** — symmetric difference 0 in every direction, BigQuery agrees with source of record |
| 28 verification gates | **28/28 PASS**, exit 0 (baseline before any change) |
| Data of record existing only locally | **None** — nothing at risk |
| SQLite residue | **Present** — two live SQLite files with 1,000 rows each, plus 9 code branches |
| Claims contradicted by this audit | **4** (see *Contradictions* below) |

---

## Contradictions with what was previously reported as built

These are stated explicitly rather than quietly fixed, as required.

1. **`gates_runner.py` was reported as built and adopted; it is dead code.**
   `src/pwa/gates/runner.py` defines `GateResult` and `run_gates` exactly as
   specified — and **nothing imports it**. Both gate suites still use the older
   ad-hoc `results.append((id, desc, detail, bool))` tuple lists with their own
   copy-pasted print/exit scaffolding. Grep for `run_gates|GateResult` outside
   the file itself returns zero hits. The dataclass exists; the refactor it was
   supposed to enable does not.

2. **Config validation rule "`MYSQL_SSL_CA` exists on disk" was reported as
   implemented; it is not, and it is currently failing silently.**
   `config.py` only calls `Path(...).resolve()` — it never checks existence.
   `certs/` **is empty**: `certs/ca.pem` does not exist on this machine. `pwa
   config check` still reports *"Settings validation: PASSED (all rules
   satisfied)"*. `get_mysql_engine()` then falls through to
   `connect_args["ssl"] = {"check_hostname": False}`, i.e. TLS **without CA
   verification and without hostname verification**. The connection is still
   encrypted (`Ssl_cipher = TLS_AES_256_GCM_SHA384`, confirmed live), so this is
   not an unencrypted-link finding — it is an unauthenticated-peer finding, and
   the validator that was supposed to catch it reported green.

3. **Gate B11 "Agent SA can query `mart.v_movie_full`" does not use the agent
   service account.** It reuses the same `client` built from the caller's own
   ADC and asserts `COUNT(*) == 1000`. It therefore proves the *developer* can
   read the view, and would pass identically if the agent SA had no access at
   all. When impersonation is actually attempted it **fails**:
   `iamcredentials.googleapis.com` is disabled on project `salitsteel-502008`.
   Enabling it would create a new cloud resource, which this audit is forbidden
   from doing, so the true state of the agent SA's read path is **unverified**.
   B11 is a false green.

4. **The SQLite fallback was reported as removed; the residue proves it ran and
   the code path is still present.**
   `data/out/mysql_movie.db` (131,072 bytes) and
   `data/out/postgres_movie_credits.db` (106,496 bytes) are genuine
   `SQLite format 3` files containing `movie` = **1,000 rows** and
   `movie_credits` = **1,000 rows** respectively. Nine live code branches still
   test `== "sqlite"` / `!= "sqlite"`, and `REQUIRE_CLOUD_DB` is still a
   defaultable env flag (`default "false"`) gating gates 0A/0B — exactly the
   flag-shaped failure mode called out as having already produced green gates
   against a local file once.

Secondary discrepancy: the raw Kaggle cache is documented as ~238 MB. It is
**901 MB** — `ratings.csv` (709,550,327 bytes) is downloaded by
`unzip=True` but is not in `EXPECTED_FILES` and is never read by the pipeline
(the pipeline uses `ratings_small.csv`).

---

## Part 1 — Code inventory

All 27 modules import cleanly from a fresh interpreter (`walk_packages` +
`import_module`, 27/27 OK).

| Path | Lines | Imported by | Reachable from an entry point |
|---|---|---|---|
| `src/__init__.py` | 1 | — | no (see note) |
| `src/pwa/__init__.py` | 3 | package marker | yes |
| `src/pwa/cli.py` | 104 | console script `pwa` | **yes (entry point)** |
| `src/pwa/config.py` | 185 | cli, db.mysql, db.postgres, 2 tests | yes |
| `src/pwa/logging.py` | 48 | cli | yes |
| `src/pwa/db/__init__.py` | 5 | 4 src modules, 3 tests | yes |
| `src/pwa/db/mysql.py` | 59 | db/__init__, db.postgres | yes |
| `src/pwa/db/postgres.py` | 83 | db/__init__ | yes |
| `src/pwa/db/bigquery.py` | 14 | db/__init__ | **tests only** — no src caller |
| `src/pwa/gates/__init__.py` | 4 | cli, pipelines | yes |
| `src/pwa/gates/runner.py` | 60 | **nothing** | **NO — dead code** |
| `src/pwa/gates/source.py` | 184 | gates/__init__ | yes |
| `src/pwa/gates/warehouse.py` | 343 | gates/__init__ | yes |
| `src/pwa/ingest/__init__.py` | 5 | pipelines | yes |
| `src/pwa/ingest/kaggle.py` | 83 | ingest/__init__ | yes |
| `src/pwa/ingest/replicate.py` | 80 | ingest/__init__ | yes |
| `src/pwa/ingest/csv_to_bq.py` | 82 | ingest/__init__ | yes |
| `src/pwa/load/__init__.py` | 3 | pipelines.source | yes |
| `src/pwa/load/source_db.py` | 161 | load/__init__ | yes |
| `src/pwa/pipelines/__init__.py` | 4 | cli | yes |
| `src/pwa/pipelines/source.py` | 35 | pipelines/__init__ | yes |
| `src/pwa/pipelines/warehouse.py` | 37 | pipelines/__init__ | yes |
| `src/pwa/transform/__init__.py` | 11 | load.source_db, pipelines.source | yes |
| `src/pwa/transform/build.py` | 5 | **nothing** | **NO — dead code** |
| `src/pwa/transform/clean.py` | 73 | transform.select, 2 tests | yes |
| `src/pwa/transform/select.py` | 299 | transform/__init__, transform.build | yes |
| `src/pwa/warehouse/__init__.py` | 4 | pipelines.warehouse | yes |
| `src/pwa/warehouse/setup.py` | 335 | warehouse/__init__, warehouse.mart | yes |
| `src/pwa/warehouse/mart.py` | 123 | warehouse/__init__ | yes |
| `src/pwa/sql/ddl/mysql_movie.sql` | 22 | `source_db_load` via `importlib.resources` | yes |
| `src/pwa/sql/ddl/postgres_movie_credits.sql` | 19 | same | yes |
| `src/pwa/sql/mart/views.sql` | 94 | `bigquery_mart` | yes |
| `src/pwa/sql/mart/descriptions.sql` | 224 | `bigquery_mart` | yes |
| `src/pwa/sql/examples/cross_db_queries.sql` | 94 | documentation only | no (reference material, intentional) |
| `src/pwa/sql/examples/agent_demo.sql` | 118 | documentation only | no (reference material, intentional) |

**Dead code:** `gates/runner.py` (60 lines), `transform/build.py` (5 lines, a
pure re-export left behind by the `transform.py` → `transform/` split).
`db/bigquery.py::get_bq_client` is reachable only from
`tests/integration/test_federation.py`; every production BigQuery call site
builds its own `bigquery.Client(...)` instead.

**Files left behind by an earlier rename:** `transform/build.py` (re-exports
`transform_and_select` from `select.py`; docstring says "Build functions for the
four output frames", it contains none) and `src/__init__.py` (a package marker
at the source root, where `[tool.setuptools.packages.find] where = ["src"]`
means `src` must *not* be a package).

**Duplicate logic**

| Duplication | Sites |
|---|---|
| Env reading (should be one module) | `config.py:64`, `db/bigquery.py:12-13`, `gates/source.py:22`, `gates/warehouse.py:21`, `ingest/csv_to_bq.py:59-61`, `ingest/kaggle.py:47-48`, `ingest/replicate.py:33-35`, `load/source_db.py:147`, `warehouse/mart.py:90-91`, `warehouse/setup.py:22` — **18 `os.getenv` / `os.environ` call sites in 10 files**, of which only one is in `config.py` |
| `load_dotenv()` re-invocation | **21 call sites** |
| BigQuery client construction | `db/bigquery.py:14`, `gates/warehouse.py:50`, `ingest/csv_to_bq.py:67`, `ingest/replicate.py:58`, `warehouse/mart.py:97`, `warehouse/setup.py:296` — 6 factories |
| Credential-masking helper | `db/mysql.py:11` (`mask_credentials`) and `logging.py:14` (`RedactingFilter.redact`) — same three regexes, two implementations |
| Gate scaffolding (collect → print table → exit) | `gates/source.py:159-180` and `gates/warehouse.py:318-339`, plus the unused third copy in `gates/runner.py` |
| `logging.basicConfig(...)` at import time | **11 modules** — every one of them overrides / races the `setup_logging()` the CLI installs, so the `RedactingFilter` is not guaranteed to be attached to the handler that actually emits |
| `_env(key, default)` helper | defined twice, identically: `gates/warehouse.py:20`, `warehouse/setup.py:21` |
| SQL-file location fallback chains | `load/source_db.py:30-35`, `load/source_db.py:92-97`, `warehouse/mart.py:49-54`, `warehouse/mart.py:101-108` |

**Bare / swallowing excepts** — 2 occurrences of the `except: pass` shape (there
are no truly bare `except:` clauses):

| File:line | Code | Consequence |
|---|---|---|
| `src/pwa/db/mysql.py:47-48` | `except Exception:` → `pass` | Swallows every failure of the `CREATE DATABASE IF NOT EXISTS` bootstrap, including auth failure and DNS failure. The masked-error path below never sees it. |
| `src/pwa/gates/warehouse.py:283-284` | `except Exception:` → `pass` | Swallows failure of Gate B14's **restore** UPDATE. If the restore fails, the audit trail is a `CANNOT VERIFY` with no mention that a Postgres row was left NULLed. |

Two further exception handlers silently discard information without `pass`:
`transform/clean.py:14` (increments a counter that is then imported *by value*
into `select.py`, so the "Total swallowed exceptions logged" line always prints
the stale value `0` — a real reporting bug) and `gates/source.py:121`
(mojibake check returns `False` on any error, conflating "cannot check" with
"corrupt").

**Occurrences of `sqlite` / `fallback` / local-file engine targets** — 14 in
`src/`:

| File:line | Occurrence |
|---|---|
| `config.py:66,69,70` | SQLite rejection validator (intended — keep) |
| `gates/source.py:22,31` | `REQUIRE_CLOUD_DB` flag gating gates 0A/0B |
| `gates/source.py:32,34` | `mysql_type != "sqlite"`, `pg_type != "sqlite"` |
| `gates/warehouse.py:225,227` | `if pg_type == "sqlite": … "CANNOT VERIFY: PG engine is SQLite fallback"` |
| `load/source_db.py:46-51` | rewrites MySQL DDL (`ENGINE=InnoDB` etc.) for SQLite |
| `load/source_db.py:72` | `insert_method = "multi" if mysql_type != "sqlite" else None` |
| `load/source_db.py:113-114` | rewrites `SERIAL PRIMARY KEY` → `INTEGER PRIMARY KEY AUTOINCREMENT` |
| `load/source_db.py:131` | `insert_method_pg = "multi" if pg_type != "sqlite" else None` |
| `load/source_db.py:148` | `if pg_type != "sqlite" and pg_bq_user:` |

No engine factory can *return* a SQLite engine any more — `get_mysql_engine` and
`get_pg_engine` both raise on failure. The nine consumer branches are therefore
already unreachable, but they are the scaffolding that a re-introduced fallback
would silently re-activate, and `REQUIRE_CLOUD_DB` still defaults to *off*.

---

## Part 2 — Configuration audit

Current state: `config.py` already validates rules 1, 2, 4, 5 and 6, and
already aggregates errors rather than failing on the first. Gaps found:

| Rule | State |
|---|---|
| 1. Required vars present and non-empty | **Partial.** Six vars are required (`MYSQL_HOST`, `MYSQL_PASSWORD`, `PG_PASSWORD`, `PG_INSTANCE_CONNECTION_NAME`, `PG_BQ_READER_PASSWORD`, `GCP_PROJECT`). `KAGGLE_USERNAME` / `KAGGLE_KEY` are declared fields but unvalidated, and both are **empty in the live `.env`** while `pwa config check` reports PASSED. |
| 2. `MYSQL_PORT` integer and ≠ 3306 | **Implemented.** Live value `26701`. |
| 3. `MYSQL_SSL_CA` exists on disk | **MISSING** — see Contradiction 2. |
| 4. `PG_INSTANCE_CONNECTION_NAME` matches `^[^:]+:[^:]+:[^:]+$` | **Implemented.** Live value `salitsteel-502008:europe-west1:test-database-agent`. |
| 5. `BQ_LOCATION` compatible with parsed region | **Implemented.** `europe-west1` → `EU`; live `BQ_LOCATION=EU` — compatible. Accepts the exact region or the covering multi-region, rejects otherwise naming both values. |
| 6. No `.db` / `.sqlite` / `sqlite://` target | **Implemented but over-broad** — it scans the *entire* `os.environ`, not project settings, so any unrelated OS variable whose value contains the substring `.db` fails the whole config with a message that quotes that variable's value. On this machine it happens not to fire. |

Redacted settings table (produced live by `pwa config check`; passwords and keys
render as `***`):

```
SETTING                        | VALUE
-------------------------------+--------------------------------------------------
kaggle_username                | (empty)
kaggle_key                     | ***
mysql_host                     | mysql-1a466403-minoridaks.k.aivencloud.com
mysql_port                     | 26701
mysql_user                     | avnadmin
mysql_password                 | ***
mysql_db                       | movie_registry
mysql_ssl_ca                   | <repo>\certs\ca.pem      <-- DOES NOT EXIST
pg_connect_mode                | connector
pg_host                        | (empty)
pg_port                        | 5432
pg_user                        | loader
pg_password                    | ***
pg_db                          | movie_credits
pg_instance_connection_name    | salitsteel-502008:europe-west1:test-database-agent
pg_bq_reader_user              | bqreader
pg_bq_reader_password          | ***
gcp_project                    | salitsteel-502008
bq_location                    | EU
bq_connection_id               | movie-credits-conn
bq_ds_registry                 | raw_registry
bq_ds_credits                  | raw_credits
bq_ds_files                    | raw_files
bq_ds_mart                     | mart
```

---

## Part 3 — Connection tests

| Target | Result | Latency | Identity / detail |
|---|---|---|---|
| Aiven MySQL | **PASS** | 3.2 s | `mysql-1a466403-minoridaks.k.aivencloud.com:26701` · version **8.4.8** · database `movie_registry` · `CURRENT_USER() = avnadmin@%` · `Ssl_cipher = TLS_AES_256_GCM_SHA384` (**SSL active**) · configured CA `certs/ca.pem` **absent on disk**, so peer identity is unverified |
| Cloud SQL Postgres — `connector` | **PASS** | 29.3 s (first connect) | instance `salitsteel-502008:europe-west1:test-database-agent` · **PostgreSQL 15.18** · database `movie_credits` · `current_user = loader` |
| Cloud SQL Postgres — `direct` | **NOT CONFIGURED** | — | `PG_HOST` is empty in `.env`. The direct path cannot be exercised at all, so the fallback is **unproven**. This is a configuration gap, not a code defect: `get_pg_engine()` raises `ValueError("PG_HOST not configured…")` before attempting a socket. |
| BigQuery | **PASS** | 4.5 s | project `salitsteel-502008`, location `EU`, `SELECT 1 → 1` · ADC = **user credentials** (not a service account) · ADC project `salitsteel-502008` · **quota project set** to `salitsteel-502008` |
| Federation (`EXTERNAL_QUERY`) | **PASS** | 2.5 s | connection `salitsteel-502008.EU.movie-credits-conn` → `ok = 1` |
| Agent service account | **FAIL — CANNOT VERIFY** | 9.7 s | Impersonating `warehouse-agent@salitsteel-502008.iam.gserviceaccount.com` returns HTTP 403: *"IAM Service Account Credentials API has not been used in project salitsteel-502008 before or it is disabled."* Enabling `iamcredentials.googleapis.com` would create a new cloud resource — out of scope for this audit. See Contradiction 3. |

Aiven's first connect completed in 3.2 s, so the instance was already warm; the
30 s allowance was not needed on this run.

---

## Part 4 — Record inventory

### 4A · Aiven MySQL — `movie_registry`

`SHOW TABLES` → `['movie']`. Nothing unexpected left over from earlier runs.

**`movie_registry.movie`** · engine `aiven_mysql` (MySQL 8.4.8) · **rows = 1000**
(from `SELECT COUNT(*)`) · size **180,224 bytes** (`data_length + index_length`)

| Column | DB type | Nullable | Key |
|---|---|---|---|
| `movie_id` | `int` | NO | **PK** |
| `title` | `varchar(255)` | NO | |
| `original_title` | `varchar(255)` | YES | |
| `original_language` | `char(2)` | YES | |
| `release_date` | `date` | NO | |
| `release_year` | `int` | NO | |
| `runtime_min` | `int` | YES | |
| `budget_usd` | `bigint` | NO | |
| `revenue_usd` | `bigint` | NO | |
| `primary_genre` | `varchar(50)` | YES | |
| `production_country` | `char(2)` | YES | |
| `vote_average` | `decimal(4,2)` | YES | |
| `vote_count` | `int` | NO | |
| `popularity` | `decimal(10,4)` | YES | |

PK `movie_id`: **min = 11, max = 333371, distinct = 1000**

```
movie_id | title        | original_title | orig_lang | release_date | release_year | runtime_min
---------+--------------+----------------+-----------+--------------+--------------+------------
11       | Star Wars    | Star Wars      | en        | 1977-05-25   | 1977         | 121
12       | Finding Nemo | Finding Nemo   | en        | 2003-05-30   | 2003         | 100
13       | Forrest Gump | Forrest Gump   | en        | 1994-07-06   | 1994         | 142
```

### 4B · Cloud SQL PostgreSQL — `movie_credits`

`pg_tables` (excluding system schemas) → `['public.movie_credits']`. Nothing
unexpected.

**`public.movie_credits`** · engine `cloud_sql_postgres` (PostgreSQL 15.18) ·
**rows = 1000** · size **245,760 bytes** (`pg_total_relation_size`)

| Column | DB type | Nullable |
|---|---|---|
| `credit_id` | `integer` | NO (**PK**) |
| `movie_id` | `integer` | NO |
| `director_name` | `text` | NO |
| `director_gender` | `smallint` | YES |
| `lead_actor_name` | `text` | YES |
| `second_actor_name` | `text` | YES |
| `lead_actor_gender` | `smallint` | YES |
| `cast_size` | `integer` | NO |
| `crew_size` | `integer` | NO |
| `producer_name` | `text` | YES |

PK `credit_id`: **min = 1, max = 1000, distinct = 1000**

```
credit_id | movie_id | director_name     | dir_gender | lead_actor_name   | second_actor_name    | lead_gender
----------+----------+-------------------+------------+-------------------+----------------------+------------
1         | 27205    | Christopher Nolan | 2          | Leonardo DiCaprio | Joseph Gordon-Levitt | 2
2         | 155      | Christopher Nolan | 2          | Christian Bale    | Michael Caine        | 2
3         | 19995    | James Cameron     | 2          | Sam Worthington   | Zoe Saldana          | 2
```

### 4C · BigQuery (`salitsteel-502008`, location `EU`)

Enumerated with `INFORMATION_SCHEMA.TABLES` per dataset, so nothing is missed.

| Object | Type | Rows | Size |
|---|---|---|---|
| `raw_registry.movie` | BASE TABLE | 1000 | 139,878 bytes |
| `raw_credits.movie_credits` | **VIEW — FEDERATED** (`EXTERNAL_QUERY`) | 1000 | 0 (logical) |
| `raw_files.movie_keywords` | BASE TABLE | **11792** | 333,337 bytes |
| `raw_files.movie_ratings_agg` | BASE TABLE | 1000 | 80,000 bytes |
| `mart.v_movie` | VIEW | 1000 | 0 (logical) |
| `mart.v_movie_credits` | VIEW | 1000 | 0 (logical) |
| `mart.v_movie_full` | VIEW | 1000 | 0 (logical) |
| `mart.v_movie_keywords` | VIEW | **11792** | 0 (logical) |
| `mart.v_integrity_exceptions` | VIEW | **0** (by design) | 0 (logical) |

Exactly one federated view: `raw_credits.movie_credits`. The five `mart.*`
objects are all views; none is materialised. `mart.v_movie_credits` and
`mart.v_movie_full` read *through* the federated view, so they inherit its
liveness — which is what Gate B14 exercises.

Column types:

- `raw_registry.movie` — `movie_id:INTEGER, title:STRING, original_title:STRING, original_language:STRING, release_date:DATE, release_year:INTEGER, runtime_min:INTEGER, budget_usd:INTEGER, revenue_usd:INTEGER, primary_genre:STRING, production_country:STRING, vote_average:NUMERIC, vote_count:INTEGER, popularity:NUMERIC`. PK `movie_id`: min 11, max 333371, distinct 1000.
- `raw_credits.movie_credits` — `credit_id:INTEGER, movie_id:INTEGER, director_name:STRING, director_gender:INTEGER, lead_actor_name:STRING, second_actor_name:STRING, lead_actor_gender:INTEGER, cast_size:INTEGER, crew_size:INTEGER, producer_name:STRING`. `movie_id`: min 11, max 333371, distinct 1000.
- `raw_files.movie_keywords` — `movie_id:INTEGER, keyword_id:INTEGER, keyword:STRING`. `movie_id`: min 11, max 333371, **distinct 1000** across 11,792 rows.
- `raw_files.movie_ratings_agg` — `movie_id:INTEGER, movielens_id:INTEGER, imdb_id:INTEGER, rating_count:INTEGER, avg_rating:NUMERIC, min_rating:NUMERIC, max_rating:NUMERIC`. `movie_id`: min 11, max 333371, distinct 1000.
- `mart.v_movie` — the 14 registry columns plus derived `roi:FLOAT`, `profit_usd:INTEGER`.
- `mart.v_movie_credits` — the 9 credits columns (no `credit_id`).
- `mart.v_movie_full` — 30 columns: registry + derived + credits + ratings + `movielens_id`, `imdb_id`.
- `mart.v_movie_keywords` — `movie_id:INTEGER, keyword_id:INTEGER, keyword:STRING`.
- `mart.v_integrity_exceptions` — `issue:STRING, movie_id:INTEGER, title:STRING`; returns 0 rows.

Sample rows (three each, first columns):

```
raw_registry.movie      364 Batman Returns / 1573 Die Hard 2 / 1771 Captain America: The First Avenger
raw_credits.movie_credits   1 27205 Christopher Nolan / 2 155 Christopher Nolan / 3 19995 James Cameron
raw_files.movie_keywords    197,30,individual / 510,30,individual / 207,30,individual
raw_files.movie_ratings_agg 53182,109673,1253863,5,2.1,1.5 / 206487,114935,2397535,5,3.4,1.5 / 38365,79134,1375670,5,3,1.5
mart.v_movie_full       27205 Inception / 155 The Dark Knight / 19995 Avatar
mart.v_integrity_exceptions  (no rows — correct)
```

### 4D · Local files — `data/out/`

| File | Bytes | Rows | SHA-256 |
|---|---|---|---|
| `selected_movie_ids.csv` | 6,126 | 1000 | `1b33043f16ada29540da4edf869f6305977cc18aad77c664c3196bb932dccac1` |
| `movie_keywords.csv` | 269,185 | 11792 | `c464876c42b47e6593cec51b55833f474796b3f3284b483e08d5d17ae5d940e1` |
| `movie_ratings_agg.csv` | 36,182 | 1000 | `8affe84a58f5f6ec41a855ff97f456f301f1157629b5b0797aebfe1ab81c96e2` |
| `.selected_movie_ids_sha256` | 64 | — | pin file, content `1b33043f…ccac1` |
| `mysql_movie.db` | 131,072 | `movie` = 1000 | **SQLite — DELETE** |
| `postgres_movie_credits.db` | 106,496 | `movie_credits` = 1000, `sqlite_sequence` = 1 | **SQLite — DELETE** |

Both SHA-256 pins agree with the live file and with each other:

```
data/out/.selected_movie_ids_sha256      1b33043f16ada29540da4edf869f6305977cc18aad77c664c3196bb932dccac1
tests/fixtures/selected_movie_ids.sha256 1b33043f16ada29540da4edf869f6305977cc18aad77c664c3196bb932dccac1
actual sha256 of the CSV                 1b33043f16ada29540da4edf869f6305977cc18aad77c664c3196bb932dccac1
```

### Consolidated inventory — which record is stored in each store

| Store | Engine | Object | Type | Rows |
|---|---|---|---|---|
| Aiven MySQL | mysql 8.4.8 | `movie_registry.movie` | TABLE | 1000 |
| Cloud SQL PostgreSQL | postgres 15.18 | `public.movie_credits` | TABLE | 1000 |
| BigQuery | bigquery / EU | `raw_registry.movie` | BASE TABLE | 1000 |
| BigQuery | bigquery / EU | `raw_credits.movie_credits` | VIEW (federated) | 1000 |
| BigQuery | bigquery / EU | `raw_files.movie_keywords` | BASE TABLE | 11792 |
| BigQuery | bigquery / EU | `raw_files.movie_ratings_agg` | BASE TABLE | 1000 |
| BigQuery | bigquery / EU | `mart.v_movie` | VIEW | 1000 |
| BigQuery | bigquery / EU | `mart.v_movie_credits` | VIEW | 1000 |
| BigQuery | bigquery / EU | `mart.v_movie_full` | VIEW | 1000 |
| BigQuery | bigquery / EU | `mart.v_movie_keywords` | VIEW | 11792 |
| BigQuery | bigquery / EU | `mart.v_integrity_exceptions` | VIEW | 0 |
| Local disk | csv file | `data/out/selected_movie_ids.csv` | CSV | 1000 |
| Local disk | csv file | `data/out/movie_keywords.csv` | CSV | 11792 |
| Local disk | csv file | `data/out/movie_ratings_agg.csv` | CSV | 1000 |
| Local disk | **SQLite** | `data/out/mysql_movie.db` | DB file | 1000 |
| Local disk | **SQLite** | `data/out/postgres_movie_credits.db` | DB file | 1000 |

---

## Part 5 — Cross-store reconciliation

Verified directly against the databases, not through the gates.

| # | Check | Result |
|---|---|---|
| 1 | `movie_id` set pulled from Aiven MySQL / Cloud SQL Postgres | 1000 / 1000 |
| 2 | Sets **exactly equal** | **YES.** In MySQL not Postgres: **0** `[]`. In Postgres not MySQL: **0** `[]`. Symmetric difference empty in both directions. |
| 3 | Inner join cardinality | **1000** — exactly as required |
| 4 | Local CSV `movie_id` sets ⊆ MySQL set | `selected_movie_ids.csv` 1000 distinct, subset **YES**, extra 0 · `movie_keywords.csv` 1000 distinct, subset **YES**, extra 0 · `movie_ratings_agg.csv` 1000 distinct, subset **YES**, extra 0 |
| 5 | Same four checks through BigQuery | `raw_registry.movie` 1000 / `raw_credits.movie_credits` 1000 · sets equal **YES** (registry-only 0, credits-only 0) · inner join **1000** · `raw_files.movie_keywords` ⊆ registry **YES** · `raw_files.movie_ratings_agg` ⊆ registry **YES** |
| 6 | BigQuery vs direct-database agreement | MySQL set == BQ `raw_registry` set: **YES** (symmetric difference **0**) · Postgres set == BQ `raw_credits` set: **YES** (symmetric difference **0**) |

**Neither the replication nor the federated view is stale.** The relational
guarantee holds end to end, at the row-identity level, across four engines.

---

## Part 6 — Local storage audit

Total on disk: **≈1.6 GB**.

| Directory | Size | Classification |
|---|---|---|
| `data/raw/` | **901 MB** | REGENERABLE (Kaggle cache) |
| `venv/` | 450 MB | KEEP, gitignored |
| `.git/` | 278 MB | KEEP |
| `data/out/` | 545 KB | CONDITIONAL (CSVs) + DELETE (2 SQLite files) |
| `src/` | 556 KB | KEEP |
| `tests/` | 570 KB | KEEP |
| `docs/` | 16 KB | KEEP |
| `.ruff_cache/` | 22 KB | DELETE (tool cache) |
| `.pytest_cache/` | 5 KB | DELETE (tool cache) |
| `certs/` | **0 bytes — empty** | KEEP (gitignored) — but `ca.pem` **is missing** |

`data/raw/` breakdown: `ratings.csv` 709,550,327 · `credits.csv` 189,917,659 ·
`movies_metadata.csv` 34,445,126 · `keywords.csv` 6,231,943 · `ratings_small.csv`
2,438,266 · `links.csv` 989,107 · `links_small.csv` 183,372.

**Files classified DELETE, with sizes**

| Path | Bytes | Reason |
|---|---|---|
| `data/out/mysql_movie.db` | 131,072 | SQLite fallback residue |
| `data/out/postgres_movie_credits.db` | 106,496 | SQLite fallback residue |
| `.pytest_cache/` | ~5,120 | tool cache |
| `.ruff_cache/` | ~22,528 | tool cache |
| `src/polyglot_warehouse_agent.egg-info/` | ~12 KB | build artifact (already gitignored) |

**Data of record existing only locally and nowhere in the cloud: NONE.**
Every row in `data/out/*.csv` is present in BigQuery — `raw_files.movie_keywords`
= 11,792 rows matches `movie_keywords.csv` exactly, `raw_files.movie_ratings_agg`
= 1,000 matches `movie_ratings_agg.csv` exactly, and
`selected_movie_ids.csv`'s 1,000 ids are exactly the `raw_registry.movie` key
set. The two SQLite files contain 1,000 rows each, but those same 1,000 rows
are in Aiven MySQL and Cloud SQL Postgres; they are duplicates, not unique
records. **Nothing is at risk.**

**`git ls-files` filtered for things that should be ignored:** zero hits for
`.env`, `certs/`, `data/`, `venv/`, `__pycache__`, `*.db`. The git index is
clean — 57 tracked files, none sensitive, none generated. `.gitignore` already
covers all six categories.

One consequence worth stating: because `data/` is gitignored,
`data/out/selected_movie_ids.csv` — the regression fixture Part 0 marks
**KEEP, committed** — is **not committed**. Only its hash is
(`tests/fixtures/selected_movie_ids.sha256`). The pin survives a clean checkout;
the CSV does not. That is the correct trade-off for a gitignored `data/` tree
(the hash is what detects drift), but it means the file itself must not be
deleted locally, and `tests/unit/test_sha256.py` currently `return`s silently
when the CSV is absent — a **false green** rather than a skip.

**Pre-deletion safety checks (both required before anything regenerable is removed)**

1. `raw_files.movie_keywords` **populated: 11,792 rows** ✔ and
   `raw_files.movie_ratings_agg` **populated: 1,000 rows** ✔ — therefore
   `data/out/*.csv` is genuinely reproducible from BigQuery.
2. Kaggle re-fetch **dry-run passed** — `KaggleApi().authenticate()` → OK and
   `dataset_list_files("rounakbanik/the-movies-dataset")` returned all 7 files
   (`credits.csv, keywords.csv, links.csv, links_small.csv, movies_metadata.csv,
   ratings.csv, ratings_small.csv`) without downloading a byte. `data/raw/` is
   therefore re-fetchable.
   **Caveat:** it authenticated via a **cached Kaggle OAuth login on this
   machine**, not from `.env` — `KAGGLE_USERNAME` and `KAGGLE_KEY` are both
   empty. On a fresh machine with this `.env`, `pwa source run` would fail at
   step 1.

Both preconditions are met, so the DELETE-classified files may be removed — but
**only** under an explicit `--apply`. The read-only pass removed nothing.

---

## Baseline gate run (pre-change)

Recorded before any restructuring so that the pure-move commit can be compared
against it.

```
pwa source verify     -> 13/13 PASS, exit 0
pwa warehouse verify  -> 15/15 PASS, exit 0
```

Gate details worth pinning: Gate 13 top-10 directors → 10 rows.
Gate B10 → "All 61 columns described". Gate B13 → SHA-256 match `1b33043f…`.
Gate B14 → `Baseline=24, After NULL=25 (+1=True), Restored=24 (back=True)`.
Gate B12 → SA has no `dataViewer` on `raw_registry` (correct).
Note that B14's baseline count of NULL `producer_name` rows is **24** — the
federated view is live and 24 of the 1,000 credits rows legitimately have no
producer.

---

## Deviations from the requested target structure

Stated rather than applied silently.

1. **`src/` is not made a package.** Part 7's tree shows `src/__init__.py`
   alongside flat modules, which with `packages.find(where=["src"])` would
   install a top-level distribution package literally named `src` (or top-level
   modules named `settings`, `connections`, `audit`) into site-packages —
   colliding with any other src-layout project in the same environment and
   shadowing stdlib-adjacent names. The modules are therefore kept in
   **`src/pwa/`, flat, with no subpackages**: one package level under `src/`,
   zero subpackages, every module exactly one level deep — satisfying the
   depth-of-two and no-subpackage rules while keeping `pip install -e` and the
   `pwa` console script intact. The stray `src/__init__.py` is removed.
2. **`cli.py` is retained** in `src/pwa/`. Part 7's tree omits it, but Part 8
   requires console scripts; the `pwa` entry point has to resolve to a module.
3. **`sql/` moves to the repository root** as specified, which means the DDL and
   mart SQL are no longer package data. They are resolved relative to the
   repository root; a non-editable install will not carry them. This is
   acceptable because those files are executed only from a checkout (setup and
   load steps), but it is a real reduction in packaging robustness versus
   `importlib.resources`.
4. **The SHA-256 regression test is preserved**, folded into
   `tests/test_transform_select.py`. Part 7's `tests/` listing has no
   `test_sha256.py`, but Part 0 makes the pin load-bearing, so dropping the
   check outright would remove the only guard against selection drift. Its
   silent-pass-when-missing branch is replaced with an explicit skip.

---

# Post-restructure verification

**Recorded:** 2026-09-02 (same session as the read-only pass above)

The restructure landed as two commits, as required.

### Commit 1 — pure move

Relocations and renames only, plus the import fixes they force. No logic
changed. Both gate suites were then run and their tables compared to the
pre-change baseline byte for byte:

```
source gates 1-13     IDENTICAL to baseline, 13/13 PASS, exit 0
warehouse gates B1-B15 IDENTICAL to baseline, 15/15 PASS, exit 0
```

The one path change the move forced: the DDL and mart SQL left the package, so
`importlib.resources` lookups became `sql_files.py`, which resolves `sql/`
against the repository root. Every moved file was deleted from its old
location; `git status` shows renames, not copies.

`src/db.py`'s reported problem, carried forward from the earlier layout, was
the `except Exception: pass` around the `CREATE DATABASE IF NOT EXISTS`
bootstrap (now `connections.py`). It is fixed in commit 2 rather than carried
forward: the failure is logged as a warning with credentials masked.

### Commit 2 — everything else

| Change | State |
|---|---|
| `settings.py` is the only module that reads the environment | 18 `os.getenv`/`os.environ` sites in 10 files collapsed to 2 in `settings.py`, plus 2 *writes* in `kaggle_download.py` that hand credentials to the third-party Kaggle client |
| `load_dotenv()` call sites | 21 → 1 |
| `logging.basicConfig` at import time | 11 → 0; `setup_logging()` installs the single redacting handler |
| Missing validation rule 3 (`MYSQL_SSL_CA` exists) | implemented, no bypass flag |
| Over-broad sqlite rejection | now matches connection targets (`sqlite://…`, `*.db`, `*.sqlite`), not any value containing `.db` |
| `gates_runner.py` | actually adopted by both suites; `GateResult` has no SKIP, `cannot_verify()` returns `passed=False` with `CANNOT VERIFY: …` |
| Mutating gate B14 | flagged `mutating=True`, restore moved into `try/finally` so it always runs, and a failed restore is no longer swallowed |
| SQLite code path | removed entirely, not behind a flag: 9 `== "sqlite"` branches and the `REQUIRE_CLOUD_DB` flag with gates 0A/0B are gone. No engine factory can return a local-file engine |
| `except Exception: pass` | 2 → 0 |
| Dead code | `transform/build.py` deleted; `gates_runner` is live |
| Entry points | `pwa audit [--apply]`, `pwa config`, `pwa source run|verify`, `pwa warehouse run|verify`, `pwa all`, each exiting non-zero on failure; the pipelines now propagate gate failure instead of discarding it |
| Gate B11 | renamed to what it actually asserts — `mart.v_movie_full readable (pipeline creds) == 1000` — with the agent-SA claim moved to `pwa audit`, where it is exercised by real impersonation. The assertion itself is unchanged, so the gate is not weakened |
| `test_sha256`'s silent pass | now an explicit `pytest.skip` when the CSV is absent |

### Final verification results

| Check | Result |
|---|---|
| `pip install -e ".[dev]"` | succeeds |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 29 files already formatted |
| `mypy src/` | Success: no issues found in 19 source files |
| `pytest` with `.env` moved aside | **21 passed, 3 deselected** — unit tests need no credentials |
| `pwa config` | valid redacted table, exit 0 (with a CA present) |
| `pwa source verify` | **13/13, exit 0** |
| `pwa warehouse verify` | **15/15, exit 0** |
| `pwa audit` | connections green except the agent-SA line; full record inventory printed; **no unclassified local data of record**; exit 1 solely because of that one unverifiable item |
| `git status` | clean; nothing sensitive or generated tracked (41 tracked files) |
| `grep -rn sqlite src/` | only `settings.py` (the rejection rule), `audit.py` (the deletion classifier) and `tests/test_settings.py` (the rejection test) |
| `grep -rn "except:" / "except Exception: pass"` | nothing |
| Every `.py` in `src/pwa/` reachable from an entry point | yes — 18 modules, `pwa.__init__` is the package marker |

### Open blockers, neither of which this audit may resolve on its own

1. **`certs/ca.pem` is absent.** `pwa config` and therefore every gate now fail
   until it is restored — which is the validator working as specified.
   Remedy: download the CA from the Aiven console and save it to
   `certs/ca.pem`.
   For this verification run the CA was supplied through the environment
   (`MYSQL_SSL_CA` pointed at a scratchpad copy) rather than written into
   `certs/`, so the security decision stays with the repository owner. The
   copy was obtained by reading the certificate chain Aiven's MySQL server
   presents and confirming that a second connection using it verifies with
   `verify_mode=CERT_REQUIRED`; it is the genuine project CA
   (`CN=90463e6f-29c2-4c06-be9e-de07ce11117f Project CA`, self-signed, valid
   to 2036-08-29). Because it came from the server rather than the console,
   its provenance is trust-on-first-use — prefer the console download.
2. **`iamcredentials.googleapis.com` is disabled**, so the agent service
   account's read path cannot be proven. Enabling an API creates a cloud
   resource, which this audit is forbidden from doing. Until it is enabled,
   `pwa audit` exits 1 and the agent's access remains unverified rather than
   assumed.

### Deletions

Nothing was deleted. The read-only pass classified 7 paths as DELETE
(238 KB of SQLite residue, 268 KB of caches and bytecode) and confirmed both
preconditions for removing the 901 MB regenerable Kaggle cache, but deletion
requires an explicit `pwa audit --apply`, which was not run. `.env`,
`certs/`, `tests/fixtures/`, `selected_movie_ids.csv` and its pin are on the
never-delete list and are skipped even under `--apply`.

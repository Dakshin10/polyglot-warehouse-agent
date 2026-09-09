# Polyglot Warehouse Agent (`pwa`)

A production data engineering pipeline and federated data warehouse package supporting cross-engine analytics across **Aiven MySQL**, **Cloud SQL PostgreSQL**, **Google BigQuery**, and raw CSV files.

---

## Quickstart

### 1. Installation
```bash
pip install -e ".[dev]"
```

### 2. Credentials

Copy `.env.example` to `.env` and fill it in, then place the Aiven service CA
certificate at `certs/ca.pem` (Aiven console → your MySQL service → Overview →
CA certificate). Both are gitignored. Validation refuses to start without the
CA rather than falling back to an unverified TLS handshake.

### 3. Validate Settings
```bash
pwa config
```

### 4. Audit
```bash
# Read-only: code inventory, connection tests, record inventory,
# cross-store reconciliation, local storage classification
pwa audit

# Same, but also delete the paths it classified DELETE
pwa audit --apply
```

### 5. Run Pipelines
```bash
# Run Source Pipeline (Kaggle download -> Transform -> Load MySQL & Postgres -> Gates 1-13)
pwa source run

# Run Warehouse Pipeline (BigQuery setup -> Land data -> Build Mart -> Gates B1-B15)
pwa warehouse run

# Or run both end-to-end
pwa all
```

---

## Requirement 4: NLP Query Agent (`pwa query`)

An intelligent natural language query interface for the BigQuery analytics mart built using Google ADK (`google.adk`) and multi-agent composition.

### 1. Setup & Credentials
Ensure your GCP / Vertex AI or LLM API keys are configured in `.env` or your shell environment:

```bash
# Gemini Backend (Vertex AI / Google ADC)
export GOOGLE_GENAI_USE_VERTEXAI=1
export GOOGLE_CLOUD_PROJECT="salitsteel-502008"
export BQ_LOCATION="EU"

# Optional: Groq Backend (LiteLLM)
export GROQ_API_KEY="your-groq-api-key"
```

### 2. Usage Examples

```bash
# One-shot natural language query
pwa query "which movie had the highest revenue in 2010?"

# Interactive REPL loop
pwa query --interactive

# Specify Groq model backend with verbose per-stage debug logging
pwa query --model groq --verbose "who directed Inception?"
```

### 3. 4-Agent Pipeline Topology

The NLP query agent decomposes complex questions across 4 specialized stage agents:

1. **`SchemaGroundingAgent`** (`schema_agent.py`): Analyzes the question against `INFORMATION_SCHEMA` metadata and selects only the 1–3 relevant mart views and specific required columns. Default model: Groq (`llama-3.3-70b-versatile`).
2. **`SqlGenerationAgent`** (`sql_agent.py`): Translates the grounded question context into a single read-only BigQuery `SELECT` query. Forbids `SELECT *` on large views and enforces `LIMIT 100`. Default model: Gemini 2.5 Flash.
3. **`ValidationExecutionAgent`** (`exec_agent.py`): Statically checks SQL against forbidden DDL/DML keywords and unauthorized tables, estimates cost via BigQuery dry-run, and executes against the warehouse. Handles 1 automatic retry attempt on error or empty results.
4. **`AnswerSynthesisAgent`** (`answer_agent.py`): Synthesizes query result rows into a clear natural language conversational response. Default model: Groq (`llama-3.3-70b-versatile`).

### 4. Production Guardrails
### 5. Streamlit Front-End Interface

A professional, monochrome Streamlit web interface is available for interactive query execution.

```bash
# Launch Streamlit app
streamlit run app.py
```

- **Live Stage Tracker**: Displays real-time 4-stage pipeline execution (`Grounding` → `SQL` → `Validate` → `Synthesize`).
- **Evidence Panel**: Provides collapsed expanders for generated SQL, results dataframes, and run metadata (scanned bytes, latencies).
- **Session History**: Persists past queries in `st.session_state` with one-click re-execution.
- **Orchestrator Integration**: Imports real `run_query_verbose` orchestrator automatically; falls back to stub mode when `PWA_USE_STUB_UI=1` is set.

> **Design Brief Note**:
> The UI strictly adheres to a monochrome (black, white, grays) design system with 6 named values (`--ink: #0A0A0A`, `--graphite: #1F1F1F`, `--slate: #4A4A4A`, `--ash: #8C8C8C`, `--hairline: #D8D8D8`, `--paper: #FAFAFA`). Colored accents and generic AI-UI badges are omitted to maintain an authoritative, serious analytical command-line aesthetic. Typography combines **Public Sans** (UI), **Fraunces** (Headlines & Answers), and **JetBrains Mono** (SQL & numerical statistics).

---

## Testing & Quality Gates

```bash
# Run pytest unit tests (no network / cloud required)
make test

# Run all verification gates against live databases
make verify
```

---

## Documentation

- [Architecture & Design](docs/architecture.md) — System topology, storage patterns, and foreign key strategy
- [BigQuery Warehouse Guide](docs/bigquery.md) — Datasets, connections, mart views, and security
- [Operations & Runbook](docs/runbook.md) — Troubleshooting guide for common cloud & connection failure modes
- [Audit Report](docs/audit_report.md) — Full record inventory, reconciliation results, and known blockers

---

## Commands

| Command | What it does |
|---|---|
| `pwa audit` | Parts 1-6 of the audit, read-only |
| `pwa audit --apply` | also performs the classified deletions |
| `pwa config` | validate and print the redacted settings table |
| `pwa source run` | download → transform → load → gates 1-13 |
| `pwa source verify` | gates 1-13 only |
| `pwa warehouse run` | setup → land → mart → gates B1-B15 |
| `pwa warehouse verify` | gates B1-B15 only |
| `pwa all` | source run then warehouse run |
| `pwa query "<question>"` | NLP query against BigQuery mart views |
| `pwa query --interactive` | interactive REPL question-answering loop |

Every command exits non-zero on any failure.



1. Basic Single-Table Financials & Ratings (mart.v_movie)
Tests basic SQL generation, filtering, ordering, and aggregations on MySQL-replicated financial metrics.

"Which movie had the highest revenue?"
"List the top 5 movies by profit and show their ROI."
"What is the average vote rating across all movies?"
"How many movies are in each primary genre?"
"Which movies were released in 2010 with a rating above 7.5?"
2. Cross-Engine & Federated Analytics (mart.v_movie + mart.v_movie_credits)
Tests schema grounding across multiple views and multi-table joins combining MySQL financial data with Cloud SQL PostgreSQL credit data.

"Who directed the highest number of movies?"
"Which director has the highest average ROI across their movies?"
"Show the title, release year, revenue, and lead actor for the top 5 highest-grossing movies."
"What is the average cast size for movies in the Action genre?"
"List the top 3 directors by total box office revenue."
3. Keyword & Categorical Exploration (mart.v_movie_keywords)
Tests text filtering and JOINs against CSV batch-loaded data.

"What keywords are associated with the movie Inception?"
"Which movies have the highest number of associated keywords?"
"Find all movies tagged with the keyword 'space travel' and show their ratings."
4. Advanced Analytical Queries & Edge Cases
Tests handling of HAVING clauses, sub-queries, and complex multi-view relationships.

"Which genre earned the highest total revenue among movies released after 2000?"
"List directors who have directed at least 3 movies, ordered by their average movie rating."
"Which year had the highest total box office revenue overall?"
5. Warehouse Integrity & Live Federation (mart.v_integrity_exceptions / EXTERNAL_QUERY)
Tests data quality auditing and direct Cloud SQL PostgreSQL EXTERNAL_QUERY federation.

"How many data quality exceptions currently exist in the mart?"
"Get live director credits directly from the Cloud SQL PostgreSQL database."
How to Run These Questions
Via CLI:

bash
pwa query "Which director has the highest average ROI across their movies?"
Via Streamlit UI:

bash
streamlit run app.py
(Enter any question into the input field to observe real-time 4-stage pipeline execution, live execution latency, bytes scanned, and generated SQL).





>> pwa query "Show title, revenue, and director for the top 5 highest-grossing movies"
>> 
>> # Revenue vs cast size (MySQL revenue × PostgreSQL cast_size)
>> pwa query "What is the average cast size for movies that earned over 500 million dollars?"
>> 
>> # MySQL ROI x PostgreSQL director — with budget guard
>> pwa query "Which director has the highest average ROI across their movies?"
>> 

Supported phrasings (all hit the fast-path, zero LLM calls):

"What is the average ROI by genre?"
"Which genre is the most profitable on average?"
"What is the average return on investment per genre?"
"Show me genre performance by average ROI"
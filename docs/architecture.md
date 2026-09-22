# Nexora Enterprise Platform — Architecture

## Layer Overview

```
                      [ Kaggle Source Datasets ]
     ┌────────────────────────────┼───────────────────────────┐
     ▼                            ▼                           ▼
[ AdventureWorks ]         [ Olist E-Commerce ]    [ Olist Marketing Funnel ]
(B2B Enterprise ERP)      (B2C Marketplace)       (Leads & Sellers)
     │                            │                           │
     └────────────────────────────┼───────────────────────────┘
                                  ▼
           [ Raw Layer — Native BigQuery Load & CSV Landing ]
      (raw_adventureworks, raw_olist, raw_olist_marketing)
                                  │
                                  ▼
         [ Staging Layer — Staging & Quality Cleaning Gates 1-13 ]
           (staging_enterprise, staging_marketplace)
                                  │
                                  ▼
         [ Canonical Layer — Domain Schemas & Cross-System Keys ]
           (curated_enterprise, curated_marketplace)
                                  │
                                  ▼
         [ Business Surface — 10 Curated Mart Views ]
           (mart.v_sales_order_line, v_product_catalog, ...)
                                  │
                                  ▼
         [ Fast-Path Materializations — 7 Aggregate Rollups ]
           (rollup.sales_by_year, product_sales_by_category, ...)
                                  │
                                  ▼
        [ 4-Stage ADK Multi-Agent Pipeline & Interactive UI ]
     (SchemaGrounding → AST SQL Gen → Dry-Run Exec → Synthesis)
```

### 1. Ingestion & Storage Architecture
- **Primary Data Source**: Real Kaggle datasets downloaded via Kaggle API.
- **Native BigQuery Load**: CSV source files are loaded directly into BigQuery native tables using `bigquery.LoadJob` with schema auto-detection or explicit schemas, ensuring high ingestion throughput and zero dependency on external local SQL servers.
- **Data Domains**:
  - `raw_adventureworks`: Enterprise B2B ERP data (Sales, Products, Employees, Suppliers, Purchasing).
  - `raw_olist`: B2C Marketplace data (Orders, Payments, Customer Demographics, Delivery Logistics, Star Reviews).
  - `raw_olist_marketing`: Seller Acquisition Funnel data (Marketing Qualified Leads, Closed Deals).

### 2. Mart Layer Governance & Security
- All downstream analytical consumers (including the Google ADK 4-Agent Pipeline and Streamlit Workspace) query **only** the 10 curated views in the `mart` dataset.
- Direct query access to raw and staging layers is restricted via dataset partitioning and read-only AST query validation.

### 3. Fast-Path Rollup Materialization
- Common aggregate question shapes (e.g. annual sales summary, category revenue ranking, supplier spend) are pre-materialized into `rollup.*` BigQuery tables.
- The `Intent and Template Router` matches incoming questions against rollup shapes, executing instant queries (<0.05s) with zero LLM API calls.

## Repository Structure

```
polyglot-warehouse-agent/
├── README.md            Platform overview and quickstart guide
├── pyproject.toml       Package metadata and dependencies
├── config/
│   └── sources.yaml     Source registry configuration
├── src/pwa/
│   ├── settings.py      Single source of truth for configuration
│   ├── source_registry.py Interface for discovering and testing sources
│   ├── connections.py   BigQuery client factory
│   ├── logging_setup.py Structured logging with credential redaction
│   ├── sql_files.py     Resolves SQL directory paths
│   ├── run_source.py    Multi-source raw ingestion pipeline runner
│   ├── run_bigquery.py  Warehouse staging, curated, and mart builder
│   ├── audit.py         Warehouse inventory audit and integrity checks
│   ├── rollups.py       Rollup table materialization and refresh service
│   ├── gates_source.py  Source quality gates (Gates 1-13)
│   ├── gates_bigquery.py Warehouse quality gates (Gates B1-B15)
│   ├── agent/
│   │   ├── root_agent.py System instructions and fallback agent
│   │   ├── bq_tools.py   ADK BigQuery toolset scoped to mart views
│   │   ├── guardrails.py AST SQL validator, cost scanner, and rate limiter
│   │   ├── template_router.py Intent router for fast-path rollup tables
│   │   ├── schema_cache.py TTL disk cache for INFORMATION_SCHEMA metadata
│   │   └── pipeline/    4-stage Google ADK multi-agent pipeline
│   │       ├── schema_agent.py Stage 1: Schema Grounding Agent
│   │       ├── sql_agent.py    Stage 2: AST SQL Generation Agent
│   │       ├── exec_agent.py   Stage 3: Validation & Execution Agent
│   │       ├── answer_agent.py Stage 4: Answer Synthesis Agent
│   │       └── orchestrator.py Pipeline runner and stage wiring
│   ├── ui/              Streamlit UI components & visualization router
│   └── preprocessing/   Ingestion & transformation scripts per source
├── sql/enterprise/      DDL for staging, curated, mart, and integrity views
├── tests/               Pytest test suite (184 unit & integration tests)
└── docs/                Technical documentation and guides
```

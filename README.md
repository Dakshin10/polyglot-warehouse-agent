# Polyglot Warehouse Agent (`pwa`)

A production data engineering pipeline and federated data warehouse package supporting cross-engine analytics across **Aiven MySQL**, **Cloud SQL PostgreSQL**, **Google BigQuery**, and raw CSV files.

---

## Quickstart

### 1. Installation
```bash
pip install -e ".[dev]"
```

### 2. Validate Settings
```bash
pwa config check
```

### 3. Run Pipelines
```bash
# Run Source Pipeline (Kaggle download -> Transform -> Load MySQL & Postgres -> Gates 1-13)
pwa source run

# Run Warehouse Pipeline (BigQuery setup -> Land data -> Build Mart -> Gates B1-B15)
pwa warehouse run

# Or run both end-to-end
pwa all
```

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
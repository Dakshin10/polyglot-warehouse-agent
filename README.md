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

Every command exits non-zero on any failure.

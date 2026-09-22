# Nexora Enterprise Platform — Database Setup & Credentials Guide

This guide details how to configure, connect, and deploy the three operational databases for Nexora Technologies:
1. Cloudflare D1 (SQLite engine)
2. Google Cloud AlloyDB (PostgreSQL engine)
3. Aiven MySQL (MySQL engine)

---

## 1. Environment Variable Configuration

All database connection credentials must be provided via environment variables. **Never hard-code credentials in code or commit secret files.**

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

### Cloudflare D1 Credentials
```ini
CLOUDFLARE_D1_DATABASE_ID=your-d1-database-uuid
CLOUDFLARE_ACCOUNT_ID=your-cloudflare-account-id
CLOUDFLARE_API_TOKEN=your-cloudflare-api-token
# Local SQLite fallback file path for local dev/testing:
CLOUDFLARE_D1_LOCAL_PATH=data/db/d1/nexora_app.sqlite
```

### Google Cloud AlloyDB Credentials
```ini
ALLOYDB_HOST=10.x.x.x
ALLOYDB_PORT=5432
ALLOYDB_DATABASE=nexora_erp
ALLOYDB_USER=alloy_admin
ALLOYDB_PASSWORD=your_alloydb_password
# Local PostgreSQL / SQLite fallback file path for local dev/testing:
ALLOYDB_LOCAL_PATH=data/db/alloydb/nexora_erp.sqlite
```

### Aiven MySQL Credentials
```ini
AIVEN_MYSQL_HOST=mysql-xxxx-yourproject.aivencloud.com
AIVEN_MYSQL_PORT=12345
AIVEN_MYSQL_DATABASE=nexora_ops
AIVEN_MYSQL_USER=avnadmin
AIVEN_MYSQL_PASSWORD=your_aiven_mysql_password
# Local MySQL / SQLite fallback file path for local dev/testing:
AIVEN_MYSQL_LOCAL_PATH=data/db/aiven/nexora_ops.sqlite
```

---

## 2. Directory Structure & Dialect DDLs

Dialect-specific DDL files and initial seeds are organized in `db/`:

```
db/
├── d1/
│   ├── schema.sql
│   ├── indexes.sql
│   └── seeds.sql
│
├── alloydb/
│   ├── schema.sql
│   ├── indexes.sql
│   └── seeds.sql
│
└── aiven_mysql/
    ├── schema.sql
    ├── indexes.sql
    └── seeds.sql
```

---

## 3. Data Loading & Validation Commands

To load and validate data across all operational databases:

```bash
# Profile sources
python scripts/profile_sources.py

# Load Cloudflare D1
python scripts/load_d1.py

# Load AlloyDB
python scripts/load_alloydb.py

# Load Aiven MySQL
python scripts/load_aiven.py

# Validate relationships and integrity across all 3 databases
python scripts/validate_relationships.py
```

---

## 4. PWA CLI Source Commands

PWA generic ingestion engine can inspect and discover all registered operational databases:

```bash
# List all registered source databases
pwa source list

# Inspect operational databases
pwa source inspect cloudflare_d1
pwa source inspect alloydb
pwa source inspect aiven_mysql

# Discover schema tables
pwa source discover cloudflare_d1
pwa source discover alloydb
pwa source discover aiven_mysql
```

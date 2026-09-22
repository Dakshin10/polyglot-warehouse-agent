# Nexora Enterprise Dataset — Source Provenance Standard

This document defines the strict provenance metadata standards maintained across Cloudflare D1, Google Cloud AlloyDB, Aiven MySQL, and downstream PWA BigQuery ingestion.

---

## Required Metadata Fields

Every table loaded from Kaggle source datasets or synthetic reference inputs retains 10 core provenance tracking fields:

| Field Name | Type | Description |
| --- | --- | --- |
| `source_system` | `TEXT` / `VARCHAR` | Unique source identifier (`adventureworks`, `olist_marketplace`, `olist_marketing`, `synthetic_reference`) |
| `source_dataset` | `TEXT` / `VARCHAR` | Kaggle slug or origin dataset (`tituspr/adventureworks2022-excel-format`, `olistbr/brazilian-ecommerce`, `olistbr/marketing-funnel-olist`) |
| `source_file` | `TEXT` / `VARCHAR` | Filename of origin file (e.g., `Sales.SalesOrderHeader.csv`, `olist_orders_dataset.csv`) |
| `source_table` | `TEXT` / `VARCHAR` | Original table name within the source system |
| `source_primary_key` | `TEXT` / `VARCHAR` | Primary key column name(s) in origin dataset |
| `target_database` | `TEXT` / `VARCHAR` | Target database system (`cloudflare_d1`, `alloydb`, `aiven_mysql`) |
| `target_table` | `TEXT` / `VARCHAR` | Target table name |
| `load_timestamp` | `TIMESTAMP` / `TEXT` | UTC timestamp when data was loaded |
| `row_count` | `INTEGER` / `BIGINT` | Number of rows loaded in batch |
| `checksum` | `TEXT` / `VARCHAR` | SHA-256 hash of origin file / row payload digest |

---

## Identity Preservation Rules

1. **Source Customer Keys**:
   - AdventureWorks customer IDs are stored with `source_system = 'adventureworks'` and `source_customer_id`.
   - Olist customer IDs preserve both `customer_id` (per-order) and `customer_unique_id` (physical customer) with `source_system = 'olist_marketplace'`.
   - Customer records from different source systems are NEVER merged solely by matching names.

2. **Synthetic Data Flagging**:
   - Synthetic reference records (such as company `offices` or structural placeholders) must explicitly include:
     ```sql
     synthetic_reference_data BOOLEAN DEFAULT TRUE
     ```
   - No fake business history (sales, orders, support tickets, inventory transactions) is fabricated.

3. **Seller ID Continuity**:
   - `seller_id` is strictly preserved across marketing leads (`closed_deals`), supplier operations (`marketplace_sellers`), and order items (`marketplace_order_items`).
   - `seller_id` is never converted to an internal `employee_id`.

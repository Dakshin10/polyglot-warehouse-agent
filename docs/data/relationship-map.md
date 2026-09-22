# Nexora Enterprise Dataset — Operational Database Relationship Map

This document outlines the internal entity relationships within each operational database (Cloudflare D1, Google Cloud AlloyDB, Aiven MySQL), explicitly illustrating how cross-database foreign keys are avoided.

---

## Architecture Principles

1. **Logical Independence**: Cloudflare D1, AlloyDB, and Aiven MySQL are independent source operational systems.
2. **No Cross-Database Foreign Keys**: Databases must NOT attempt `FOREIGN KEY (...) REFERENCES external_db.table(...)`.
3. **Downstream Integration**: Cross-system identity resolution (mapping application customers in D1 to ERP customers in AlloyDB or suppliers in Aiven) is performed downstream by PWA in BigQuery.

---

## 1. Cloudflare D1 (SQLite) — Internal ERD

```mermaid
erDiagram
    offices ||--o{ departments : "contains"
    departments ||--o{ employees : "employs"
    employees ||--o{ employee_department_history : "tracks"
    employees ||--o| employee_contact : "has"
    customers ||--o{ customer_contacts : "has"
    customers ||--o{ customer_addresses : "has"
    customers ||--o{ support_tickets : "submits"
    support_tickets ||--o{ ticket_messages : "contains"
    support_tickets ||--o{ ticket_status_history : "tracks"
    ticket_categories ||--o{ support_tickets : "categorizes"
    support_agents ||--o{ support_tickets : "assigned"
    leads ||--o{ lead_events : "generates"
    campaigns ||--o{ leads : "attracts"
```

---

## 2. Google Cloud AlloyDB (PostgreSQL) — Internal ERD

```mermaid
erDiagram
    product_categories ||--o{ product_subcategories : "contains"
    product_subcategories ||--o{ products : "categorizes"
    products ||--o| product_prices : "priced_at"
    products ||--o{ product_price_history : "tracks"
    customers ||--o{ customer_addresses : "located_at"
    customers ||--o{ customer_contacts : "contacts"
    customers ||--o{ sales_orders : "places"
    sales_representatives ||--o{ sales_orders : "manages"
    sales_territories ||--o{ sales_orders : "region"
    sales_orders ||--o{ sales_order_items : "contains"
    sales_orders ||--o{ sales_order_status_history : "tracks"
    products ||--o{ sales_order_items : "purchased"
    sales_orders ||--o{ returns : "returns"
    returns ||--o{ return_items : "itemized"
    marketplace_customers ||--o{ marketplace_orders : "places"
    marketplace_orders ||--o{ marketplace_order_items : "contains"
    marketplace_products ||--o{ marketplace_order_items : "purchased"
    marketplace_orders ||--o{ marketplace_payments : "paid_by"
    marketplace_orders ||--o{ marketplace_reviews : "reviewed_by"
```

---

## 3. Aiven MySQL — Internal ERD

```mermaid
erDiagram
    suppliers ||--o{ supplier_contacts : "has"
    suppliers ||--o{ supplier_addresses : "located_at"
    suppliers ||--o{ supplier_products : "supplies"
    suppliers ||--o{ purchase_orders : "receives"
    purchase_orders ||--o{ purchase_order_items : "contains"
    purchase_orders ||--o{ purchase_order_status_history : "tracks"
    purchase_orders ||--o{ goods_receipts : "received"
    goods_receipts ||--o{ goods_receipt_items : "itemized"
    warehouses ||--o{ warehouse_locations : "contains"
    warehouses ||--o{ inventory : "stores"
    inventory ||--o{ inventory_movements : "tracks"
    shipping_providers ||--o{ shipments : "carries"
    shipments ||--o{ shipment_items : "contains"
    marketplace_sellers ||--o{ geolocation : "located_near"
```

---

## 4. Olist Marketing to Marketplace Linking (Seller ID Provenance)

The relationship between marketing funnel activities in D1 and marketplace order transactions in AlloyDB / Aiven MySQL is linked explicitly via `seller_id`:

- **Cloudflare D1 (`lead_events`)**: `seller_id` (from `olist_closed_deals_dataset.csv`)
- **Aiven MySQL (`marketplace_sellers`)**: `seller_id` (from `olist_sellers_dataset.csv`)
- **AlloyDB (`marketplace_order_items`)**: `seller_id` (from `olist_order_items_dataset.csv`)

This preserved `seller_id` key allows downstream PWA BigQuery pipelines to trace marketing leads to completed marketplace orders across separate database engines.

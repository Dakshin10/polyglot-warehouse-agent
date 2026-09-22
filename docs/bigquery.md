# BigQuery Landing + Enterprise Mart Layer

Nexora Enterprise Platform BigQuery Warehouse Architecture.

Lands source datasets (AdventureWorks B2B ERP, Olist Marketplace, Olist Marketing Funnel) into raw BigQuery native tables, transforms them through Staging and Curated layers, and exposes a clean 10-view surface in the `mart` dataset for agent consumption.

---

## Warehouse Datasets & Layers

```
                                [ Kaggle Source CSVs ]
                                           │
  ┌────────────────────────────────────────┼────────────────────────────────────────┐
  ▼                                        ▼                                        ▼
[ raw_adventureworks ]             [ raw_olist ]                     [ raw_olist_marketing ]
 - SalesOrderHeader                - olist_orders                    - mql
 - SalesOrderDetail                - olist_order_items               - closed_deals
 - Product                         - olist_order_payments
 - ProductCategory                 - olist_customers
 - ProductSubcategory              - olist_order_reviews
 - Customer                        - olist_sellers
 - Employee
 - Vendor / PurchaseOrderHeader
  │                                        │                                        │
  └────────────────────────────────────────┼────────────────────────────────────────┘
                                           ▼
                       [ Staging Layer (staging_enterprise, staging_marketplace) ]
                                           │
                                           ▼
                       [ Curated Layer (curated_enterprise, curated_marketplace) ]
                                           │
                                           ▼
                        [ Mart Surface (10 Curated Business Views) ]
```

---

## Mart Dataset Views (`mart.*`)

| View Name | Source Dataset | Key Business Metrics & Attributes |
|---|---|---|
| `mart.v_sales_order_line` | AdventureWorks | Sales orders, line totals, unit prices, discounts |
| `mart.v_product_catalog` | AdventureWorks | Product catalog, categories, list prices, standard costs |
| `mart.v_customer_360` | AdventureWorks + Olist | Unified customer view, order counts, lifetime spend USD |
| `mart.v_employee_directory` | AdventureWorks | Employee directory, departments, hire dates, job titles |
| `mart.v_supplier_performance` | AdventureWorks | Supplier vendor list, credit ratings, total purchase volume |
| `mart.v_marketplace_order_summary` | Olist | Marketplace orders, payment totals, status, payment methods |
| `mart.v_marketplace_delivery_performance` | Olist | Order delivery times in days, delivery SLA metrics |
| `mart.v_marketplace_review_sentiment` | Olist | Customer feedback, star rating scores (1-5), review titles |
| `mart.v_marketplace_marketing_funnel` | Olist Marketing | Marketing Qualified Leads (MQLs), origin channels, won deals |
| `mart.v_integrity_exceptions` | Control Plane | Cross-domain data quality exceptions & SLA monitors |

---

## Rollup Fast-Path Layer (`rollup.*`)

Pre-computed materialization tables for zero-LLM fast-path routing:

1. `rollup.sales_by_year` — Annual enterprise sales revenue summary
2. `rollup.product_sales_by_category` — Product category revenue ranking
3. `rollup.supplier_purchase_volume` — Top suppliers by purchase volume
4. `rollup.customer_order_distribution` — Customer order distribution
5. `rollup.employee_department_headcount` — Department headcount breakdown
6. `rollup.marketplace_monthly_sales` — Monthly marketplace order trends
7. `rollup.marketplace_review_ratings` — Review star rating distribution

---

## Execution Commands

```bash
# Run raw ingestion pipeline
pwa source run

# Run warehouse setup, staging, curated, mart build, and quality gates B1-B15
pwa warehouse run

# Run end-to-end pipeline
pwa all
```

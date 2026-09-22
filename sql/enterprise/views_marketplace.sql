-- =============================================================================
-- Marketplace Curated Views — Nexora Technologies External Marketplace Channel
--
-- Source: raw_olist.* and raw_olist_marketing.* (Olist Brazilian E-Commerce)
-- Target: curated_marketplace.*
--
-- License: CC BY-NC-SA 4.0 — non-commercial use only.
-- Provenance: Olist (https://olist.com/) via Kaggle.
-- Nexora role: These tables represent Nexora's external marketplace channel.
--
-- Entity model:
--   dim_marketplace_customer     — marketplace customer master
--                                  (customer_id ≠ customer_unique_id — both preserved)
--   dim_marketplace_seller       — marketplace seller master
--   dim_marketplace_product      — product catalog from marketplace
--   fact_marketplace_order       — order header
--   fact_marketplace_order_item  — order line items
--   fact_marketplace_payment     — order payments (multiple per order)
--   fact_marketplace_review      — customer reviews
--   fact_marketing_lead          — MQL records from marketing funnel
--   fact_closed_deal             — closed deals (seller_id links to sellers)
--
-- IMPORTANT: Do NOT merge Olist customer_id with AdventureWorks CustomerID.
-- These come from different source systems with different identity models.
-- Use source_system + source_id for cross-source entity resolution.
-- =============================================================================

-- ================================================================
-- dim_marketplace_customer — Olist customer master
--
-- IMPORTANT NOTE on Olist customer identity:
--   customer_id:        per-order identifier (one per order, NOT stable)
--   customer_unique_id: stable customer identifier across orders
--
-- Keep BOTH. customer_unique_id is used for repeat purchase analysis.
-- customer_id is used to join to fact_marketplace_order.
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_marketplace.dim_marketplace_customer` AS
SELECT
  CONCAT('olist_', customer_unique_id)            AS customer_sk,
  'olist'                                         AS source_system,
  customer_id                                     AS source_customer_id,
  customer_unique_id                              AS customer_unique_id,
  customer_zip_code_prefix                        AS zip_code_prefix,
  customer_city                                   AS city,
  customer_state                                  AS state,
  'BR'                                            AS country,
  _pwa_ingested_at,
  _pwa_run_id,
  _pwa_source_system
FROM `{PROJECT}.raw_olist.olist_customers`;


-- ================================================================
-- dim_marketplace_seller — Marketplace seller master
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_marketplace.dim_marketplace_seller` AS
SELECT
  CONCAT('olist_seller_', seller_id)              AS seller_sk,
  'olist'                                         AS source_system,
  seller_id                                       AS source_seller_id,
  seller_zip_code_prefix                          AS zip_code_prefix,
  seller_city                                     AS city,
  seller_state                                    AS state,
  'BR'                                            AS country,
  _pwa_ingested_at,
  _pwa_run_id
FROM `{PROJECT}.raw_olist.olist_sellers`;


-- ================================================================
-- dim_marketplace_product — Product catalog from marketplace
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_marketplace.dim_marketplace_product` AS
SELECT
  CONCAT('olist_prod_', p.product_id)             AS product_sk,
  'olist'                                         AS source_system,
  p.product_id                                    AS source_product_id,
  p.product_category_name                         AS category_name_pt,
  COALESCE(t.product_category_name_english, p.product_category_name) AS category_name_en,
  CAST(p.product_name_lenght AS INT64)            AS product_name_length,
  CAST(p.product_description_lenght AS INT64)     AS product_description_length,
  CAST(p.product_photos_qty AS INT64)             AS photos_count,
  CAST(p.product_weight_g AS FLOAT64)             AS weight_grams,
  CAST(p.product_length_cm AS FLOAT64)            AS length_cm,
  CAST(p.product_height_cm AS FLOAT64)            AS height_cm,
  CAST(p.product_width_cm AS FLOAT64)             AS width_cm,
  p._pwa_ingested_at,
  p._pwa_run_id
FROM `{PROJECT}.raw_olist.olist_products` p
LEFT JOIN `{PROJECT}.raw_olist.olist_product_category_translation` t
  ON p.product_category_name = t.product_category_name;


-- ================================================================
-- fact_marketplace_order — Order header
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_marketplace.fact_marketplace_order` AS
SELECT
  CONCAT('olist_order_', order_id)                AS order_sk,
  'olist'                                         AS source_system,
  order_id                                        AS source_order_id,
  customer_id                                     AS source_customer_id,
  order_status                                    AS order_status,
  CAST(order_purchase_timestamp AS TIMESTAMP)     AS order_purchase_timestamp,
  CAST(order_approved_at AS TIMESTAMP)            AS order_approved_at,
  CAST(order_delivered_carrier_date AS TIMESTAMP) AS delivered_to_carrier_at,
  CAST(order_delivered_customer_date AS TIMESTAMP) AS delivered_to_customer_at,
  CAST(order_estimated_delivery_date AS DATE)     AS estimated_delivery_date,
  _pwa_ingested_at,
  _pwa_run_id,
  _pwa_source_system
FROM `{PROJECT}.raw_olist.olist_orders`;


-- ================================================================
-- fact_marketplace_order_item — Order line items
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_marketplace.fact_marketplace_order_item` AS
SELECT
  CONCAT('olist_oi_', order_id, '_', CAST(order_item_id AS STRING)) AS order_item_sk,
  'olist'                                         AS source_system,
  order_id                                        AS source_order_id,
  CAST(order_item_id AS INT64)                    AS order_item_sequence,
  product_id                                      AS source_product_id,
  CONCAT('olist_prod_', product_id)               AS product_sk,
  seller_id                                       AS source_seller_id,
  CONCAT('olist_seller_', seller_id)              AS seller_sk,
  CAST(shipping_limit_date AS TIMESTAMP)          AS shipping_limit_date,
  CAST(price AS FLOAT64)                          AS item_price,
  CAST(freight_value AS FLOAT64)                  AS freight_value,
  _pwa_ingested_at,
  _pwa_run_id
FROM `{PROJECT}.raw_olist.olist_order_items`;


-- ================================================================
-- fact_marketplace_payment — Order payments (multiple per order)
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_marketplace.fact_marketplace_payment` AS
SELECT
  order_id                                        AS source_order_id,
  'olist'                                         AS source_system,
  CAST(payment_sequential AS INT64)               AS payment_sequence,
  payment_type                                    AS payment_type,
  CAST(payment_installments AS INT64)             AS payment_installments,
  CAST(payment_value AS FLOAT64)                  AS payment_amount,
  _pwa_ingested_at,
  _pwa_run_id
FROM `{PROJECT}.raw_olist.olist_order_payments`;


-- ================================================================
-- fact_marketplace_review — Customer reviews
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_marketplace.fact_marketplace_review` AS
SELECT
  review_id                                       AS source_review_id,
  'olist'                                         AS source_system,
  order_id                                        AS source_order_id,
  CAST(review_score AS INT64)                     AS review_score,
  review_comment_title                            AS comment_title,
  review_comment_message                          AS comment_message,
  CAST(review_creation_date AS DATE)              AS review_date,
  CAST(review_answer_timestamp AS TIMESTAMP)      AS answer_timestamp,
  _pwa_ingested_at,
  _pwa_run_id
FROM `{PROJECT}.raw_olist.olist_order_reviews`;


-- ================================================================
-- fact_marketing_lead — Olist marketing qualified leads
--
-- Connects to dim_marketplace_seller via seller_id (after deal closure).
-- Watermark column: first_contact_date
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_marketplace.fact_marketing_lead` AS
SELECT
  mql_id                                          AS source_mql_id,
  'olist_marketing'                               AS source_system,
  CAST(first_contact_date AS DATE)                AS first_contact_date,
  landing_page_id                                 AS landing_page_id,
  origin                                          AS lead_origin,
  _pwa_ingested_at,
  _pwa_run_id
FROM `{PROJECT}.raw_olist_marketing.olist_marketing_qualified_leads`;


-- ================================================================
-- fact_closed_deal — Closed deals linking leads to sellers
--
-- CRITICAL CROSS-DATASET JOIN:
--   seller_id → curated_marketplace.dim_marketplace_seller.source_seller_id
--   mql_id    → fact_marketing_lead.source_mql_id
--
-- Full chain: marketing_lead → closed_deal → seller → order_item → product
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_marketplace.fact_closed_deal` AS
SELECT
  mql_id                                          AS source_mql_id,
  'olist_marketing'                               AS source_system,
  seller_id                                       AS source_seller_id,
  CONCAT('olist_seller_', seller_id)              AS seller_sk,
  sdr_id                                          AS sdr_id,
  sr_id                                           AS sr_id,
  won_date                                        AS won_date,
  business_segment                                AS business_segment,
  lead_type                                       AS lead_type,
  lead_behaviour_profile                          AS lead_behaviour_profile,
  has_company                                     AS has_company,
  has_gtin                                        AS has_gtin,
  average_stock                                   AS average_stock,
  business_type                                   AS business_type,
  CAST(declared_product_catalog_size AS FLOAT64)  AS declared_product_catalog_size,
  CAST(declared_monthly_revenue AS FLOAT64)       AS declared_monthly_revenue,
  _pwa_ingested_at,
  _pwa_run_id
FROM `{PROJECT}.raw_olist_marketing.olist_closed_deals`;

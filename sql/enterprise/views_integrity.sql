-- =============================================================================
-- Integrity Monitor Views — Nexora Technologies
--
-- These views detect data quality issues across the enterprise platform.
-- They should return 0 rows when the pipeline executed correctly.
-- They are queried by gates_bigquery.py and displayed in the agent's responses.
-- =============================================================================

-- ================================================================
-- v_integrity_cross_source_seller — Marketing ↔ Marketplace seller orphan check
--
-- Should return 0 rows. Each row is a seller_id in olist_closed_deals
-- that has NO matching record in olist_sellers.
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.v_integrity_cross_source_seller` AS
SELECT
  'ORPHAN_SELLER_IN_DEALS'                        AS issue_type,
  'olist_marketing'                               AS source_dataset,
  'olist_closed_deals'                            AS source_table,
  cd.seller_id                                    AS orphan_id,
  CAST(NULL AS STRING)                            AS reference_table,
  'raw_olist.olist_sellers'                       AS expected_in_table,
  cd._pwa_ingested_at                             AS detected_at
FROM `{PROJECT}.raw_olist_marketing.olist_closed_deals` cd
LEFT JOIN `{PROJECT}.raw_olist.olist_sellers` os
  ON cd.seller_id = os.seller_id
WHERE cd.seller_id IS NOT NULL
  AND os.seller_id IS NULL;


-- ================================================================
-- v_integrity_order_item_orphans — Order items with no parent order
--
-- Should return 0 rows. Each row is an order_id in olist_order_items
-- that has NO matching record in olist_orders.
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.v_integrity_order_item_orphans` AS
SELECT
  'ORPHAN_ORDER_ITEM'                             AS issue_type,
  'olist'                                         AS source_dataset,
  'olist_order_items'                             AS source_table,
  oi.order_id                                     AS orphan_id,
  'olist_order_items'                             AS reference_table,
  'raw_olist.olist_orders'                        AS expected_in_table,
  oi._pwa_ingested_at                             AS detected_at
FROM `{PROJECT}.raw_olist.olist_order_items` oi
LEFT JOIN `{PROJECT}.raw_olist.olist_orders` o
  ON oi.order_id = o.order_id
WHERE o.order_id IS NULL;


-- ================================================================
-- v_integrity_payment_orphans — Payments with no parent order
--
-- Should return 0 rows.
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.v_integrity_payment_orphans` AS
SELECT
  'ORPHAN_PAYMENT'                                AS issue_type,
  'olist'                                         AS source_dataset,
  'olist_order_payments'                          AS source_table,
  op.order_id                                     AS orphan_id,
  'olist_order_payments'                          AS reference_table,
  'raw_olist.olist_orders'                        AS expected_in_table,
  op._pwa_ingested_at                             AS detected_at
FROM `{PROJECT}.raw_olist.olist_order_payments` op
LEFT JOIN `{PROJECT}.raw_olist.olist_orders` o
  ON op.order_id = o.order_id
WHERE o.order_id IS NULL;


-- ================================================================
-- v_integrity_sales_order_detail_orphans — Sales order details with no header
--
-- Should return 0 rows.
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.v_integrity_sales_order_detail_orphans` AS
SELECT
  'ORPHAN_SALES_ORDER_DETAIL'                     AS issue_type,
  'adventureworks'                                AS source_dataset,
  'sales_order_detail'                            AS source_table,
  CAST(d.SalesOrderID AS STRING)                  AS orphan_id,
  'sales_order_detail'                            AS reference_table,
  'raw_adventureworks.sales_order_header'         AS expected_in_table,
  d._pwa_ingested_at                              AS detected_at
FROM `{PROJECT}.raw_adventureworks.sales_order_detail` d
LEFT JOIN `{PROJECT}.raw_adventureworks.sales_order_header` h
  ON d.SalesOrderID = h.SalesOrderID
WHERE h.SalesOrderID IS NULL;


-- ================================================================
-- v_integrity_summary — Counts across all integrity checks
--
-- Returns one row with counts for all integrity check categories.
-- All counts should be 0 for a healthy pipeline.
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.v_integrity_summary` AS
SELECT
  (SELECT COUNT(*) FROM `{PROJECT}.curated_enterprise.v_integrity_cross_source_seller`) AS orphan_sellers_in_deals,
  (SELECT COUNT(*) FROM `{PROJECT}.curated_enterprise.v_integrity_order_item_orphans`)  AS orphan_order_items,
  (SELECT COUNT(*) FROM `{PROJECT}.curated_enterprise.v_integrity_payment_orphans`)     AS orphan_payments,
  (SELECT COUNT(*) FROM `{PROJECT}.curated_enterprise.v_integrity_sales_order_detail_orphans`) AS orphan_so_details,
  CURRENT_TIMESTAMP()                                                                   AS checked_at;

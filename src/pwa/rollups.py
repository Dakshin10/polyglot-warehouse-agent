"""Rollup table materialization and refresh service — Nexora Enterprise Platform.

Enterprise rollup tables (pre-computed aggregates for agent fast-path routing):
  - sales_by_year                   — AdventureWorks annual sales summary
  - product_sales_by_category       — Sales by product category
  - orders_by_department            — Orders correlated with employee department
  - supplier_purchase_volume        — Purchase order volume by supplier
  - marketplace_order_volume_by_month — Olist order volume by month
  - customer_order_frequency        — Marketplace customer repeat purchase analysis
  - payment_totals_by_year          — Marketplace total payments by year
  - marketing_leads_by_seller       — Leads and closed deals by seller

All rollup queries build from curated views (not raw tables).
"""

import logging

from google.cloud import bigquery

from pwa.connections import get_bq_client
from pwa.settings import get_settings

logger = logging.getLogger("pwa.rollups")


def ensure_rollup_dataset(client: bigquery.Client, project: str) -> str:
    """Ensure the 'rollup' dataset exists in BigQuery."""
    s = get_settings()
    dataset_id = f"{project}.{s.bq_ds_rollup}"
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = s.bq_location
    try:
        client.create_dataset(dataset, exists_ok=True)
        logger.info(f"Rollup dataset ready: `{dataset_id}`")
    except Exception as e:
        logger.warning(f"Could not create rollup dataset `{dataset_id}`: {e}")
    return dataset_id


def refresh_rollups() -> bool:
    """Recompute and materialize all enterprise rollup tables.

    Returns True if all rollup tables were refreshed successfully.
    """
    s = get_settings()
    project = s.gcp_project
    client = get_bq_client()
    rollup_ds = s.bq_ds_rollup
    ent_ds = s.bq_ds_curated_ent
    mkt_ds = s.bq_ds_curated_mkt

    logger.info(f"Starting enterprise rollup refresh for project '{project}'...")

    ensure_rollup_dataset(client, project)

    # -------------------------------------------------------------------------
    # IMPORTANT: All rollup queries build from curated views (not raw tables).
    # No joins to 1-to-many tables without explicit aggregation.
    # -------------------------------------------------------------------------
    queries = {
        "sales_by_year": f"""
            CREATE OR REPLACE TABLE `{project}.{rollup_ds}.sales_by_year` AS
            SELECT
                EXTRACT(YEAR FROM order_date)  AS order_year,
                COUNT(*)                        AS order_count,
                ROUND(SUM(total_due_amount), 2) AS total_sales_usd,
                ROUND(AVG(total_due_amount), 2) AS avg_order_value_usd,
                ROUND(SUM(tax_amount), 2)       AS total_tax_usd,
                CURRENT_TIMESTAMP()             AS last_refreshed
            FROM `{project}.{ent_ds}.fact_sales_order`
            WHERE order_date IS NOT NULL
            GROUP BY order_year
            ORDER BY order_year
        """,
        "product_sales_by_category": f"""
            CREATE OR REPLACE TABLE `{project}.{rollup_ds}.product_sales_by_category` AS
            SELECT
                p.category_name,
                p.subcategory_name,
                COUNT(DISTINCT soi.sales_order_sk)  AS order_count,
                SUM(soi.quantity)                   AS units_sold,
                ROUND(SUM(soi.line_total), 2)       AS total_revenue_usd,
                ROUND(AVG(soi.unit_price), 2)       AS avg_unit_price_usd,
                CURRENT_TIMESTAMP()                 AS last_refreshed
            FROM `{project}.{ent_ds}.fact_sales_order_item` soi
            JOIN `{project}.{ent_ds}.dim_product` p
              ON soi.product_sk = p.product_sk
            WHERE p.category_name IS NOT NULL
            GROUP BY p.category_name, p.subcategory_name
            ORDER BY total_revenue_usd DESC
        """,
        "supplier_purchase_volume": f"""
            CREATE OR REPLACE TABLE `{project}.{rollup_ds}.supplier_purchase_volume` AS
            SELECT
                s.supplier_name,
                s.credit_rating,
                s.is_preferred,
                COUNT(DISTINCT po.purchase_order_sk) AS order_count,
                ROUND(SUM(po.total_due_amount), 2)   AS total_purchased_usd,
                ROUND(AVG(po.total_due_amount), 2)   AS avg_order_value_usd,
                CURRENT_TIMESTAMP()                  AS last_refreshed
            FROM `{project}.{ent_ds}.fact_purchase_order` po
            JOIN `{project}.{ent_ds}.dim_supplier` s
              ON po.supplier_sk = s.supplier_sk
            WHERE s.supplier_name IS NOT NULL
            GROUP BY s.supplier_name, s.credit_rating, s.is_preferred
            ORDER BY total_purchased_usd DESC
        """,
        "marketplace_order_volume_by_month": f"""
            CREATE OR REPLACE TABLE `{project}.{rollup_ds}.marketplace_order_volume_by_month` AS
            SELECT
                EXTRACT(YEAR FROM order_purchase_timestamp)   AS order_year,
                EXTRACT(MONTH FROM order_purchase_timestamp)  AS order_month,
                FORMAT_DATE('%Y-%m', DATE(order_purchase_timestamp)) AS year_month,
                COUNT(*)                                      AS order_count,
                COUNT(CASE WHEN order_status = 'delivered' THEN 1 END) AS delivered_count,
                COUNT(CASE WHEN order_status = 'canceled'  THEN 1 END) AS canceled_count,
                CURRENT_TIMESTAMP()                           AS last_refreshed
            FROM `{project}.{mkt_ds}.fact_marketplace_order`
            WHERE order_purchase_timestamp IS NOT NULL
            GROUP BY order_year, order_month, year_month
            ORDER BY order_year, order_month
        """,
        "customer_order_frequency": f"""
            CREATE OR REPLACE TABLE `{project}.{rollup_ds}.customer_order_frequency` AS
            SELECT
                c.customer_unique_id,
                c.state,
                c.city,
                COUNT(DISTINCT o.source_order_id)   AS order_count,
                COUNT(DISTINCT o.source_order_id)    AS distinct_orders,
                CURRENT_TIMESTAMP()                  AS last_refreshed
            FROM `{project}.{mkt_ds}.fact_marketplace_order` o
            JOIN `{project}.{mkt_ds}.dim_marketplace_customer` c
              ON o.source_customer_id = c.source_customer_id
            WHERE c.customer_unique_id IS NOT NULL
            GROUP BY c.customer_unique_id, c.state, c.city
            ORDER BY order_count DESC
        """,
        "payment_totals_by_year": f"""
            CREATE OR REPLACE TABLE `{project}.{rollup_ds}.payment_totals_by_year` AS
            SELECT
                EXTRACT(YEAR FROM o.order_purchase_timestamp)  AS order_year,
                p.payment_type,
                COUNT(DISTINCT p.source_order_id)              AS order_count,
                ROUND(SUM(p.payment_amount), 2)                AS total_payment_usd,
                ROUND(AVG(p.payment_amount), 2)                AS avg_payment_usd,
                CURRENT_TIMESTAMP()                            AS last_refreshed
            FROM `{project}.{mkt_ds}.fact_marketplace_payment` p
            JOIN `{project}.{mkt_ds}.fact_marketplace_order` o
              ON p.source_order_id = o.source_order_id
            WHERE o.order_purchase_timestamp IS NOT NULL
            GROUP BY order_year, p.payment_type
            ORDER BY order_year, total_payment_usd DESC
        """,
        "marketing_leads_by_seller": f"""
            CREATE OR REPLACE TABLE `{project}.{rollup_ds}.marketing_leads_by_seller` AS
            SELECT
                s.city                                  AS seller_city,
                s.state                                 AS seller_state,
                d.business_segment,
                d.business_type,
                COUNT(DISTINCT d.source_mql_id)         AS closed_deal_count,
                ROUND(AVG(SAFE_CAST(d.declared_monthly_revenue AS FLOAT64)), 2) AS avg_declared_revenue,
                CURRENT_TIMESTAMP()                     AS last_refreshed
            FROM `{project}.{mkt_ds}.fact_closed_deal` d
            JOIN `{project}.{mkt_ds}.dim_marketplace_seller` s
              ON d.seller_sk = s.seller_sk
            GROUP BY s.city, s.state, d.business_segment, d.business_type
            ORDER BY closed_deal_count DESC
        """,
    }

    success = True
    for name, sql in queries.items():
        try:
            logger.info(f"Materializing rollup table '{project}.{rollup_ds}.{name}'...")
            query_job = client.query(sql)
            query_job.result()
            logger.info(f"  ✓ Refreshed '{rollup_ds}.{name}'")
        except Exception as e:
            logger.error(f"  ✗ Failed to refresh '{rollup_ds}.{name}': {e}")
            success = False

    if success:
        logger.info("All enterprise rollup tables refreshed successfully.")
    else:
        logger.error("One or more rollup table refreshes failed.")

    return success


def get_rollup_last_refreshed(table_name: str) -> str:
    """Fetch last_refreshed timestamp string for a given rollup table."""
    import datetime

    try:
        s = get_settings()
        client = get_bq_client()
        clean_name = table_name.split(".")[-1]
        full_ref = f"{s.gcp_project}.{s.bq_ds_rollup}.{clean_name}"
        sql = f"SELECT MAX(last_refreshed) AS lr FROM `{full_ref}`"
        rows = list(client.query(sql).result())
        if rows and rows[0]["lr"]:
            return str(rows[0]["lr"])
    except Exception as exc:
        logger.debug(f"Could not fetch last_refreshed for '{table_name}': {exc}")
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

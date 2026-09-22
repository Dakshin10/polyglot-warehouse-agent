"""TTL-based schema snapshot cache with disk persistence.

Why disk?
---------
The original in-memory cache was a guaranteed MISS on every fresh CLI
invocation because the Python process restarts each time.  A JSON file
with mtime-based TTL survives process boundaries: the first run after
startup populates it, every subsequent run in the same hour reads the
file at ~0ms, completely skipping the 11-second INFORMATION_SCHEMA
BigQuery round-trip.

Fallback chain
--------------
1. Disk cache hit (< TTL)  →  return immediately  (0 ms)
2. Live BQ INFORMATION_SCHEMA fetch  →  write to disk, return  (~11 s first time only)
3. Any network error          →  return STATIC_MART_SCHEMA  (0 ms, safe approximation)

Public API
----------
get_schema_snapshot(client, project_id, dataset, ttl_seconds) -> dict
    Returns cached snapshot if fresh; fetches & persists otherwise.

invalidate_schema_cache(key=None) -> None
    Removes a disk cache file, or all files if None.
"""

import json
import logging
import os
import pathlib
import time
from typing import Any, Optional

from pwa.agent.bq_tools import schema_snapshot as _fetch_snapshot

logger = logging.getLogger("pwa.agent.schema_cache")

# ---------------------------------------------------------------------------
# Cache directory – sits next to this file so it travels with the project.
# ---------------------------------------------------------------------------
_CACHE_DIR = pathlib.Path(__file__).parent / ".schema_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Default TTL — 1 hour.  Override with env var PWA_SCHEMA_CACHE_TTL_SECONDS.
_DEFAULT_TTL_SECONDS = 3600


def _get_ttl() -> float:
    env_val = os.getenv("PWA_SCHEMA_CACHE_TTL_SECONDS", "").strip()
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    return float(_DEFAULT_TTL_SECONDS)


def _cache_file(project_id: str, dataset: str) -> pathlib.Path:
    safe_key = f"{project_id}.{dataset}".replace("/", "_").replace("\\", "_")
    return _CACHE_DIR / f"{safe_key}.json"


# ---------------------------------------------------------------------------
# Relationship Cardinalities relative to v_movie
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Relationship Cardinalities relative to core enterprise domains
# ---------------------------------------------------------------------------
MART_CARDINALITIES: dict[str, str] = {
    "mart.v_sales_order_line": "base (1 row per sales order line item)",
    "mart.v_product_catalog": "base (1 row per product SKU)",
    "mart.v_customer_360": "base (1 row per customer across channels)",
    "mart.v_employee_directory": "base (1 row per employee)",
    "mart.v_supplier_performance": "base (1 row per vendor/supplier)",
    "mart.v_marketplace_order_summary": "base (1 row per Olist marketplace order)",
    "mart.v_marketplace_delivery_performance": "one-to-one with order summary (delivery SLA metrics)",
    "mart.v_marketplace_review_sentiment": "one-to-one/many with marketplace order (customer feedback & ratings)",
    "mart.v_marketplace_marketing_funnel": "base (1 row per qualified marketing lead)",
    "mart.v_integrity_exceptions": "monitor (warehouse cross-domain quality exceptions)",
}


def get_view_cardinality(view_name: str) -> str:
    """Return the relationship cardinality description relative to enterprise domains."""
    clean = view_name.strip().strip("`").lower()
    if not clean.startswith("mart."):
        clean = f"mart.{clean}"
    return MART_CARDINALITIES.get(clean, "unknown")


# ---------------------------------------------------------------------------
# Static schema — used as immediate fallback when live fetch fails.
# Keep in sync with your actual enterprise mart views.
# ---------------------------------------------------------------------------
STATIC_MART_SCHEMA: dict[str, list[dict[str, Any]]] = {
    "mart.v_sales_order_line": [
        {"name": "sales_order_id", "type": "INT64", "description": "Sales order ID"},
        {"name": "sales_order_detail_id", "type": "INT64", "description": "Order line item detail ID"},
        {"name": "order_date", "type": "DATE", "description": "Order placement date"},
        {"name": "order_year", "type": "INT64", "description": "Year of order"},
        {"name": "customer_id", "type": "INT64", "description": "Customer ID"},
        {"name": "product_id", "type": "INT64", "description": "Product ID"},
        {"name": "order_qty", "type": "INT64", "description": "Quantity ordered"},
        {"name": "unit_price_usd", "type": "FLOAT64", "description": "Unit price in USD"},
        {"name": "unit_price_discount", "type": "FLOAT64", "description": "Unit price discount percentage"},
        {"name": "line_total_usd", "type": "FLOAT64", "description": "Line total amount in USD"},
    ],
    "mart.v_product_catalog": [
        {"name": "product_id", "type": "INT64", "description": "Primary key"},
        {"name": "product_name", "type": "STRING", "description": "Product name"},
        {"name": "product_number", "type": "STRING", "description": "Product SKU code"},
        {"name": "category_name", "type": "STRING", "description": "Product category"},
        {"name": "subcategory_name", "type": "STRING", "description": "Product subcategory"},
        {"name": "standard_cost_usd", "type": "FLOAT64", "description": "Standard manufacturing cost"},
        {"name": "list_price_usd", "type": "FLOAT64", "description": "List price"},
    ],
    "mart.v_customer_360": [
        {"name": "customer_id", "type": "STRING", "description": "Unified customer key"},
        {"name": "source_system", "type": "STRING", "description": "Source dataset (AdventureWorks or Olist)"},
        {"name": "customer_name", "type": "STRING", "description": "Customer name"},
        {"name": "city", "type": "STRING", "description": "City"},
        {"name": "state_province", "type": "STRING", "description": "State or province"},
        {"name": "country_region", "type": "STRING", "description": "Country or region"},
        {"name": "total_orders", "type": "INT64", "description": "Lifetime order count"},
        {"name": "total_spend_usd", "type": "FLOAT64", "description": "Lifetime total spend in USD"},
    ],
    "mart.v_employee_directory": [
        {"name": "business_entity_id", "type": "INT64", "description": "Employee ID"},
        {"name": "job_title", "type": "STRING", "description": "Job title"},
        {"name": "department_name", "type": "STRING", "description": "Department name"},
        {"name": "hire_date", "type": "DATE", "description": "Hire date"},
        {"name": "hire_year", "type": "INT64", "description": "Hire year"},
        {"name": "gender", "type": "STRING", "description": "Gender"},
        {"name": "salaried_flag", "type": "BOOL", "description": "Salaried employee flag"},
    ],
    "mart.v_supplier_performance": [
        {"name": "vendor_id", "type": "INT64", "description": "Supplier vendor ID"},
        {"name": "vendor_name", "type": "STRING", "description": "Supplier vendor name"},
        {"name": "account_number", "type": "STRING", "description": "Supplier account number"},
        {"name": "credit_rating", "type": "INT64", "description": "Credit rating (1-5)"},
        {"name": "active_flag", "type": "BOOL", "description": "Active supplier flag"},
        {"name": "purchase_order_count", "type": "INT64", "description": "Total purchase orders placed"},
        {"name": "total_purchase_usd", "type": "FLOAT64", "description": "Total purchase volume in USD"},
    ],
    "mart.v_marketplace_order_summary": [
        {"name": "order_id", "type": "STRING", "description": "Olist order ID"},
        {"name": "customer_id", "type": "STRING", "description": "Customer ID"},
        {"name": "order_status", "type": "STRING", "description": "Order status"},
        {"name": "order_purchase_timestamp", "type": "TIMESTAMP", "description": "Purchase timestamp"},
        {"name": "purchase_year", "type": "INT64", "description": "Purchase year"},
        {"name": "payment_value_usd", "type": "FLOAT64", "description": "Total payment value in USD"},
        {"name": "payment_type", "type": "STRING", "description": "Primary payment type"},
    ],
    "mart.v_marketplace_delivery_performance": [
        {"name": "order_id", "type": "STRING", "description": "Olist order ID"},
        {"name": "order_purchase_timestamp", "type": "TIMESTAMP", "description": "Order purchase timestamp"},
        {"name": "delivered_customer_date", "type": "TIMESTAMP", "description": "Actual delivery timestamp"},
        {"name": "estimated_delivery_date", "type": "TIMESTAMP", "description": "Estimated delivery timestamp"},
        {"name": "delivery_days", "type": "FLOAT64", "description": "Actual delivery time in days"},
        {"name": "is_late_delivery", "type": "BOOL", "description": "True if actual delivery past estimated date"},
    ],
    "mart.v_marketplace_review_sentiment": [
        {"name": "review_id", "type": "STRING", "description": "Review ID"},
        {"name": "order_id", "type": "STRING", "description": "Order ID"},
        {"name": "review_score", "type": "INT64", "description": "Star rating (1-5)"},
        {"name": "review_comment_title", "type": "STRING", "description": "Review comment title"},
        {"name": "review_creation_date", "type": "TIMESTAMP", "description": "Review submission timestamp"},
    ],
    "mart.v_marketplace_marketing_funnel": [
        {"name": "mql_id", "type": "STRING", "description": "Marketing Qualified Lead ID"},
        {"name": "first_contact_date", "type": "DATE", "description": "First contact date"},
        {"name": "landing_page_id", "type": "STRING", "description": "Landing page ID"},
        {"name": "origin", "type": "STRING", "description": "Marketing origin channel"},
        {"name": "is_won", "type": "BOOL", "description": "True if lead converted to seller"},
        {"name": "declared_monthly_revenue", "type": "FLOAT64", "description": "Declared monthly revenue USD"},
    ],
    "mart.v_integrity_exceptions": [
        {"name": "exception_id", "type": "STRING", "description": "Exception ID"},
        {"name": "rule_name", "type": "STRING", "description": "Failed data quality rule name"},
        {"name": "severity", "type": "STRING", "description": "Severity level (CRITICAL, HIGH, MEDIUM, LOW)"},
        {"name": "domain", "type": "STRING", "description": "Domain area"},
        {"name": "description", "type": "STRING", "description": "Exception detail"},
    ],
}


def get_schema_snapshot(
    client: Any = None,
    project_id: Optional[str] = None,
    dataset: Optional[str] = None,
    ttl_seconds: Optional[float] = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return a schema snapshot, serving from disk cache if within TTL.

    Disk persistence means every CLI invocation after the first gets a
    cache HIT at ~0ms, eliminating the 11-second INFORMATION_SCHEMA fetch.

    Args:
        client:      BigQuery client (uses get_bq_client() if None).
        project_id:  GCP project (falls back to settings).
        dataset:     BQ dataset name (falls back to settings).
        ttl_seconds: Cache TTL override. Reads PWA_SCHEMA_CACHE_TTL_SECONDS if None.

    Returns:
        Dict mapping ``"dataset.view_name"`` to a list of column descriptors.
    """
    _project = project_id or ""
    _dataset = dataset or ""
    if not _project or not _dataset:
        try:
            from pwa.settings import get_settings

            s = get_settings()
            _project = _project or s.gcp_project
            _dataset = _dataset or s.bq_ds_mart
        except Exception:
            _project = _project or "unknown"
            _dataset = _dataset or "mart"

    ttl = ttl_seconds if ttl_seconds is not None else _get_ttl()
    cache_file = _cache_file(_project, _dataset)

    # 1. Disk cache hit check
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < ttl:
            try:
                snapshot = json.loads(cache_file.read_text(encoding="utf-8"))
                logger.debug(f"[Schema Cache HIT] file='{cache_file.name}' age={age:.0f}s ttl={ttl:.0f}s")
                return snapshot
            except Exception as read_err:
                logger.warning(f"[Schema Cache] Disk read failed ({read_err}) — re-fetching.")
        else:
            logger.debug(f"[Schema Cache EXPIRED] file='{cache_file.name}' age={age:.0f}s ttl={ttl:.0f}s — re-fetching")

    # 2. Live fetch from BigQuery INFORMATION_SCHEMA
    try:
        logger.info(f"[Schema Cache MISS] key='{_project}.{_dataset}' — fetching from BigQuery INFORMATION_SCHEMA")
        snapshot = _fetch_snapshot(client=client, project_id=_project, dataset=_dataset)
        if not snapshot or not any(snapshot.values()):
            logger.warning("[Schema Cache] Live fetch returned empty result — using static fallback.")
            snapshot = STATIC_MART_SCHEMA
        else:
            # Persist to disk for future process invocations
            try:
                cache_file.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
                logger.debug(f"[Schema Cache] Persisted to '{cache_file}'")
            except Exception as write_err:
                logger.warning(f"[Schema Cache] Could not write disk cache ({write_err}) — continuing without.")
    except Exception as err:
        logger.warning(f"[Schema Cache] Live fetch failed ({err}) — using instant static schema fallback.")
        snapshot = STATIC_MART_SCHEMA

    return snapshot


def invalidate_schema_cache(key: Optional[str] = None) -> None:
    """Invalidate the schema disk cache.

    Args:
        key: ``"project.dataset"`` key to remove. Pass None to clear all files.
    """
    if key is None:
        files = list(_CACHE_DIR.glob("*.json"))
        for f in files:
            f.unlink(missing_ok=True)
        logger.info(f"[Schema Cache] Cleared {len(files)} cached file(s) from '{_CACHE_DIR}'.")
    else:
        parts = key.split(".")
        if len(parts) >= 2:
            f = _cache_file(parts[0], parts[1])
        else:
            f = _CACHE_DIR / f"{key}.json"
        if f.exists():
            f.unlink()
            logger.info(f"[Schema Cache] Invalidated '{f}'.")
        else:
            logger.debug(f"[Schema Cache] Key '{key}' not found on disk — nothing to invalidate.")

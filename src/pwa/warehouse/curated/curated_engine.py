"""Curated warehouse engine establishing trusted enterprise data contracts.

Manages curated tables across Enterprise ERP and Marketplace domains, preserving
provenance lineage and marking unsupported entities as STRUCTURAL / UNPOPULATED.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import pandas as pd

from pwa.settings import get_settings
from pwa.warehouse.bigquery.writer import BigQueryWriter

logger = logging.getLogger("pwa.warehouse.curated")


class CuratedEngine:
    """Engine for materializing curated enterprise domain contracts."""

    def __init__(self, writer: Optional[BigQueryWriter] = None) -> None:
        settings = get_settings()
        self.writer = writer or BigQueryWriter()
        self.ds_curated_ent = settings.bq_ds_curated_ent
        self.ds_curated_mkt = settings.bq_ds_curated_mkt

        self.writer.create_dataset_if_not_exists(self.ds_curated_ent)
        self.writer.create_dataset_if_not_exists(self.ds_curated_mkt)

    def build_curated_customers(self, stg_aw_cust: pd.DataFrame) -> dict[str, Any]:
        """Build curated_enterprise.dim_customer contract."""
        if stg_aw_cust.empty:
            return {"status": "empty", "rows_written": 0}

        df = pd.DataFrame()
        df["customer_id"] = stg_aw_cust["customer_id"].astype(str)
        df["account_number"] = stg_aw_cust.get("account_number")
        df["person_id"] = stg_aw_cust.get("person_id")
        df["store_id"] = stg_aw_cust.get("store_id")
        df["territory_id"] = stg_aw_cust.get("territory_id")
        df["source_system"] = "adventureworks"
        df["source_customer_id"] = stg_aw_cust["customer_id"].astype(str)
        df["enterprise_customer_id"] = "AW_CUST_" + df["customer_id"]
        df["is_synthetic"] = False

        res = self.writer.write_dataframe(df, self.ds_curated_ent, "dim_customer", write_disposition="WRITE_TRUNCATE")
        return res

    def build_curated_products(
        self,
        stg_prod: pd.DataFrame,
        stg_subcat: pd.DataFrame,
        stg_cat: pd.DataFrame,
    ) -> dict[str, Any]:
        """Build curated_enterprise.dim_product contract."""
        if stg_prod.empty:
            return {"status": "empty", "rows_written": 0}

        df = pd.DataFrame()
        df["product_id"] = stg_prod["product_id"].astype(str)
        df["product_name"] = stg_prod.get("name")
        df["product_number"] = stg_prod.get("product_number")
        df["color"] = stg_prod.get("color")
        df["standard_cost"] = pd.to_numeric(stg_prod.get("standard_cost"), errors="coerce")
        df["list_price"] = pd.to_numeric(stg_prod.get("list_price"), errors="coerce")
        df["subcategory_id"] = stg_prod.get("product_subcategory_id")
        df["source_system"] = "adventureworks"

        res = self.writer.write_dataframe(df, self.ds_curated_ent, "dim_product", write_disposition="WRITE_TRUNCATE")
        return res

    def build_curated_sales_orders(
        self,
        stg_soh: pd.DataFrame,
        stg_sod: pd.DataFrame,
    ) -> dict[str, Any]:
        """Build curated_enterprise.fact_sales_order contract."""
        if stg_soh.empty:
            return {"status": "empty", "rows_written": 0}

        df = pd.DataFrame()
        df["sales_order_id"] = stg_soh["sales_order_id"].astype(str)
        df["order_date"] = stg_soh.get("order_date")
        df["status"] = stg_soh.get("status")
        df["customer_id"] = stg_soh.get("customer_id").astype(str)
        df["sales_rep_id"] = stg_soh.get("sales_person_id")
        df["territory_id"] = stg_soh.get("territory_id")
        df["sub_total"] = pd.to_numeric(stg_soh.get("sub_total"), errors="coerce")
        df["tax_amt"] = pd.to_numeric(stg_soh.get("tax_amt"), errors="coerce")
        df["freight"] = pd.to_numeric(stg_soh.get("freight"), errors="coerce")
        df["total_due"] = pd.to_numeric(stg_soh.get("total_due"), errors="coerce")
        df["source_system"] = "adventureworks"

        res = self.writer.write_dataframe(
            df, self.ds_curated_ent, "fact_sales_order", write_disposition="WRITE_TRUNCATE"
        )
        return res

    def register_structural_unpopulated(self, entity_name: str, domain: str = "enterprise") -> dict[str, Any]:
        """Register an unsupported table contract as STRUCTURAL / UNPOPULATED."""
        df = pd.DataFrame(
            [
                {
                    "entity_name": entity_name,
                    "status": "STRUCTURAL / UNPOPULATED",
                    "note": "Source dataset does not contain rows for this conceptual domain.",
                }
            ]
        )
        ds = self.ds_curated_mkt if domain == "marketplace" else self.ds_curated_ent
        tbl = f"structural_{entity_name}"
        res = self.writer.write_dataframe(df, ds, tbl, write_disposition="WRITE_TRUNCATE")
        logger.info(f"Registered structural unpopulated entity: `{ds}.{tbl}`")
        return res

"""Curated domain enterprise data contracts for downstream consumption."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ColumnContract:
    """Contract definition for a single column in a curated dataset."""

    name: str
    data_type: str
    nullable: bool = True
    description: str = ""
    is_pii: bool = False
    sensitivity_level: str = "PUBLIC"  # PUBLIC | INTERNAL | CONFIDENTIAL | RESTRICTED


@dataclass
class DataContract:
    """Enterprise data contract for a curated entity or domain dataset."""

    domain_name: str
    entity_name: str
    target_table: str
    grain: str
    primary_key: list[str]
    freshness_sla_minutes: int
    owner_team: str
    columns: list[ColumnContract] = field(default_factory=list)
    is_populated: bool = True


# Standard Curated Enterprise Data Contracts
CURATED_CONTRACTS: dict[str, DataContract] = {
    "dim_customer": DataContract(
        domain_name="CUSTOMER",
        entity_name="Enterprise Customer Master",
        target_table="curated_enterprise.dim_customer",
        grain="One row per canonical customer across enterprise systems",
        primary_key=["enterprise_customer_id"],
        freshness_sla_minutes=1440,
        owner_team="CRM & Enterprise Analytics",
        columns=[
            ColumnContract(
                "enterprise_customer_id", "STRING", False, "Canonical enterprise customer identity", False, "INTERNAL"
            ),
            ColumnContract("source_system", "STRING", False, "Origin operational source system", False, "INTERNAL"),
            ColumnContract(
                "source_customer_id", "STRING", False, "Source-native customer identifier", False, "INTERNAL"
            ),
            ColumnContract("customer_name", "STRING", True, "Full customer name", True, "CONFIDENTIAL"),
            ColumnContract("account_number", "STRING", True, "Customer account number", False, "INTERNAL"),
        ],
    ),
    "dim_product": DataContract(
        domain_name="PRODUCT",
        entity_name="Enterprise Product Catalog",
        target_table="curated_enterprise.dim_product",
        grain="One row per enterprise product SKU",
        primary_key=["enterprise_product_id"],
        freshness_sla_minutes=1440,
        owner_team="Product Architecture",
        columns=[
            ColumnContract("enterprise_product_id", "STRING", False, "Canonical product identifier", False, "INTERNAL"),
            ColumnContract("product_name", "STRING", False, "Product display name", False, "PUBLIC"),
            ColumnContract("product_number", "STRING", True, "SKU or product code", False, "INTERNAL"),
            ColumnContract("list_price", "NUMERIC", True, "Standard list price", False, "PUBLIC"),
        ],
    ),
    "fact_sales_order": DataContract(
        domain_name="SALES",
        entity_name="Sales Order Headers",
        target_table="curated_enterprise.fact_sales_order",
        grain="One row per sales order header",
        primary_key=["sales_order_id"],
        freshness_sla_minutes=60,
        owner_team="Revenue Operations",
        columns=[
            ColumnContract("sales_order_id", "STRING", False, "Sales order header key", False, "INTERNAL"),
            ColumnContract("customer_id", "STRING", False, "Customer key", False, "INTERNAL"),
            ColumnContract("order_date", "TIMESTAMP", False, "Order timestamp", False, "INTERNAL"),
            ColumnContract(
                "total_due", "NUMERIC", False, "Total order value including tax and freight", False, "CONFIDENTIAL"
            ),
        ],
    ),
}


def get_data_contract(entity_key: str) -> Optional[DataContract]:
    """Retrieve data contract by entity key."""
    return CURATED_CONTRACTS.get(entity_key.lower())

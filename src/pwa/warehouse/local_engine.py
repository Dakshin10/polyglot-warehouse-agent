"""Local SQLite query engine for offline execution against repository source datasets."""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
from typing import Optional
import pandas as pd

from pwa.settings import REPO_ROOT

logger = logging.getLogger("pwa.warehouse.local_engine")

_LOCAL_ENGINE_LOCK = threading.Lock()
_SINGLETON_ENGINE: Optional[LocalSQLiteEngine] = None


class LocalSQLiteEngine:
    """In-memory SQLite execution engine populated from local CSV and SQLite sources."""

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._init_tables()

    def _init_tables(self) -> None:
        try:
            # 1. Ingest AdventureWorks CSVs
            aw_dir = REPO_ROOT / "data" / "source" / "adventureworks"
            if aw_dir.exists():
                for csv_path in aw_dir.glob("*.csv"):
                    table_name = csv_path.stem.split(".")[-1].lower()
                    try:
                        df = pd.read_csv(csv_path)
                        df.to_sql(table_name, self.conn, if_exists="replace", index=False)
                    except Exception as e:
                        logger.debug(f"Failed to load CSV `{csv_path}` into SQLite: {e}")

            # 2. Ingest Olist CSVs if present
            olist_dir = REPO_ROOT / "data" / "source" / "olist"
            if olist_dir.exists():
                for csv_path in olist_dir.glob("*.csv"):
                    table_name = csv_path.stem.replace("olist_", "").lower()
                    try:
                        df = pd.read_csv(csv_path)
                        df.to_sql(table_name, self.conn, if_exists="replace", index=False)
                    except Exception as e:
                        logger.debug(f"Failed to load Olist CSV `{csv_path}` into SQLite: {e}")

            # 3. Create Curated Views
            curated_ddl = [
                """
                CREATE VIEW IF NOT EXISTS dim_employee AS
                SELECT
                    CAST(e.BusinessEntityID AS TEXT) AS employee_id,
                    CONCAT('adventureworks_', e.BusinessEntityID) AS employee_sk,
                    COALESCE(p.FirstName, '') || ' ' || COALESCE(p.LastName, '') AS full_name,
                    p.FirstName AS first_name,
                    p.LastName AS last_name,
                    e.JobTitle AS job_title,
                    e.Gender AS gender,
                    e.HireDate AS hire_date,
                    '100' AS department_id,
                    'Human Resources' AS department_name
                FROM employee e
                LEFT JOIN person p ON e.BusinessEntityID = p.BusinessEntityID;
                """,
                """
                CREATE VIEW IF NOT EXISTS dim_department AS
                SELECT
                    CAST(DepartmentID AS TEXT) AS department_id,
                    Name AS department_name,
                    GroupName AS department_group
                FROM department;
                """,
                """
                CREATE VIEW IF NOT EXISTS dim_customer AS
                SELECT
                    CAST(c.CustomerID AS TEXT) AS enterprise_customer_id,
                    CAST(c.CustomerID AS TEXT) AS customer_id,
                    CONCAT('adventureworks_', c.CustomerID) AS customer_sk,
                    COALESCE(p.FirstName, '') || ' ' || COALESCE(p.LastName, '') AS customer_name,
                    p.FirstName AS first_name,
                    p.LastName AS last_name
                FROM customer c
                LEFT JOIN person p ON c.PersonID = p.BusinessEntityID;
                """,
                """
                CREATE VIEW IF NOT EXISTS dim_product AS
                SELECT
                    CAST(p.ProductID AS TEXT) AS enterprise_product_id,
                    CAST(p.ProductID AS TEXT) AS product_id,
                    CONCAT('adventureworks_', p.ProductID) AS product_sk,
                    p.Name AS product_name,
                    p.ProductNumber AS product_number,
                    CAST(p.StandardCost AS REAL) AS standard_cost,
                    CAST(p.ListPrice AS REAL) AS list_price,
                    sc.Name AS subcategory_name,
                    cat.Name AS category_name,
                    p.Color AS color
                FROM product p
                LEFT JOIN productsubcategory sc ON p.ProductSubcategoryID = sc.ProductSubcategoryID
                LEFT JOIN productcategory cat ON sc.ProductCategoryID = cat.ProductCategoryID;
                """,
                """
                CREATE VIEW IF NOT EXISTS dim_product_category AS
                SELECT
                    CAST(ProductCategoryID AS TEXT) AS category_id,
                    Name AS category_name
                FROM productcategory;
                """,
                """
                CREATE VIEW IF NOT EXISTS dim_product_subcategory AS
                SELECT
                    CAST(sc.ProductSubcategoryID AS TEXT) AS subcategory_id,
                    sc.Name AS subcategory_name,
                    cat.Name AS category_name
                FROM productsubcategory sc
                LEFT JOIN productcategory cat ON sc.ProductCategoryID = cat.ProductCategoryID;
                """,
                """
                CREATE VIEW IF NOT EXISTS dim_supplier AS
                SELECT
                    CAST(BusinessEntityID AS TEXT) AS vendor_id,
                    CAST(BusinessEntityID AS TEXT) AS supplier_id,
                    CONCAT('adventureworks_vendor_', BusinessEntityID) AS supplier_sk,
                    Name AS vendor_name,
                    Name AS supplier_name,
                    CreditRating AS credit_rating,
                    ActiveFlag AS is_active
                FROM vendor;
                """,
                """
                CREATE VIEW IF NOT EXISTS fact_sales_order AS
                SELECT
                    CAST(SalesOrderID AS TEXT) AS sales_order_id,
                    SalesOrderNumber AS order_number,
                    OrderDate AS order_date,
                    CAST(CustomerID AS TEXT) AS customer_id,
                    CAST(CustomerID AS TEXT) AS enterprise_customer_id,
                    CAST(TerritoryID AS TEXT) AS territory_id,
                    CAST(SubTotal AS REAL) AS subtotal,
                    CAST(TaxAmt AS REAL) AS tax_amount,
                    CAST(Freight AS REAL) AS freight,
                    CAST(TotalDue AS REAL) AS total_due,
                    2011 AS order_year
                FROM salesorderheader;
                """,
                """
                CREATE VIEW IF NOT EXISTS fact_sales_order_item AS
                SELECT
                    CAST(SalesOrderDetailID AS TEXT) AS sales_order_item_id,
                    CAST(SalesOrderID AS TEXT) AS sales_order_id,
                    CAST(ProductID AS TEXT) AS product_id,
                    CAST(OrderQty AS INTEGER) AS order_qty,
                    CAST(OrderQty AS INTEGER) AS quantity,
                    CAST(UnitPrice AS REAL) AS unit_price,
                    CAST(LineTotal AS REAL) AS line_total,
                    CAST(LineTotal AS REAL) AS line_total_usd,
                    2011 AS order_year
                FROM salesorderdetail;
                """,
                """
                CREATE VIEW IF NOT EXISTS fact_purchase_order AS
                SELECT
                    CAST(PurchaseOrderID AS TEXT) AS purchase_order_id,
                    CAST(VendorID AS TEXT) AS vendor_id,
                    CAST(EmployeeID AS TEXT) AS employee_id,
                    CAST(SubTotal AS REAL) AS subtotal,
                    CAST(TaxAmt AS REAL) AS tax_amount,
                    CAST(Freight AS REAL) AS freight,
                    CAST(TotalDue AS REAL) AS total_due
                FROM purchaseorderheader;
                """,
                """
                CREATE VIEW IF NOT EXISTS fact_purchase_order_item AS
                SELECT
                    CAST(PurchaseOrderDetailID AS TEXT) AS purchase_order_item_id,
                    CAST(PurchaseOrderID AS TEXT) AS purchase_order_id,
                    CAST(ProductID AS TEXT) AS product_id,
                    CAST(OrderQty AS INTEGER) AS order_qty,
                    CAST(UnitPrice AS REAL) AS unit_price,
                    CAST(LineTotal AS REAL) AS line_total
                FROM purchaseorderdetail;
                """,
            ]

            for ddl in curated_ddl:
                self.conn.execute(ddl)

            logger.info("Initialized LocalSQLiteEngine in-memory views successfully.")
        except Exception as exc:
            logger.error(f"Error initializing LocalSQLiteEngine: {exc}")

    def execute_sql(self, sql: str) -> pd.DataFrame:
        """Sanitize BigQuery SQL dialects and execute on local SQLite views."""
        clean_sql = sql

        # Remove GCP project / schema qualifiers from backtick references
        # e.g. `{PROJECT}.curated_enterprise.dim_product` -> `dim_product`
        clean_sql = re.sub(r"`[^`]*\b(dim_[a-z_]+|fact_[a-z_]+)`", r"`\1`", clean_sql)
        clean_sql = re.sub(r"\bcurated_enterprise\.", "", clean_sql)
        clean_sql = re.sub(r"\bcurated_marketplace\.", "", clean_sql)
        clean_sql = re.sub(r"\bmart\.v_sales_order_line\b", "fact_sales_order_item", clean_sql)
        clean_sql = re.sub(r"\bmart\.v_product_catalog\b", "dim_product", clean_sql)
        clean_sql = re.sub(r"`", "", clean_sql)

        # Replace BigQuery types with SQLite equivalents
        clean_sql = re.sub(r"\bFLOAT64\b", "REAL", clean_sql, flags=re.IGNORECASE)
        clean_sql = re.sub(r"\bINT64\b", "INTEGER", clean_sql, flags=re.IGNORECASE)

        try:
            return pd.read_sql_query(clean_sql, self.conn)
        except Exception as exc:
            logger.warning(f"Local SQLite query execution error on SQL:\n{clean_sql}\nError: {exc}")
            raise


def get_local_sqlite_engine() -> LocalSQLiteEngine:
    """Return process-level singleton instance of LocalSQLiteEngine."""
    global _SINGLETON_ENGINE
    if _SINGLETON_ENGINE is None:
        with _LOCAL_ENGINE_LOCK:
            if _SINGLETON_ENGINE is None:
                _SINGLETON_ENGINE = LocalSQLiteEngine()
    return _SINGLETON_ENGINE

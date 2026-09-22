"""Load Google Cloud AlloyDB (PostgreSQL engine) with Nexora Core Enterprise ERP datasets.

Supports loading into AlloyDB PostgreSQL engine or local SQLite-compatible fallback database for local testing.
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


import os
import sqlite3
from pathlib import Path
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
SOURCE_BASE = DATA_DIR / "source"
DB_DIR = DATA_DIR / "db" / "alloydb"
DB_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.getenv("ALLOYDB_LOCAL_PATH", DB_DIR / "nexora_erp.sqlite"))
DDL_PATH = REPO_ROOT / "db" / "alloydb" / "schema.sql"
INDEX_PATH = REPO_ROOT / "db" / "alloydb" / "indexes.sql"
SEED_PATH = REPO_ROOT / "db" / "alloydb" / "seeds.sql"


def _get_sqlite_compat_ddl(ddl_sql: str) -> str:
    """Convert Postgres DDL features (SERIAL, TIMESTAMP WITH TIME ZONE, etc.) for local SQLite execution."""
    sql = ddl_sql.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    sql = sql.replace("BIGINT PRIMARY KEY", "INTEGER PRIMARY KEY")
    sql = sql.replace("TIMESTAMP WITH TIME ZONE", "TEXT")
    sql = sql.replace("NUMERIC(15, 2)", "REAL")
    sql = sql.replace("NUMERIC(5, 4)", "REAL")
    sql = sql.replace("BOOLEAN", "INTEGER")
    sql = sql.replace("VARCHAR(255)", "TEXT")
    sql = sql.replace("VARCHAR(150)", "TEXT")
    sql = sql.replace("VARCHAR(100)", "TEXT")
    sql = sql.replace("VARCHAR(50)", "TEXT")
    sql = sql.replace("VARCHAR(30)", "TEXT")
    sql = sql.replace("VARCHAR(20)", "TEXT")
    sql = sql.replace("VARCHAR(10)", "TEXT")
    return sql


def load_alloydb(db_path: Path = DB_PATH) -> dict:
    print(f"=== Loading AlloyDB ERP (PostgreSQL / SQLite Local) -> {db_path} ===")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Apply DDL
    pg_ddl = DDL_PATH.read_text(encoding="utf-8")
    sqlite_ddl = _get_sqlite_compat_ddl(pg_ddl)
    cursor.executescript(sqlite_ddl)

    pg_idx = INDEX_PATH.read_text(encoding="utf-8")
    cursor.executescript(pg_idx)

    conn.commit()

    tables_loaded = 0
    total_rows = 0

    # 1. Product Category
    cat_file = SOURCE_BASE / "adventureworks" / "Production.ProductCategory.csv"
    if cat_file.exists():
        df = pd.read_csv(cat_file)
        cursor.execute("DELETE FROM product_categories;")
        for _, r in df.iterrows():
            cursor.execute(
                "INSERT INTO product_categories (category_id, category_name, source_system) VALUES (?, ?, ?)",
                (int(r["ProductCategoryID"]), r["Name"], "adventureworks"),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ product_categories: {len(df)} rows")

    # 2. Product Subcategory
    subcat_file = SOURCE_BASE / "adventureworks" / "Production.ProductSubcategory.csv"
    if subcat_file.exists():
        df = pd.read_csv(subcat_file)
        cursor.execute("DELETE FROM product_subcategories;")
        for _, r in df.iterrows():
            cursor.execute(
                "INSERT INTO product_subcategories (subcategory_id, category_id, subcategory_name, source_system) VALUES (?, ?, ?, ?)",
                (int(r["ProductSubcategoryID"]), int(r["ProductCategoryID"]), r["Name"], "adventureworks"),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ product_subcategories: {len(df)} rows")

    # 3. Product
    prod_file = SOURCE_BASE / "adventureworks" / "Production.Product.csv"
    if prod_file.exists():
        df = pd.read_csv(prod_file)
        cursor.execute("DELETE FROM products;")
        for _, r in df.iterrows():
            cursor.execute(
                """INSERT INTO products
                   (product_id, product_name, product_number, color, standard_cost, list_price, subcategory_id, source_system)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(r["ProductID"]),
                    r["Name"],
                    r["ProductNumber"],
                    r.get("Color", ""),
                    float(r["StandardCost"]) if pd.notnull(r["StandardCost"]) else None,
                    float(r["ListPrice"]) if pd.notnull(r["ListPrice"]) else None,
                    int(r["ProductSubcategoryID"]) if pd.notnull(r["ProductSubcategoryID"]) else None,
                    "adventureworks",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ products: {len(df)} rows")

    # 4. Customers
    cust_file = SOURCE_BASE / "adventureworks" / "Sales.Customer.csv"
    if cust_file.exists():
        df = pd.read_csv(cust_file)
        cursor.execute("DELETE FROM customers;")
        for _, r in df.iterrows():
            cid = int(r["CustomerID"])
            cursor.execute(
                "INSERT INTO customers (customer_id, account_number, person_id, store_id, territory_id, source_system, adventureworks_customer_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    cid,
                    r["AccountNumber"],
                    int(r["PersonID"]) if pd.notnull(r["PersonID"]) else None,
                    int(r["StoreID"]) if pd.notnull(r["StoreID"]) else None,
                    int(r["TerritoryID"]) if pd.notnull(r["TerritoryID"]) else 1,
                    "adventureworks",
                    cid,
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ customers: {len(df)} rows")

    # 5. Sales Representatives
    emp_file = SOURCE_BASE / "adventureworks" / "HumanResources.Employee.csv"
    if emp_file.exists():
        df = pd.read_csv(emp_file)
        reps = df[df["JobTitle"].astype(str).str.contains("Sales", case=False, na=False)]
        if reps.empty:
            reps = df.head(5)
        cursor.execute("DELETE FROM sales_representatives;")
        for _, r in reps.iterrows():
            cursor.execute(
                "INSERT INTO sales_representatives (sales_rep_id, rep_name, job_title, source_system) VALUES (?, ?, ?, ?)",
                (int(r["BusinessEntityID"]), f"Sales Rep #{r['BusinessEntityID']}", r["JobTitle"], "adventureworks"),
            )
        tables_loaded += 1
        total_rows += len(reps)
        print(f"  ✓ sales_representatives: {len(reps)} rows")

    # 6. Sales Territories
    terr_file = SOURCE_BASE / "adventureworks" / "Sales.SalesTerritory.csv"
    if terr_file.exists():
        df = pd.read_csv(terr_file)
        cursor.execute("DELETE FROM sales_territories;")
        for _, r in df.iterrows():
            cursor.execute(
                "INSERT INTO sales_territories (territory_id, territory_name, country_code, group_name, sales_ytd, source_system) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    int(r["TerritoryID"]),
                    r["Name"],
                    r["CountryRegionCode"],
                    r["Group"],
                    float(r["SalesYTD"]) if pd.notnull(r["SalesYTD"]) else 0.0,
                    "adventureworks",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ sales_territories: {len(df)} rows")

    # 7. Sales Orders
    soh_file = SOURCE_BASE / "adventureworks" / "Sales.SalesOrderHeader.csv"
    if soh_file.exists():
        df = pd.read_csv(soh_file)
        cursor.execute("DELETE FROM sales_orders;")
        for _, r in df.iterrows():
            cursor.execute(
                """INSERT INTO sales_orders
                   (sales_order_id, revision_number, order_date, due_date, ship_date, status, online_order_flag, sales_order_number, customer_id, sales_rep_id, territory_id, sub_total, tax_amt, freight, total_due, source_system)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(r["SalesOrderID"]),
                    int(r.get("RevisionNumber", 1)),
                    str(r["OrderDate"]),
                    str(r.get("DueDate", "")),
                    str(r.get("ShipDate", "")),
                    int(r.get("Status", 5)),
                    int(r.get("OnlineOrderFlag", 0)),
                    str(r["SalesOrderNumber"]),
                    int(r["CustomerID"]),
                    int(r["SalesPersonID"]) if pd.notnull(r.get("SalesPersonID")) else None,
                    int(r.get("TerritoryID", 1)),
                    float(r["SubTotal"]) if pd.notnull(r.get("SubTotal")) else 0.0,
                    float(r["TaxAmt"]) if pd.notnull(r.get("TaxAmt")) else 0.0,
                    float(r["Freight"]) if pd.notnull(r.get("Freight")) else 0.0,
                    float(r["TotalDue"]) if pd.notnull(r.get("TotalDue")) else 0.0,
                    "adventureworks",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ sales_orders: {len(df)} rows")

    # 8. Sales Order Items
    sod_file = SOURCE_BASE / "adventureworks" / "Sales.SalesOrderDetail.csv"
    if sod_file.exists():
        df = pd.read_csv(sod_file)
        cursor.execute("DELETE FROM sales_order_items;")
        for _, r in df.iterrows():
            cursor.execute(
                """INSERT INTO sales_order_items
                   (sales_order_item_id, sales_order_id, carrier_tracking_number, order_qty, product_id, unit_price, unit_price_discount, line_total, source_system)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(r["SalesOrderDetailID"]),
                    int(r["SalesOrderID"]),
                    str(r.get("CarrierTrackingNumber", "")),
                    int(r["OrderQty"]),
                    int(r["ProductID"]),
                    float(r["UnitPrice"]),
                    float(r.get("UnitPriceDiscount", 0.0)),
                    float(r["LineTotal"]),
                    "adventureworks",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ sales_order_items: {len(df)} rows")

    # 9. Olist Marketplace Tables in AlloyDB
    ocust_file = SOURCE_BASE / "olist" / "olist_customers_dataset.csv"
    if ocust_file.exists():
        df = pd.read_csv(ocust_file)
        cursor.execute("DELETE FROM marketplace_customers;")
        for _, r in df.iterrows():
            cursor.execute(
                "INSERT INTO marketplace_customers (customer_id, customer_unique_id, zip_code_prefix, city, state, source_system) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(r["customer_id"]),
                    str(r["customer_unique_id"]),
                    int(r["customer_zip_code_prefix"]) if pd.notnull(r["customer_zip_code_prefix"]) else None,
                    str(r["customer_city"]),
                    str(r["customer_state"]),
                    "olist_marketplace",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ marketplace_customers: {len(df)} rows")

    oprod_file = SOURCE_BASE / "olist" / "olist_products_dataset.csv"
    if oprod_file.exists():
        df = pd.read_csv(oprod_file)
        cursor.execute("DELETE FROM marketplace_products;")
        for _, r in df.iterrows():
            cursor.execute(
                """INSERT INTO marketplace_products
                   (product_id, product_category_name, photos_qty, weight_g, length_cm, height_cm, width_cm, source_system)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(r["product_id"]),
                    str(r.get("product_category_name", "")),
                    int(r["product_photos_qty"]) if pd.notnull(r.get("product_photos_qty")) else None,
                    int(r["product_weight_g"]) if pd.notnull(r.get("product_weight_g")) else None,
                    int(r["product_length_cm"]) if pd.notnull(r.get("product_length_cm")) else None,
                    int(r["product_height_cm"]) if pd.notnull(r.get("product_height_cm")) else None,
                    int(r["product_width_cm"]) if pd.notnull(r.get("product_width_cm")) else None,
                    "olist_marketplace",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ marketplace_products: {len(df)} rows")

    oord_file = SOURCE_BASE / "olist" / "olist_orders_dataset.csv"
    if oord_file.exists():
        df = pd.read_csv(oord_file)
        cursor.execute("DELETE FROM marketplace_orders;")
        for _, r in df.iterrows():
            cursor.execute(
                """INSERT INTO marketplace_orders
                   (order_id, customer_id, order_status, purchase_timestamp, approved_at, delivered_carrier_date, delivered_customer_date, estimated_delivery_date, source_system)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(r["order_id"]),
                    str(r["customer_id"]),
                    str(r["order_status"]),
                    str(r["order_purchase_timestamp"]),
                    str(r.get("order_approved_at", "")),
                    str(r.get("order_delivered_carrier_date", "")),
                    str(r.get("order_delivered_customer_date", "")),
                    str(r.get("order_estimated_delivery_date", "")),
                    "olist_marketplace",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ marketplace_orders: {len(df)} rows")

    oitems_file = SOURCE_BASE / "olist" / "olist_order_items_dataset.csv"
    if oitems_file.exists():
        df = pd.read_csv(oitems_file)
        cursor.execute("DELETE FROM marketplace_order_items;")
        for _, r in df.iterrows():
            cursor.execute(
                """INSERT INTO marketplace_order_items
                   (order_id, order_item_id, product_id, seller_id, shipping_limit_date, price, freight_value, source_system)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(r["order_id"]),
                    int(r["order_item_id"]),
                    str(r["product_id"]),
                    str(r["seller_id"]),
                    str(r.get("shipping_limit_date", "")),
                    float(r["price"]),
                    float(r["freight_value"]),
                    "olist_marketplace",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ marketplace_order_items: {len(df)} rows")

    opay_file = SOURCE_BASE / "olist" / "olist_order_payments_dataset.csv"
    if opay_file.exists():
        df = pd.read_csv(opay_file)
        cursor.execute("DELETE FROM marketplace_payments;")
        for _, r in df.iterrows():
            cursor.execute(
                """INSERT INTO marketplace_payments
                   (order_id, payment_sequential, payment_type, payment_installments, payment_value, source_system)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    str(r["order_id"]),
                    int(r["payment_sequential"]),
                    str(r["payment_type"]),
                    int(r.get("payment_installments", 1)),
                    float(r["payment_value"]),
                    "olist_marketplace",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ marketplace_payments: {len(df)} rows")

    orev_file = SOURCE_BASE / "olist" / "olist_order_reviews_dataset.csv"
    if orev_file.exists():
        df = pd.read_csv(orev_file)
        cursor.execute("DELETE FROM marketplace_reviews;")
        for _, r in df.iterrows():
            cursor.execute(
                """INSERT INTO marketplace_reviews
                   (review_id, order_id, review_score, review_title, review_message, creation_date, source_system)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(r["review_id"]),
                    str(r["order_id"]),
                    int(r["review_score"]),
                    str(r.get("review_comment_title", "")),
                    str(r.get("review_comment_message", "")),
                    str(r.get("review_creation_date", "")),
                    "olist_marketplace",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ marketplace_reviews: {len(df)} rows")

    conn.commit()
    conn.close()

    summary = {"target_database": "AlloyDB", "tables_created": tables_loaded, "rows_loaded": total_rows, "failures": 0}
    print(f"=== AlloyDB Load Complete: {tables_loaded} tables, {total_rows} rows ===")
    return summary


if __name__ == "__main__":
    load_alloydb()

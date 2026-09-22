"""Load Aiven MySQL with Nexora Operational Supply Chain datasets.

Supports loading into Aiven MySQL engine or local SQLite-compatible fallback database for local testing.
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
DB_DIR = DATA_DIR / "db" / "aiven"
DB_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.getenv("AIVEN_MYSQL_LOCAL_PATH", DB_DIR / "nexora_ops.sqlite"))
DDL_PATH = REPO_ROOT / "db" / "aiven_mysql" / "schema.sql"
INDEX_PATH = REPO_ROOT / "db" / "aiven_mysql" / "indexes.sql"
SEED_PATH = REPO_ROOT / "db" / "aiven_mysql" / "seeds.sql"


def _get_sqlite_compat_ddl(ddl_sql: str) -> str:
    """Convert MySQL DDL features for local SQLite execution."""
    sql = ddl_sql.replace("BIGINT AUTO_INCREMENT PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    sql = sql.replace("INT AUTO_INCREMENT PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    sql = sql.replace("BIGINT PRIMARY KEY", "INTEGER PRIMARY KEY")
    sql = sql.replace("BIGINT", "INTEGER")
    sql = sql.replace("TINYINT", "INTEGER")
    sql = sql.replace("DATETIME", "TEXT")
    sql = sql.replace("TIMESTAMP", "TEXT")
    sql = sql.replace("DECIMAL(15, 2)", "REAL")
    sql = sql.replace("DECIMAL(10, 8)", "REAL")
    sql = sql.replace("DECIMAL(11, 8)", "REAL")
    sql = sql.replace("DECIMAL(5, 2)", "REAL")
    sql = sql.replace("VARCHAR(255)", "TEXT")
    sql = sql.replace("VARCHAR(100)", "TEXT")
    sql = sql.replace("VARCHAR(50)", "TEXT")
    sql = sql.replace("VARCHAR(30)", "TEXT")
    sql = sql.replace("VARCHAR(20)", "TEXT")
    sql = sql.replace("VARCHAR(10)", "TEXT")
    sql = sql.replace("ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;", ";")
    return sql


def load_aiven(db_path: Path = DB_PATH) -> dict:
    print(f"=== Loading Aiven MySQL (MySQL / SQLite Local) -> {db_path} ===")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Apply DDL
    mysql_ddl = DDL_PATH.read_text(encoding="utf-8")
    sqlite_ddl = _get_sqlite_compat_ddl(mysql_ddl)
    cursor.executescript(sqlite_ddl)

    mysql_idx = INDEX_PATH.read_text(encoding="utf-8")
    cursor.executescript(mysql_idx)

    mysql_seed = SEED_PATH.read_text(encoding="utf-8")
    cursor.executescript(mysql_seed)

    conn.commit()

    tables_loaded = 0
    total_rows = 0

    # 1. Suppliers (from Purchasing.Vendor.csv)
    vendor_file = SOURCE_BASE / "adventureworks" / "Purchasing.Vendor.csv"
    if vendor_file.exists():
        df = pd.read_csv(vendor_file)
        cursor.execute("DELETE FROM suppliers;")
        for _, r in df.iterrows():
            cursor.execute(
                """INSERT INTO suppliers
                   (supplier_id, account_number, supplier_name, credit_rating, preferred_vendor_status, active_flag, purchasing_web_url, source_system)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(r["BusinessEntityID"]),
                    r["AccountNumber"],
                    r["Name"],
                    int(r["CreditRating"]),
                    int(r.get("PreferredVendorStatus", 1)),
                    int(r.get("ActiveFlag", 1)),
                    str(r.get("PurchasingWebServiceURL", "")),
                    "adventureworks",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ suppliers: {len(df)} rows")

    # 2. Purchase Orders (from Purchasing.PurchaseOrderHeader.csv)
    poh_file = SOURCE_BASE / "adventureworks" / "Purchasing.PurchaseOrderHeader.csv"
    if poh_file.exists():
        df = pd.read_csv(poh_file)
        cursor.execute("DELETE FROM purchase_orders;")
        for _, r in df.iterrows():
            cursor.execute(
                """INSERT INTO purchase_orders
                   (purchase_order_id, revision_number, status, employee_id, supplier_id, ship_method_id, order_date, ship_date, sub_total, tax_amt, freight, total_due, source_system)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(r["PurchaseOrderID"]),
                    int(r.get("RevisionNumber", 1)),
                    int(r["Status"]),
                    int(r["EmployeeID"]) if pd.notnull(r.get("EmployeeID")) else None,
                    int(r["VendorID"]),
                    int(r.get("ShipMethodID", 1)),
                    str(r["OrderDate"]),
                    str(r.get("ShipDate", "")),
                    float(r["SubTotal"]) if pd.notnull(r.get("SubTotal")) else 0.0,
                    float(r["TaxAmt"]) if pd.notnull(r.get("TaxAmt")) else 0.0,
                    float(r["Freight"]) if pd.notnull(r.get("Freight")) else 0.0,
                    float(r["TotalDue"]) if pd.notnull(r.get("TotalDue")) else 0.0,
                    "adventureworks",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ purchase_orders: {len(df)} rows")

    # 3. Purchase Order Items (from Purchasing.PurchaseOrderDetail.csv)
    pod_file = SOURCE_BASE / "adventureworks" / "Purchasing.PurchaseOrderDetail.csv"
    if pod_file.exists():
        df = pd.read_csv(pod_file)
        cursor.execute("DELETE FROM purchase_order_items;")
        for _, r in df.iterrows():
            cursor.execute(
                """INSERT INTO purchase_order_items
                   (purchase_order_item_id, purchase_order_id, due_date, order_qty, product_id, unit_price, line_total, received_qty, rejected_qty, stocked_qty, source_system)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(r["PurchaseOrderDetailID"]),
                    int(r["PurchaseOrderID"]),
                    str(r.get("DueDate", "")),
                    int(r["OrderQty"]),
                    int(r["ProductID"]),
                    float(r["UnitPrice"]),
                    float(r["LineTotal"]),
                    float(r.get("ReceivedQty", 0.0)),
                    float(r.get("RejectedQty", 0.0)),
                    float(r.get("StockedQty", 0.0)),
                    "adventureworks",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ purchase_order_items: {len(df)} rows")

    # 4. Inventory
    if pod_file.exists():
        df = pd.read_csv(pod_file)
        cursor.execute("DELETE FROM inventory;")
        for idx, r in df.iterrows():
            cursor.execute(
                "INSERT INTO inventory (warehouse_id, product_id, quantity_on_hand, source_system) VALUES (?, ?, ?, ?)",
                (1, int(r["ProductID"]), int(float(r.get("StockedQty", 50.0))), "adventureworks"),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ inventory: {len(df)} rows")

    # 5. Olist Marketplace Sellers
    seller_file = SOURCE_BASE / "olist" / "olist_sellers_dataset.csv"
    if seller_file.exists():
        df = pd.read_csv(seller_file)
        cursor.execute("DELETE FROM marketplace_sellers;")
        for _, r in df.iterrows():
            cursor.execute(
                "INSERT INTO marketplace_sellers (seller_id, seller_zip_code_prefix, seller_city, seller_state, source_system) VALUES (?, ?, ?, ?, ?)",
                (
                    str(r["seller_id"]),
                    int(r["seller_zip_code_prefix"]) if pd.notnull(r["seller_zip_code_prefix"]) else None,
                    str(r["seller_city"]),
                    str(r["seller_state"]),
                    "olist_marketplace",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ marketplace_sellers: {len(df)} rows")

    # 6. Geolocation
    geo_file = SOURCE_BASE / "olist" / "olist_geolocation_dataset.csv"
    if geo_file.exists():
        df = pd.read_csv(geo_file)
        cursor.execute("DELETE FROM geolocation;")
        for _, r in df.iterrows():
            cursor.execute(
                "INSERT INTO geolocation (zip_code_prefix, lat, lng, city, state, source_system) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    int(r["geolocation_zip_code_prefix"]),
                    float(r["geolocation_lat"]),
                    float(r["geolocation_lng"]),
                    str(r["geolocation_city"]),
                    str(r["geolocation_state"]),
                    "olist_marketplace",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ geolocation: {len(df)} rows")

    conn.commit()
    conn.close()

    summary = {
        "target_database": "Aiven MySQL",
        "tables_created": tables_loaded,
        "rows_loaded": total_rows,
        "failures": 0,
    }
    print(f"=== Aiven MySQL Load Complete: {tables_loaded} tables, {total_rows} rows ===")
    return summary


if __name__ == "__main__":
    load_aiven()

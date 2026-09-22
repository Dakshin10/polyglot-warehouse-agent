"""Profile source datasets and generate source schema audit and data profiling documentation.

Target output files:
  - docs/data/source-schema-audit.md
  - docs/data/data-profiling.md
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_BASE = REPO_ROOT / "data" / "source"
DOCS_DATA_DIR = REPO_ROOT / "docs" / "data"
PROFILING_DIR = DOCS_DATA_DIR / "profiling"

DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROFILING_DIR.mkdir(parents=True, exist_ok=True)

# Dataset target mapping logic according to user requirements:
# Cloudflare D1 (SQLite): Organization, HR, CRM, Customer Support, Marketing
# Google Cloud AlloyDB (Postgres): Core Enterprise ERP (Customers, Products, Sales, Returns, Finance)
# Aiven MySQL: Operations / Supply Chain (Suppliers, Procurement, Warehouses, Inventory, Logistics)

TARGET_DB_MAP = {
    # AdventureWorks
    "HumanResources.Department.csv": ("Cloudflare D1", "departments"),
    "HumanResources.Employee.csv": ("Cloudflare D1", "employees"),
    "HumanResources.EmployeeDepartmentHistory.csv": ("Cloudflare D1", "employee_department_history"),
    "Person.Address.csv": ("AlloyDB / D1", "customer_addresses / offices"),
    "Person.Person.csv": ("Cloudflare D1 / AlloyDB", "employees / customers"),
    "Production.Product.csv": ("AlloyDB", "products"),
    "Production.ProductCategory.csv": ("AlloyDB", "product_categories"),
    "Production.ProductSubcategory.csv": ("AlloyDB", "product_subcategories"),
    "Sales.Customer.csv": ("AlloyDB", "customers"),
    "Sales.SalesOrderHeader.csv": ("AlloyDB", "sales_orders"),
    "Sales.SalesOrderDetail.csv": ("AlloyDB", "sales_order_items"),
    "Sales.SalesTerritory.csv": ("AlloyDB", "sales_territories"),
    "Purchasing.Vendor.csv": ("Aiven MySQL", "suppliers"),
    "Purchasing.PurchaseOrderHeader.csv": ("Aiven MySQL", "purchase_orders"),
    "Purchasing.PurchaseOrderDetail.csv": ("Aiven MySQL", "purchase_order_items"),
    # Olist E-Commerce
    "olist_customers_dataset.csv": ("AlloyDB / D1", "marketplace_customers"),
    "olist_orders_dataset.csv": ("AlloyDB", "marketplace_orders"),
    "olist_order_items_dataset.csv": ("AlloyDB", "marketplace_order_items"),
    "olist_order_payments_dataset.csv": ("AlloyDB", "marketplace_payments"),
    "olist_order_reviews_dataset.csv": ("AlloyDB", "marketplace_reviews"),
    "olist_products_dataset.csv": ("AlloyDB", "marketplace_products"),
    "olist_sellers_dataset.csv": ("Aiven MySQL", "marketplace_sellers"),
    "olist_geolocation_dataset.csv": ("Aiven MySQL", "geolocation"),
    "product_category_name_translation.csv": ("AlloyDB", "product_category_translation"),
    # Olist Marketing Funnel
    "olist_marketing_qualified_leads_dataset.csv": ("Cloudflare D1", "leads"),
    "olist_closed_deals_dataset.csv": ("Cloudflare D1", "lead_events"),
}

CANDIDATE_PKS = {
    "HumanResources.Department.csv": "DepartmentID",
    "HumanResources.Employee.csv": "BusinessEntityID",
    "HumanResources.EmployeeDepartmentHistory.csv": "(BusinessEntityID, DepartmentID)",
    "Person.Address.csv": "AddressID",
    "Person.Person.csv": "BusinessEntityID",
    "Production.Product.csv": "ProductID",
    "Production.ProductCategory.csv": "ProductCategoryID",
    "Production.ProductSubcategory.csv": "ProductSubcategoryID",
    "Sales.Customer.csv": "CustomerID",
    "Sales.SalesOrderHeader.csv": "SalesOrderID",
    "Sales.SalesOrderDetail.csv": "SalesOrderDetailID",
    "Sales.SalesTerritory.csv": "TerritoryID",
    "Purchasing.Vendor.csv": "BusinessEntityID",
    "Purchasing.PurchaseOrderHeader.csv": "PurchaseOrderID",
    "Purchasing.PurchaseOrderDetail.csv": "PurchaseOrderDetailID",
    "olist_customers_dataset.csv": "customer_id",
    "olist_orders_dataset.csv": "order_id",
    "olist_order_items_dataset.csv": "(order_id, order_item_id)",
    "olist_order_payments_dataset.csv": "(order_id, payment_sequential)",
    "olist_order_reviews_dataset.csv": "review_id",
    "olist_products_dataset.csv": "product_id",
    "olist_sellers_dataset.csv": "seller_id",
    "olist_geolocation_dataset.csv": "(geolocation_zip_code_prefix, geolocation_lat, geolocation_lng)",
    "product_category_name_translation.csv": "product_category_name",
    "olist_marketing_qualified_leads_dataset.csv": "mql_id",
    "olist_closed_deals_dataset.csv": "mql_id",
}

CANDIDATE_FKS = {
    "HumanResources.EmployeeDepartmentHistory.csv": "BusinessEntityID -> Employee, DepartmentID -> Department",
    "Sales.Customer.csv": "PersonID -> Person, TerritoryID -> SalesTerritory",
    "Sales.SalesOrderHeader.csv": "CustomerID -> Customer, SalesPersonID -> Employee, TerritoryID -> SalesTerritory",
    "Sales.SalesOrderDetail.csv": "SalesOrderID -> SalesOrderHeader, ProductID -> Product",
    "Production.Product.csv": "ProductSubcategoryID -> ProductSubcategory",
    "Production.ProductSubcategory.csv": "ProductCategoryID -> ProductCategory",
    "Purchasing.PurchaseOrderHeader.csv": "VendorID -> Vendor, EmployeeID -> Employee",
    "Purchasing.PurchaseOrderDetail.csv": "PurchaseOrderID -> PurchaseOrderHeader, ProductID -> Product",
    "olist_orders_dataset.csv": "customer_id -> olist_customers",
    "olist_order_items_dataset.csv": "order_id -> olist_orders, product_id -> olist_products, seller_id -> olist_sellers",
    "olist_order_payments_dataset.csv": "order_id -> olist_orders",
    "olist_order_reviews_dataset.csv": "order_id -> olist_orders",
    "olist_closed_deals_dataset.csv": "mql_id -> olist_mqls, seller_id -> olist_sellers",
}


def profile_all():
    audit_rows = []
    profiling_reports = []

    for src_dir_name in ["adventureworks", "olist", "olist_marketing"]:
        src_path = SOURCE_BASE / src_dir_name
        if not src_path.exists():
            continue

        for file_path in sorted(src_path.glob("*.csv")):
            df = pd.read_csv(file_path, low_memory=False)
            filename = file_path.name
            num_rows = len(df)
            num_cols = len(df.columns)

            target_db, target_tbl = TARGET_DB_MAP.get(filename, ("TBD", "TBD"))
            candidate_pk = CANDIDATE_PKS.get(filename, "None")
            candidate_fk = CANDIDATE_FKS.get(filename, "None")

            audit_rows.append(
                {
                    "Source": src_dir_name,
                    "File": filename,
                    "Rows": num_rows,
                    "Columns": num_cols,
                    "Candidate PK": candidate_pk,
                    "Candidate FK": candidate_fk,
                    "Target DB": target_db,
                }
            )

            # Column profile
            col_details = []
            for col in df.columns:
                null_cnt = df[col].isnull().sum()
                null_pct = round((null_cnt / num_rows) * 100, 2) if num_rows > 0 else 0
                nunique = df[col].nunique()
                dtype = str(df[col].dtype)
                col_details.append(
                    {
                        "column": col,
                        "dtype": dtype,
                        "null_count": null_cnt,
                        "null_pct": null_pct,
                        "distinct_count": nunique,
                    }
                )

            profiling_reports.append(
                {
                    "source": src_dir_name,
                    "file": filename,
                    "rows": num_rows,
                    "columns": num_cols,
                    "column_profile": col_details,
                }
            )

    # Write source-schema-audit.md
    audit_md = "# Nexora Enterprise Dataset — Source Schema Audit\n\n"
    audit_md += "This document lists the schema audit for all source files across AdventureWorks 2022, Olist E-Commerce, and Olist Marketing Funnel.\n\n"
    audit_md += "| Source | File | Rows | Columns | Candidate PK | Candidate FK | Target DB |\n"
    audit_md += "| --- | --- | --- | --- | --- | --- | --- |\n"
    for r in audit_rows:
        audit_md += f"| {r['Source']} | {r['File']} | {r['Rows']:,} | {r['Columns']} | {r['Candidate PK']} | {r['Candidate FK']} | {r['Target DB']} |\n"

    with open(DOCS_DATA_DIR / "source-schema-audit.md", "w", encoding="utf-8") as f:
        f.write(audit_md)

    # Write data-profiling.md
    profiling_md = "# Nexora Enterprise Dataset — Data Profiling Report\n\n"
    for p in profiling_reports:
        profiling_md += f"## {p['source']} / {p['file']}\n"
        profiling_md += f"- **Rows**: {p['rows']:,}\n"
        profiling_md += f"- **Columns**: {p['columns']}\n\n"
        profiling_md += "| Column | Type | Null Count | Null % | Distinct Count |\n"
        profiling_md += "| --- | --- | --- | --- | --- |\n"
        for c in p["column_profile"]:
            profiling_md += (
                f"| {c['column']} | {c['dtype']} | {c['null_count']} | {c['null_pct']}% | {c['distinct_count']} |\n"
            )
        profiling_md += "\n"

    with open(DOCS_DATA_DIR / "data-profiling.md", "w", encoding="utf-8") as f:
        f.write(profiling_md)

    print("Generated docs/data/source-schema-audit.md and docs/data/data-profiling.md successfully.")


if __name__ == "__main__":
    profile_all()

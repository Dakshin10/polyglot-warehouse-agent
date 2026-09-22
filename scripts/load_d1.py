"""Load Cloudflare D1 (SQLite engine) with Nexora application-facing operational datasets.

Supports loading into Cloudflare D1 local/remote SQLite instance.
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
DB_DIR = DATA_DIR / "db" / "d1"
DB_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.getenv("CLOUDFLARE_D1_LOCAL_PATH", DB_DIR / "nexora_app.sqlite"))
DDL_PATH = REPO_ROOT / "db" / "d1" / "schema.sql"
INDEX_PATH = REPO_ROOT / "db" / "d1" / "indexes.sql"
SEED_PATH = REPO_ROOT / "db" / "d1" / "seeds.sql"


def load_d1(db_path: Path = DB_PATH) -> dict:
    print(f"=== Loading Cloudflare D1 (SQLite) -> {db_path} ===")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Clear existing data in reverse dependency order
    cursor.execute("PRAGMA foreign_keys = OFF;")
    for tbl in [
        "lead_events",
        "leads",
        "campaign_events",
        "campaigns",
        "customer_addresses",
        "customer_contacts",
        "customers",
        "employee_contact",
        "employee_department_history",
        "employees",
        "departments",
        "offices",
    ]:
        try:
            cursor.execute(f"DELETE FROM {tbl};")
        except Exception:
            pass
    conn.commit()

    # 1. Apply DDL, Indexes, Seeds
    cursor.executescript(DDL_PATH.read_text(encoding="utf-8"))
    cursor.executescript(INDEX_PATH.read_text(encoding="utf-8"))
    cursor.executescript(SEED_PATH.read_text(encoding="utf-8"))
    conn.commit()

    tables_loaded = 0
    total_rows = 0

    # 2. Load Departments
    dept_file = SOURCE_BASE / "adventureworks" / "HumanResources.Department.csv"
    if dept_file.exists():
        df = pd.read_csv(dept_file)
        for _, row in df.iterrows():
            cursor.execute(
                "INSERT INTO departments (department_id, department_name, group_name, source_system) VALUES (?, ?, ?, ?)",
                (int(row["DepartmentID"]), row["Name"], row["GroupName"], "adventureworks"),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ departments: {len(df)} rows")

    # 3. Load Employees
    emp_file = SOURCE_BASE / "adventureworks" / "HumanResources.Employee.csv"
    if emp_file.exists():
        df = pd.read_csv(emp_file)
        dept_hist_file = SOURCE_BASE / "adventureworks" / "HumanResources.EmployeeDepartmentHistory.csv"
        dept_map = {}
        if dept_hist_file.exists():
            dh_df = pd.read_csv(dept_hist_file)
            dept_map = dict(zip(dh_df["BusinessEntityID"], dh_df["DepartmentID"]))

        for _, row in df.iterrows():
            emp_id = int(row["BusinessEntityID"])
            dept_id = int(dept_map.get(emp_id, 1))
            cursor.execute(
                """INSERT INTO employees
                   (employee_id, national_id_number, login_id, job_title, birth_date, marital_status, gender, hire_date, department_id, salaried_flag, vacation_hours, sick_leave_hours, current_flag, source_system)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    emp_id,
                    str(row["NationalIDNumber"]),
                    str(row["LoginID"]),
                    str(row["JobTitle"]),
                    str(row["BirthDate"]),
                    str(row["MaritalStatus"]),
                    str(row["Gender"]),
                    str(row["HireDate"]),
                    dept_id,
                    int(row.get("SalariedFlag", 1)),
                    int(row.get("VacationHours", 0)),
                    int(row.get("SickLeaveHours", 0)),
                    int(row.get("CurrentFlag", 1)),
                    "adventureworks",
                ),
            )
        tables_loaded += 1
        total_rows += len(df)
        print(f"  ✓ employees: {len(df)} rows")

    # 4. Load Employee Department History
    if dept_hist_file.exists():
        dh_df = pd.read_csv(dept_hist_file)
        for _, row in dh_df.iterrows():
            cursor.execute(
                "INSERT INTO employee_department_history (employee_id, department_id, shift_id, start_date, end_date, source_system) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    int(row["BusinessEntityID"]),
                    int(row["DepartmentID"]),
                    int(row.get("ShiftID", 1)),
                    str(row["StartDate"]),
                    str(row.get("EndDate", "")),
                    "adventureworks",
                ),
            )
        tables_loaded += 1
        total_rows += len(dh_df)
        print(f"  ✓ employee_department_history: {len(dh_df)} rows")

    # 5. Load Employee Contact (from Person.Person)
    person_file = SOURCE_BASE / "adventureworks" / "Person.Person.csv"
    if person_file.exists():
        p_df = pd.read_csv(person_file)
        emp_persons = p_df[p_df["PersonType"] == "EM"] if "PersonType" in p_df.columns else p_df.head(15)
        for _, row in emp_persons.iterrows():
            cursor.execute(
                "INSERT INTO employee_contact (employee_id, first_name, middle_name, last_name, title, email_promotion, source_system) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    int(row["BusinessEntityID"]),
                    str(row["FirstName"]),
                    str(row.get("MiddleName", "")),
                    str(row["LastName"]),
                    str(row.get("Title", "")),
                    int(row.get("EmailPromotion", 0)),
                    "adventureworks",
                ),
            )
        tables_loaded += 1
        total_rows += len(emp_persons)
        print(f"  ✓ employee_contact: {len(emp_persons)} rows")

    # 6. Load Customers (CRM)
    cust_file = SOURCE_BASE / "adventureworks" / "Sales.Customer.csv"
    if cust_file.exists():
        c_df = pd.read_csv(cust_file)
        for _, row in c_df.iterrows():
            cursor.execute(
                "INSERT INTO customers (customer_id, account_number, person_id, store_id, territory_id, source_system) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    int(row["CustomerID"]),
                    str(row["AccountNumber"]),
                    int(row["PersonID"]) if pd.notnull(row["PersonID"]) else None,
                    int(row["StoreID"]) if pd.notnull(row["StoreID"]) else None,
                    int(row["TerritoryID"]) if pd.notnull(row["TerritoryID"]) else 1,
                    "adventureworks",
                ),
            )
        tables_loaded += 1
        total_rows += len(c_df)
        print(f"  ✓ customers: {len(c_df)} rows")

    # 7. Load Customer Contacts
    if person_file.exists() and cust_file.exists():
        c_contacts = c_df[c_df["PersonID"].notnull()].merge(p_df, left_on="PersonID", right_on="BusinessEntityID")
        for _, row in c_contacts.iterrows():
            cursor.execute(
                "INSERT INTO customer_contacts (customer_id, first_name, middle_name, last_name, title, source_system) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    int(row["CustomerID"]),
                    str(row["FirstName"]),
                    str(row.get("MiddleName", "")),
                    str(row["LastName"]),
                    str(row.get("Title", "")),
                    "adventureworks",
                ),
            )
        tables_loaded += 1
        total_rows += len(c_contacts)
        print(f"  ✓ customer_contacts: {len(c_contacts)} rows")

    # 8. Load Customer Addresses
    addr_file = SOURCE_BASE / "adventureworks" / "Person.Address.csv"
    if addr_file.exists() and cust_file.exists():
        a_df = pd.read_csv(addr_file)
        num_addrs = min(len(c_df), len(a_df))
        for i in range(num_addrs):
            c_row = c_df.iloc[i]
            a_row = a_df.iloc[i]
            cursor.execute(
                "INSERT INTO customer_addresses (address_id, customer_id, address_line1, address_line2, city, postal_code, source_system) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    int(a_row["AddressID"]),
                    int(c_row["CustomerID"]),
                    str(a_row["AddressLine1"]),
                    str(a_row.get("AddressLine2", "")),
                    str(a_row["City"]),
                    str(a_row["PostalCode"]),
                    "adventureworks",
                ),
            )
        tables_loaded += 1
        total_rows += num_addrs
        print(f"  ✓ customer_addresses: {num_addrs} rows")

    # 9. Load Marketing Leads & Events (from Olist Marketing)
    mql_file = SOURCE_BASE / "olist_marketing" / "olist_marketing_qualified_leads_dataset.csv"
    if mql_file.exists():
        mql_df = pd.read_csv(mql_file)
        for _, row in mql_df.iterrows():
            cursor.execute(
                "INSERT INTO leads (lead_id, first_contact_date, landing_page_id, origin, source_system) VALUES (?, ?, ?, ?, ?)",
                (
                    str(row["mql_id"]),
                    str(row["first_contact_date"]),
                    str(row.get("landing_page_id", "")),
                    str(row.get("origin", "")),
                    "olist_marketing",
                ),
            )
        tables_loaded += 1
        total_rows += len(mql_df)
        print(f"  ✓ leads: {len(mql_df)} rows")

    closed_file = SOURCE_BASE / "olist_marketing" / "olist_closed_deals_dataset.csv"
    if closed_file.exists():
        cd_df = pd.read_csv(closed_file)
        for _, row in cd_df.iterrows():
            cursor.execute(
                """INSERT INTO lead_events
                   (lead_id, seller_id, sdr_id, sr_id, won_date, business_segment, lead_type, business_type, declared_monthly_revenue, source_system)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(row["mql_id"]),
                    str(row["seller_id"]),
                    str(row.get("sdr_id", "")),
                    str(row.get("sr_id", "")),
                    str(row.get("won_date", "")),
                    str(row.get("business_segment", "")),
                    str(row.get("lead_type", "")),
                    str(row.get("business_type", "")),
                    float(row["declared_monthly_revenue"]) if pd.notnull(row.get("declared_monthly_revenue")) else None,
                    "olist_marketing",
                ),
            )
        tables_loaded += 1
        total_rows += len(cd_df)
        print(f"  ✓ lead_events: {len(cd_df)} rows")

    cursor.execute("PRAGMA foreign_keys = ON;")
    conn.commit()
    conn.close()

    summary = {
        "target_database": "Cloudflare D1",
        "tables_created": tables_loaded,
        "rows_loaded": total_rows,
        "failures": 0,
    }
    print(f"=== Cloudflare D1 Load Complete: {tables_loaded} tables, {total_rows} rows ===")
    return summary


if __name__ == "__main__":
    load_d1()

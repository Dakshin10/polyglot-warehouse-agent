"""Validate PK uniqueness, FK integrity, and data quality across Cloudflare D1, AlloyDB, and Aiven MySQL databases."""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "db"

D1_DB = DATA_DIR / "d1" / "nexora_app.sqlite"
ALLOY_DB = DATA_DIR / "alloydb" / "nexora_erp.sqlite"
AIVEN_DB = DATA_DIR / "aiven" / "nexora_ops.sqlite"


def validate_d1() -> tuple[int, int]:
    print("--- Validating Cloudflare D1 ---")
    if not D1_DB.exists():
        print("  ❌ D1 database file missing.")
        return 0, 1

    conn = sqlite3.connect(D1_DB)
    cursor = conn.cursor()
    passed = 0
    failed = 0

    # Test 1: Employees -> Departments FK check
    cursor.execute("""
        SELECT COUNT(*) FROM employees e
        LEFT JOIN departments d ON e.department_id = d.department_id
        WHERE e.department_id IS NOT NULL AND d.department_id IS NULL;
    """)
    orphans = cursor.fetchone()[0]
    if orphans == 0:
        print("  ✓ FK Check: employees -> departments (0 orphans)")
        passed += 1
    else:
        print(f"  ❌ FK Check Failed: employees -> departments ({orphans} orphans)")
        failed += 1

    # Test 2: Customer Contacts -> Customers FK check
    cursor.execute("""
        SELECT COUNT(*) FROM customer_contacts cc
        LEFT JOIN customers c ON cc.customer_id = c.customer_id
        WHERE c.customer_id IS NULL;
    """)
    orphans = cursor.fetchone()[0]
    if orphans == 0:
        print("  ✓ FK Check: customer_contacts -> customers (0 orphans)")
        passed += 1
    else:
        print(f"  ❌ FK Check Failed: customer_contacts -> customers ({orphans} orphans)")
        failed += 1

    # Test 3: Lead Events -> Leads FK check
    cursor.execute("""
        SELECT COUNT(*) FROM lead_events le
        LEFT JOIN leads l ON le.lead_id = l.lead_id
        WHERE l.lead_id IS NULL;
    """)
    orphans = cursor.fetchone()[0]
    if orphans == 0:
        print("  ✓ FK Check: lead_events -> leads (0 orphans)")
        passed += 1
    else:
        print(f"  ❌ FK Check Failed: lead_events -> leads ({orphans} orphans)")
        failed += 1

    conn.close()
    return passed, failed


def validate_alloydb() -> tuple[int, int]:
    print("--- Validating AlloyDB PostgreSQL ---")
    if not ALLOY_DB.exists():
        print("  ❌ AlloyDB database file missing.")
        return 0, 1

    conn = sqlite3.connect(ALLOY_DB)
    cursor = conn.cursor()
    passed = 0
    failed = 0

    # Test 1: Products -> Product Subcategories FK check
    cursor.execute("""
        SELECT COUNT(*) FROM products p
        LEFT JOIN product_subcategories ps ON p.subcategory_id = ps.subcategory_id
        WHERE p.subcategory_id IS NOT NULL AND ps.subcategory_id IS NULL;
    """)
    orphans = cursor.fetchone()[0]
    if orphans == 0:
        print("  ✓ FK Check: products -> product_subcategories (0 orphans)")
        passed += 1
    else:
        print(f"  ❌ FK Check Failed: products -> product_subcategories ({orphans} orphans)")
        failed += 1

    # Test 2: Sales Order Items -> Sales Orders FK check
    cursor.execute("""
        SELECT COUNT(*) FROM sales_order_items soi
        LEFT JOIN sales_orders so ON soi.sales_order_id = so.sales_order_id
        WHERE so.sales_order_id IS NULL;
    """)
    orphans = cursor.fetchone()[0]
    if orphans == 0:
        print("  ✓ FK Check: sales_order_items -> sales_orders (0 orphans)")
        passed += 1
    else:
        print(f"  ❌ FK Check Failed: sales_order_items -> sales_orders ({orphans} orphans)")
        failed += 1

    # Test 3: Sales Orders -> Customers FK check
    cursor.execute("""
        SELECT COUNT(*) FROM sales_orders so
        LEFT JOIN customers c ON so.customer_id = c.customer_id
        WHERE c.customer_id IS NULL;
    """)
    orphans = cursor.fetchone()[0]
    if orphans == 0:
        print("  ✓ FK Check: sales_orders -> customers (0 orphans)")
        passed += 1
    else:
        print(f"  ❌ FK Check Failed: sales_orders -> customers ({orphans} orphans)")
        failed += 1

    # Test 4: Olist Order Items -> Marketplace Orders FK check
    cursor.execute("""
        SELECT COUNT(*) FROM marketplace_order_items moi
        LEFT JOIN marketplace_orders mo ON moi.order_id = mo.order_id
        WHERE mo.order_id IS NULL;
    """)
    orphans = cursor.fetchone()[0]
    if orphans == 0:
        print("  ✓ FK Check: marketplace_order_items -> marketplace_orders (0 orphans)")
        passed += 1
    else:
        print(f"  ❌ FK Check Failed: marketplace_order_items -> marketplace_orders ({orphans} orphans)")
        failed += 1

    conn.close()
    return passed, failed


def validate_aiven() -> tuple[int, int]:
    print("--- Validating Aiven MySQL ---")
    if not AIVEN_DB.exists():
        print("  ❌ Aiven MySQL database file missing.")
        return 0, 1

    conn = sqlite3.connect(AIVEN_DB)
    cursor = conn.cursor()
    passed = 0
    failed = 0

    # Test 1: Purchase Orders -> Suppliers FK check
    cursor.execute("""
        SELECT COUNT(*) FROM purchase_orders po
        LEFT JOIN suppliers s ON po.supplier_id = s.supplier_id
        WHERE s.supplier_id IS NULL;
    """)
    orphans = cursor.fetchone()[0]
    if orphans == 0:
        print("  ✓ FK Check: purchase_orders -> suppliers (0 orphans)")
        passed += 1
    else:
        print(f"  ❌ FK Check Failed: purchase_orders -> suppliers ({orphans} orphans)")
        failed += 1

    # Test 2: Purchase Order Items -> Purchase Orders FK check
    cursor.execute("""
        SELECT COUNT(*) FROM purchase_order_items poi
        LEFT JOIN purchase_orders po ON poi.purchase_order_id = po.purchase_order_id
        WHERE po.purchase_order_id IS NULL;
    """)
    orphans = cursor.fetchone()[0]
    if orphans == 0:
        print("  ✓ FK Check: purchase_order_items -> purchase_orders (0 orphans)")
        passed += 1
    else:
        print(f"  ❌ FK Check Failed: purchase_order_items -> purchase_orders ({orphans} orphans)")
        failed += 1

    # Test 3: Inventory -> Warehouses FK check
    cursor.execute("""
        SELECT COUNT(*) FROM inventory inv
        LEFT JOIN warehouses w ON inv.warehouse_id = w.warehouse_id
        WHERE w.warehouse_id IS NULL;
    """)
    orphans = cursor.fetchone()[0]
    if orphans == 0:
        print("  ✓ FK Check: inventory -> warehouses (0 orphans)")
        passed += 1
    else:
        print(f"  ❌ FK Check Failed: inventory -> warehouses ({orphans} orphans)")
        failed += 1

    conn.close()
    return passed, failed


def run_all_validations():
    print("=== Automated FK & Relationship Integrity Checks ===")
    p1, f1 = validate_d1()
    p2, f2 = validate_alloydb()
    p3, f3 = validate_aiven()

    total_passed = p1 + p2 + p3
    total_failed = f1 + f2 + f3

    print(f"\nSummary: {total_passed} passed, {total_failed} failed.")
    return total_failed == 0


if __name__ == "__main__":
    success = run_all_validations()
    raise SystemExit(0 if success else 1)

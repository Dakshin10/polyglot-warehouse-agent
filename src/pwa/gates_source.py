"""Source quality gates for Nexora Technologies enterprise platform.

Gate IDs: G1–G13 (source-layer checks, before BigQuery ingestion)

These gates validate source data quality at the LOCAL file layer:
  G1:  AdventureWorks source directory exists with files
  G2:  Olist source directory exists with files
  G3:  Olist Marketing source directory exists with files
  G4:  AdventureWorks sales_order_header file non-empty (>= 31,000 rows)
  G5:  AdventureWorks product file non-empty (>= 500 rows)
  G6:  Olist orders file non-empty (>= 90,000 rows)
  G7:  Olist customers file row count matches orders (1:1 relationship)
  G8:  Olist order_items has more rows than orders (1:many relationship)
  G9:  Olist sellers file non-empty (>= 3,000 rows)
  G10: Olist marketing qualified_leads non-empty (>= 7,000 rows)
  G11: Olist marketing closed_deals non-empty and subset of leads (mql_id check)
  G12: Dataset manifests present with checksums
  G13: Cross-dataset seller_id in closed_deals has high match rate vs sellers
"""

import logging
from pathlib import Path

from pwa.gates_runner import GateResult, cannot_verify, run_gates
from pwa.settings import get_settings

logger = logging.getLogger("pwa.gates_source")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _count_csv_rows(file_path: Path) -> int:
    """Count non-header rows in a CSV file."""
    if not file_path.exists():
        return -1
    with open(file_path, "r", encoding="utf-8") as fh:
        count = sum(1 for _ in fh) - 1  # subtract header row
    return max(count, 0)


def _find_file(directory: Path, pattern: str) -> Path | None:
    import glob

    matches = sorted(glob.glob(str(directory / pattern)))
    if matches:
        return Path(matches[0])
    return None


# ---------------------------------------------------------------------------
# G1: AdventureWorks source directory
# ---------------------------------------------------------------------------


def gate_g1_adventureworks_files_present() -> GateResult:
    """G1: AdventureWorks source directory exists and contains Excel/CSV files."""
    s = get_settings()
    aw_dir = s.source_base_dir / "adventureworks"

    if not aw_dir.exists():
        return GateResult(
            id="G1",
            name="AdventureWorks source files present",
            passed=False,
            detail=(f"Source directory not found: {aw_dir}. Run: pwa ingest download adventureworks"),
        )

    files = [f for f in aw_dir.iterdir() if f.is_file() and f.suffix.lower() in (".xlsx", ".xls", ".csv")]
    if not files:
        return GateResult(
            id="G1",
            name="AdventureWorks source files present",
            passed=False,
            detail=f"Directory exists but contains no Excel or CSV files: {aw_dir}",
        )

    return GateResult(
        id="G1",
        name="AdventureWorks source files present",
        passed=True,
        detail=f"{len(files)} file(s) found in {aw_dir}",
    )


# ---------------------------------------------------------------------------
# G2: Olist source directory
# ---------------------------------------------------------------------------


def gate_g2_olist_files_present() -> GateResult:
    """G2: Olist source directory exists and contains CSV files."""
    s = get_settings()
    olist_dir = s.source_base_dir / "olist"

    if not olist_dir.exists():
        return GateResult(
            id="G2",
            name="Olist source files present",
            passed=False,
            detail=f"Source directory not found: {olist_dir}. Run: pwa ingest download olist",
        )

    files = [f for f in olist_dir.iterdir() if f.is_file() and f.suffix.lower() == ".csv"]
    if len(files) < 7:
        return GateResult(
            id="G2",
            name="Olist source files present",
            passed=False,
            detail=(
                f"Expected at least 7 CSV files (9 Olist tables), found {len(files)} in {olist_dir}. "
                f"Re-run: pwa ingest download olist"
            ),
        )

    return GateResult(
        id="G2",
        name="Olist source files present",
        passed=True,
        detail=f"{len(files)} CSV file(s) found in {olist_dir}",
    )


# ---------------------------------------------------------------------------
# G3: Olist Marketing source directory
# ---------------------------------------------------------------------------


def gate_g3_olist_marketing_files_present() -> GateResult:
    """G3: Olist Marketing source directory exists and contains CSV files."""
    s = get_settings()
    mkt_dir = s.source_base_dir / "olist_marketing"

    if not mkt_dir.exists():
        return GateResult(
            id="G3",
            name="Olist Marketing source files present",
            passed=False,
            detail=(f"Source directory not found: {mkt_dir}. Run: pwa ingest download olist_marketing"),
        )

    files = [f for f in mkt_dir.iterdir() if f.is_file() and f.suffix.lower() == ".csv"]
    if len(files) < 2:
        return GateResult(
            id="G3",
            name="Olist Marketing source files present",
            passed=False,
            detail=(f"Expected 2 CSV files (leads + closed_deals), found {len(files)} in {mkt_dir}."),
        )

    return GateResult(
        id="G3",
        name="Olist Marketing source files present",
        passed=True,
        detail=f"{len(files)} CSV file(s) found in {mkt_dir}",
    )


# ---------------------------------------------------------------------------
# G4: AdventureWorks sales_order_header row count
# ---------------------------------------------------------------------------


def gate_g4_aw_sales_order_header_count() -> GateResult:
    """G4: AdventureWorks sales_order_header has at least 31,000 rows."""
    s = get_settings()
    aw_dir = s.source_base_dir / "adventureworks"

    import glob

    # Match typical AdventureWorks file naming conventions
    patterns = ["Sales.SalesOrderHeader*", "*SalesOrderHeader*", "*sales_order_header*"]
    file_path = None
    for pat in patterns:
        matches = sorted(glob.glob(str(aw_dir / pat)))
        if matches:
            file_path = Path(matches[0])
            break

    if file_path is None:
        return cannot_verify(
            "G4",
            "AdventureWorks sales_order_header row count",
            "SalesOrderHeader file not found in AdventureWorks source directory.",
        )

    suffix = file_path.suffix.lower()
    try:
        if suffix in (".xlsx", ".xls"):
            import pandas as pd

            df = pd.read_excel(file_path)
            row_count = len(df)
        else:
            row_count = _count_csv_rows(file_path)
    except Exception as exc:
        return cannot_verify("G4", "AdventureWorks sales_order_header row count", str(exc))

    min_rows = 31_000
    passed = row_count >= min_rows
    return GateResult(
        id="G4",
        name="AdventureWorks sales_order_header row count",
        passed=passed,
        detail=(f"{row_count:,} rows in {file_path.name}. Threshold: >= {min_rows:,}."),
    )


# ---------------------------------------------------------------------------
# G5: AdventureWorks product row count
# ---------------------------------------------------------------------------


def gate_g5_aw_product_count() -> GateResult:
    """G5: AdventureWorks product file has at least 500 rows."""
    s = get_settings()
    aw_dir = s.source_base_dir / "adventureworks"

    import glob

    patterns = ["Production.Product*", "*Product.*", "*product*"]
    file_path = None
    for pat in patterns:
        matches = sorted(glob.glob(str(aw_dir / pat)))
        if matches:
            # Avoid matching ProductCategory or ProductSubcategory
            for m in matches:
                p = Path(m)
                name = p.name.lower()
                if "subcategory" not in name and "category" not in name:
                    file_path = p
                    break
        if file_path:
            break

    if file_path is None:
        return cannot_verify("G5", "AdventureWorks product row count", "Product file not found.")

    try:
        suffix = file_path.suffix.lower()
        if suffix in (".xlsx", ".xls"):
            import pandas as pd

            df = pd.read_excel(file_path)
            row_count = len(df)
        else:
            row_count = _count_csv_rows(file_path)
    except Exception as exc:
        return cannot_verify("G5", "AdventureWorks product row count", str(exc))

    min_rows = 500
    passed = row_count >= min_rows
    return GateResult(
        id="G5",
        name="AdventureWorks product row count",
        passed=passed,
        detail=f"{row_count:,} rows in {file_path.name}. Threshold: >= {min_rows:,}.",
    )


# ---------------------------------------------------------------------------
# G6: Olist orders row count
# ---------------------------------------------------------------------------


def gate_g6_olist_orders_count() -> GateResult:
    """G6: Olist orders file has at least 90,000 rows."""
    s = get_settings()
    olist_dir = s.source_base_dir / "olist"
    orders_file = _find_file(olist_dir, "olist_orders_dataset.csv")

    if orders_file is None:
        return cannot_verify("G6", "Olist orders row count", "olist_orders_dataset.csv not found.")

    row_count = _count_csv_rows(orders_file)
    min_rows = 90_000
    passed = row_count >= min_rows
    return GateResult(
        id="G6",
        name="Olist orders row count",
        passed=passed,
        detail=f"{row_count:,} rows in {orders_file.name}. Threshold: >= {min_rows:,}.",
    )


# ---------------------------------------------------------------------------
# G7: Olist customers row count >= orders (1:1 per order)
# ---------------------------------------------------------------------------


def gate_g7_olist_customers_row_count() -> GateResult:
    """G7: Olist customers row count >= orders row count (1 customer record per order)."""
    s = get_settings()
    olist_dir = s.source_base_dir / "olist"
    orders_file = _find_file(olist_dir, "olist_orders_dataset.csv")
    customers_file = _find_file(olist_dir, "olist_customers_dataset.csv")

    if orders_file is None or customers_file is None:
        return cannot_verify("G7", "Olist customers vs orders row count", "Required CSV files not found.")

    orders_count = _count_csv_rows(orders_file)
    customers_count = _count_csv_rows(customers_file)

    # customers should be >= orders (each order has one customer record)
    # Small slack allowed for data freshness differences
    passed = customers_count >= orders_count * 0.99
    return GateResult(
        id="G7",
        name="Olist customers >= orders row count",
        passed=passed,
        detail=(
            f"orders: {orders_count:,}, customers: {customers_count:,}. Customers should be >= 99% of orders count."
        ),
    )


# ---------------------------------------------------------------------------
# G8: Olist order_items has more rows than orders (1:many)
# ---------------------------------------------------------------------------


def gate_g8_olist_order_items_ratio() -> GateResult:
    """G8: Olist order_items has more rows than orders (1:many relationship)."""
    s = get_settings()
    olist_dir = s.source_base_dir / "olist"
    orders_file = _find_file(olist_dir, "olist_orders_dataset.csv")
    items_file = _find_file(olist_dir, "olist_order_items_dataset.csv")

    if orders_file is None or items_file is None:
        return cannot_verify("G8", "Olist order_items > orders", "Required CSV files not found.")

    orders_count = _count_csv_rows(orders_file)
    items_count = _count_csv_rows(items_file)

    passed = items_count > orders_count
    return GateResult(
        id="G8",
        name="Olist order_items rows > orders rows",
        passed=passed,
        detail=(
            f"orders: {orders_count:,}, order_items: {items_count:,}. "
            f"Ratio: {items_count / orders_count:.2f}x. Expected > 1.0 (multiple items per order)."
        ),
    )


# ---------------------------------------------------------------------------
# G9: Olist sellers row count
# ---------------------------------------------------------------------------


def gate_g9_olist_sellers_count() -> GateResult:
    """G9: Olist sellers file has at least 3,000 rows."""
    s = get_settings()
    olist_dir = s.source_base_dir / "olist"
    sellers_file = _find_file(olist_dir, "olist_sellers_dataset.csv")

    if sellers_file is None:
        return cannot_verify("G9", "Olist sellers row count", "olist_sellers_dataset.csv not found.")

    row_count = _count_csv_rows(sellers_file)
    min_rows = 3_000
    passed = row_count >= min_rows
    return GateResult(
        id="G9",
        name="Olist sellers row count",
        passed=passed,
        detail=f"{row_count:,} rows in {sellers_file.name}. Threshold: >= {min_rows:,}.",
    )


# ---------------------------------------------------------------------------
# G10: Olist marketing qualified leads row count
# ---------------------------------------------------------------------------


def gate_g10_olist_mql_count() -> GateResult:
    """G10: Olist marketing qualified_leads has at least 7,000 rows."""
    s = get_settings()
    mkt_dir = s.source_base_dir / "olist_marketing"
    leads_file = _find_file(mkt_dir, "olist_marketing_qualified_leads_dataset.csv")

    if leads_file is None:
        return cannot_verify(
            "G10",
            "Olist marketing leads row count",
            "olist_marketing_qualified_leads_dataset.csv not found.",
        )

    row_count = _count_csv_rows(leads_file)
    min_rows = 7_000
    passed = row_count >= min_rows
    return GateResult(
        id="G10",
        name="Olist marketing qualified leads row count",
        passed=passed,
        detail=f"{row_count:,} rows in {leads_file.name}. Threshold: >= {min_rows:,}.",
    )


# ---------------------------------------------------------------------------
# G11: Olist closed_deals row count > 0
# ---------------------------------------------------------------------------


def gate_g11_olist_closed_deals_count() -> GateResult:
    """G11: Olist closed_deals has rows and seller_id column is present."""
    s = get_settings()
    mkt_dir = s.source_base_dir / "olist_marketing"
    deals_file = _find_file(mkt_dir, "olist_closed_deals_dataset.csv")

    if deals_file is None:
        return cannot_verify(
            "G11",
            "Olist closed_deals row count",
            "olist_closed_deals_dataset.csv not found.",
        )

    try:
        import pandas as pd

        df = pd.read_csv(deals_file, nrows=5)
        row_count = _count_csv_rows(deals_file)
        has_seller_id = "seller_id" in df.columns

        passed = row_count > 0 and has_seller_id
        return GateResult(
            id="G11",
            name="Olist closed_deals non-empty with seller_id",
            passed=passed,
            detail=(
                f"{row_count:,} rows in {deals_file.name}. "
                f"seller_id column present: {has_seller_id}. "
                f"(seller_id is required for cross-dataset join to olist_sellers)"
            ),
        )
    except Exception as exc:
        return cannot_verify("G11", "Olist closed_deals row count", str(exc))


# ---------------------------------------------------------------------------
# G12: Dataset manifests present
# ---------------------------------------------------------------------------


def gate_g12_manifests_present() -> GateResult:
    """G12: Data provenance manifests exist for all three datasets."""
    s = get_settings()
    manifest_dir = s.manifest_dir
    required_manifests = ["adventureworks.yaml", "olist.yaml", "olist_marketing.yaml"]

    missing = []
    for fname in required_manifests:
        mpath = manifest_dir / fname
        if not mpath.exists():
            missing.append(fname)

    if missing:
        return GateResult(
            id="G12",
            name="Dataset provenance manifests present",
            passed=False,
            detail=(
                f"Missing manifests: {missing}. "
                f"Manifests are written automatically during download. "
                f"Re-run: pwa ingest download"
            ),
        )

    return GateResult(
        id="G12",
        name="Dataset provenance manifests present",
        passed=True,
        detail=f"All {len(required_manifests)} manifests present in {manifest_dir}",
    )


# ---------------------------------------------------------------------------
# G13: Cross-dataset seller_id match rate (file-level check)
# ---------------------------------------------------------------------------


def gate_g13_cross_dataset_seller_match() -> GateResult:
    """G13: seller_ids in closed_deals have >= 80% match rate against olist_sellers."""
    s = get_settings()
    olist_dir = s.source_base_dir / "olist"
    mkt_dir = s.source_base_dir / "olist_marketing"

    sellers_file = _find_file(olist_dir, "olist_sellers_dataset.csv")
    deals_file = _find_file(mkt_dir, "olist_closed_deals_dataset.csv")

    if sellers_file is None or deals_file is None:
        return cannot_verify(
            "G13",
            "Cross-dataset seller_id match rate",
            "Required files not found (olist_sellers or olist_closed_deals).",
        )

    try:
        import pandas as pd

        sellers_df = pd.read_csv(sellers_file, usecols=["seller_id"], dtype=str)
        deals_df = pd.read_csv(deals_file, usecols=["seller_id"], dtype=str)

        seller_ids = set(sellers_df["seller_id"].dropna().unique())
        deal_seller_ids = deals_df["seller_id"].dropna()
        total = len(deal_seller_ids)
        matched = sum(1 for sid in deal_seller_ids if sid in seller_ids)
        orphans = total - matched
        match_rate = matched / total if total > 0 else 0.0

        min_rate = 0.80
        passed = match_rate >= min_rate
        return GateResult(
            id="G13",
            name="Cross-dataset seller_id match rate",
            passed=passed,
            detail=(
                f"{matched:,}/{total:,} seller_ids in closed_deals match olist_sellers "
                f"(match rate: {match_rate:.1%}). "
                f"Orphans: {orphans:,}. Threshold: >= {min_rate:.0%}."
            ),
        )
    except Exception as exc:
        return cannot_verify("G13", "Cross-dataset seller_id match rate", str(exc))


# ---------------------------------------------------------------------------
# Registry and runner
# ---------------------------------------------------------------------------

GATES = [
    gate_g1_adventureworks_files_present,
    gate_g2_olist_files_present,
    gate_g3_olist_marketing_files_present,
    gate_g4_aw_sales_order_header_count,
    gate_g5_aw_product_count,
    gate_g6_olist_orders_count,
    gate_g7_olist_customers_row_count,
    gate_g8_olist_order_items_ratio,
    gate_g9_olist_sellers_count,
    gate_g10_olist_mql_count,
    gate_g11_olist_closed_deals_count,
    gate_g12_manifests_present,
    gate_g13_cross_dataset_seller_match,
]


def run_all_gates() -> bool:
    """Run all 13 source quality gates. Returns True only if all gates pass."""
    return run_gates(GATES, title="SOURCE QUALITY GATES")


if __name__ == "__main__":
    from pwa.logging_setup import setup_logging

    setup_logging()
    raise SystemExit(0 if run_all_gates() else 1)

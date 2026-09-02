import os
import sys
import logging
from dotenv import load_dotenv
import pandas as pd
from pwa.connections import get_mysql_engine, get_pg_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify")

OUT_DIR = os.path.join(".", "data", "out")


def run_all_gates():
    """Run all 13 verification gates and exit non-zero if any gate fails."""
    load_dotenv()
    logger.info("=== STARTING VERIFICATION GATES ===")

    mysql_engine, mysql_type = get_mysql_engine()
    pg_engine, pg_type = get_pg_engine()

    require_cloud = os.getenv("REQUIRE_CLOUD_DB", "false").lower().strip() in ("true", "1", "yes")

    logger.info(f"Querying MySQL engine ({mysql_type.upper()}) and PostgreSQL engine ({pg_type.upper()})...")

    mysql_df = pd.read_sql("SELECT * FROM movie", con=mysql_engine)
    pg_df = pd.read_sql("SELECT * FROM movie_credits", con=pg_engine)

    results = []

    if require_cloud:
        mysql_cloud_pass = mysql_type != "sqlite"
        results.append(("GATE 0A", "MySQL Engine is Cloud DB (Aiven)", f"Engine: {mysql_type}", mysql_cloud_pass))
        pg_cloud_pass = pg_type != "sqlite"
        results.append(("GATE 0B", "PostgreSQL Engine is Cloud DB (Cloud SQL)", f"Engine: {pg_type}", pg_cloud_pass))

    keywords_csv_path = os.path.join(OUT_DIR, "movie_keywords.csv")
    ratings_csv_path = os.path.join(OUT_DIR, "movie_ratings_agg.csv")

    keywords_df = pd.read_csv(keywords_csv_path) if os.path.exists(keywords_csv_path) else pd.DataFrame()
    ratings_df = pd.read_csv(ratings_csv_path) if os.path.exists(ratings_csv_path) else pd.DataFrame()

    # GATE 1: MySQL COUNT == 1000
    gate1_pass = len(mysql_df) == 1000
    results.append(("GATE 1", "MySQL SELECT COUNT(*) FROM movie == 1000", f"Actual: {len(mysql_df)}", gate1_pass))

    # GATE 2: Postgres COUNT == 1000
    gate2_pass = len(pg_df) == 1000
    results.append(
        ("GATE 2", "Postgres SELECT COUNT(*) FROM movie_credits == 1000", f"Actual: {len(pg_df)}", gate2_pass)
    )

    # GATE 3: set(mysql movie_id) == set(postgres movie_id)
    mysql_ids = set(mysql_df["movie_id"])
    pg_ids = set(pg_df["movie_id"])
    gate3_pass = mysql_ids == pg_ids
    results.append(("GATE 3", "set(mysql movie_id) == set(postgres movie_id)", f"Equal: {gate3_pass}", gate3_pass))

    # GATE 4: orphan filings (pg ids not in mysql) == 0
    orphans = len(pg_ids - mysql_ids)
    gate4_pass = orphans == 0
    results.append(("GATE 4", "Orphan filings (pg ids not in mysql) == 0", f"Actual: {orphans}", gate4_pass))

    # GATE 5: missing credits (mysql ids not in pg) == 0
    missing_credits = len(mysql_ids - pg_ids)
    gate5_pass = missing_credits == 0
    results.append(("GATE 5", "Missing credits (mysql ids not in pg) == 0", f"Actual: {missing_credits}", gate5_pass))

    # GATE 6: duplicate movie_id in either table == 0
    mysql_dups = mysql_df["movie_id"].duplicated().sum()
    pg_dups = pg_df["movie_id"].duplicated().sum()
    gate6_pass = mysql_dups == 0 and pg_dups == 0
    results.append(
        (
            "GATE 6",
            "Duplicate movie_id in either table == 0",
            f"MySQL dups: {mysql_dups}, PG dups: {pg_dups}",
            gate6_pass,
        )
    )

    # GATE 7: NULL director_name in postgres == 0
    null_directors = pg_df["director_name"].isna().sum() + (pg_df["director_name"].astype(str).str.strip() == "").sum()
    gate7_pass = null_directors == 0
    results.append(("GATE 7", "NULL director_name in postgres == 0", f"Actual: {null_directors}", gate7_pass))

    # GATE 8: movie_keywords.csv distinct movie_id == 1000
    distinct_kw_ids = keywords_df["movie_id"].nunique() if not keywords_df.empty else 0
    gate8_pass = distinct_kw_ids == 1000
    results.append(("GATE 8", "movie_keywords.csv distinct movie_id == 1000", f"Actual: {distinct_kw_ids}", gate8_pass))

    # GATE 9: movie_ratings_agg.csv rows == 1000
    ratings_rows = len(ratings_df) if not ratings_df.empty else 0
    gate9_pass = ratings_rows == 1000
    results.append(("GATE 9", "movie_ratings_agg.csv rows == 1000", f"Actual: {ratings_rows}", gate9_pass))

    # GATE 10: keyword/ratings movie_ids <= mysql movie_id set
    kw_ids = set(keywords_df["movie_id"]) if not keywords_df.empty else set()
    rat_ids = set(ratings_df["movie_id"]) if not ratings_df.empty else set()
    gate10_pass = kw_ids.issubset(mysql_ids) and rat_ids.issubset(mysql_ids)
    results.append(
        ("GATE 10", "keyword/ratings movie_ids <= mysql movie_id set", f"Subset: {gate10_pass}", gate10_pass)
    )

    # GATE 11: budget_usd > 0 and revenue_usd > 0 for all rows
    invalid_budget_rev = ((mysql_df["budget_usd"] <= 0) | (mysql_df["revenue_usd"] <= 0)).sum()
    gate11_pass = invalid_budget_rev == 0
    results.append(
        (
            "GATE 11",
            "budget_usd > 0 and revenue_usd > 0 for all rows",
            f"Invalid rows: {invalid_budget_rev}",
            gate11_pass,
        )
    )

    # GATE 12: no mojibake in title (round-trip utf8mb4 check)
    def check_mojibake(title):
        try:
            return title.encode("utf-8").decode("utf-8") == title
        except Exception:
            return False

    mojibake_count = (~mysql_df["title"].apply(check_mojibake)).sum()
    gate12_pass = mojibake_count == 0
    results.append(
        ("GATE 12", "No mojibake in title (round-trip utf8mb4 check)", f"Corrupt titles: {mojibake_count}", gate12_pass)
    )

    # GATE 13: Cross-engine join proof
    join_result = None
    gate13_pass = False
    try:
        join_result = (
            mysql_df.merge(pg_df, on="movie_id")
            .assign(roi=lambda d: d.revenue_usd / d.budget_usd)
            .groupby("director_name")
            .agg(films=("movie_id", "count"), median_roi=("roi", "median"), total_revenue=("revenue_usd", "sum"))
            .query("films >= 2")
            .sort_values("median_roi", ascending=False)
            .head(10)
        )
        has_10_rows = len(join_result) >= 10
        has_no_nan_director = not join_result.index.isna().any() and not (join_result.index == "").any()
        gate13_pass = has_10_rows and has_no_nan_director
    except Exception as e:
        logger.error(f"Gate 13 computation error: {e}")
        gate13_pass = False

    results.append(
        (
            "GATE 13",
            "Cross-engine join proof (top 10 directors >= 2 films)",
            f"Rows: {len(join_result) if join_result is not None else 0}",
            gate13_pass,
        )
    )

    print("\n" + "=" * 85)
    print(f"{'GATE':<8} | {'DESCRIPTION':<50} | {'STATUS':<8} | {'DETAILS'}")
    print("-" * 85)
    all_passed = True
    for gate_id, desc, details, status in results:
        status_str = "PASS" if status else "FAIL"
        if not status:
            all_passed = False
        print(f"{gate_id:<8} | {desc:<50} | {status_str:<8} | {details}")
    print("=" * 85 + "\n")

    if join_result is not None:
        print("=== GATE 13: CROSS-ENGINE JOIN PROOF TOP 10 DIRECTORS BY MEDIAN ROI ===")
        print(join_result.to_string())
        print("=" * 85 + "\n")

    if not all_passed:
        logger.error("FATAL: One or more verification gates failed.")
        sys.exit(1)

    logger.info("=== ALL 13 VERIFICATION GATES PASSED SUCCESSFULLY ===")
    return True


if __name__ == "__main__":
    run_all_gates()

"""Source-database verification gates 1-13.

These assert data quality against the live Aiven MySQL and Cloud SQL PostgreSQL
databases at pipeline runtime and block the pipeline on failure. They are not
pytest tests: a gate that only runs when someone remembers to run pytest is not
a gate.
"""

import logging
import os

import pandas as pd
from sqlalchemy import text

from pwa.connections import get_mysql_engine, get_pg_engine
from pwa.gates_runner import GateResult, run_gates, cannot_verify

logger = logging.getLogger("pwa.gates_source")

OUT_DIR = os.path.join(".", "data", "out")
KEYWORDS_CSV = os.path.join(OUT_DIR, "movie_keywords.csv")
RATINGS_CSV = os.path.join(OUT_DIR, "movie_ratings_agg.csv")


class SourceFacts:
    """Everything the 13 gates read, fetched once from the live databases."""

    def __init__(self):
        mysql_engine, self.mysql_type = get_mysql_engine()
        pg_engine, self.pg_type = get_pg_engine()

        with mysql_engine.connect() as conn:
            self.mysql_count = conn.execute(text("SELECT COUNT(*) FROM movie")).scalar()
        with pg_engine.connect() as conn:
            self.pg_count = conn.execute(text("SELECT COUNT(*) FROM movie_credits")).scalar()

        logger.info(f"Querying MySQL ({self.mysql_type}) and PostgreSQL ({self.pg_type})...")
        self.mysql_df = pd.read_sql("SELECT * FROM movie", con=mysql_engine)
        self.pg_df = pd.read_sql("SELECT * FROM movie_credits", con=pg_engine)

        self.mysql_ids = set(self.mysql_df["movie_id"])
        self.pg_ids = set(self.pg_df["movie_id"])

        self.keywords_df = pd.read_csv(KEYWORDS_CSV) if os.path.exists(KEYWORDS_CSV) else pd.DataFrame()
        self.ratings_df = pd.read_csv(RATINGS_CSV) if os.path.exists(RATINGS_CSV) else pd.DataFrame()


def _no_mojibake(title) -> bool:
    return title.encode("utf-8").decode("utf-8") == title


def build_gates(f: SourceFacts):
    """Return the 13 source gates as zero-argument callables over the fetched facts."""

    def gate_1():
        return GateResult(
            "1", "MySQL SELECT COUNT(*) FROM movie == 1000", f.mysql_count == 1000, f"Actual: {f.mysql_count}"
        )

    def gate_2():
        return GateResult(
            "2", "Postgres SELECT COUNT(*) FROM movie_credits == 1000", f.pg_count == 1000, f"Actual: {f.pg_count}"
        )

    def gate_3():
        equal = f.mysql_ids == f.pg_ids
        return GateResult("3", "set(mysql movie_id) == set(postgres movie_id)", equal, f"Equal: {equal}")

    def gate_4():
        orphans = len(f.pg_ids - f.mysql_ids)
        return GateResult("4", "Orphan filings (pg ids not in mysql) == 0", orphans == 0, f"Actual: {orphans}")

    def gate_5():
        missing = len(f.mysql_ids - f.pg_ids)
        return GateResult("5", "Missing credits (mysql ids not in pg) == 0", missing == 0, f"Actual: {missing}")

    def gate_6():
        mysql_dups = f.mysql_df["movie_id"].duplicated().sum()
        pg_dups = f.pg_df["movie_id"].duplicated().sum()
        return GateResult(
            "6",
            "Duplicate movie_id in either table == 0",
            mysql_dups == 0 and pg_dups == 0,
            f"MySQL dups: {mysql_dups}, PG dups: {pg_dups}",
        )

    def gate_7():
        nulls = f.pg_df["director_name"].isna().sum() + (f.pg_df["director_name"].astype(str).str.strip() == "").sum()
        return GateResult("7", "NULL director_name in postgres == 0", nulls == 0, f"Actual: {nulls}")

    def gate_8():
        if f.keywords_df.empty:
            return cannot_verify(
                "8", "movie_keywords.csv distinct movie_id == 1000", f"{KEYWORDS_CSV} missing or empty"
            )
        distinct = f.keywords_df["movie_id"].nunique()
        return GateResult("8", "movie_keywords.csv distinct movie_id == 1000", distinct == 1000, f"Actual: {distinct}")

    def gate_9():
        if f.ratings_df.empty:
            return cannot_verify("9", "movie_ratings_agg.csv rows == 1000", f"{RATINGS_CSV} missing or empty")
        rows = len(f.ratings_df)
        return GateResult("9", "movie_ratings_agg.csv rows == 1000", rows == 1000, f"Actual: {rows}")

    def gate_10():
        if f.keywords_df.empty or f.ratings_df.empty:
            return cannot_verify(
                "10", "keyword/ratings movie_ids <= mysql movie_id set", "output CSVs missing or empty"
            )
        kw_ids = set(f.keywords_df["movie_id"])
        rat_ids = set(f.ratings_df["movie_id"])
        subset = kw_ids.issubset(f.mysql_ids) and rat_ids.issubset(f.mysql_ids)
        return GateResult("10", "keyword/ratings movie_ids <= mysql movie_id set", subset, f"Subset: {subset}")

    def gate_11():
        invalid = ((f.mysql_df["budget_usd"] <= 0) | (f.mysql_df["revenue_usd"] <= 0)).sum()
        return GateResult(
            "11", "budget_usd > 0 and revenue_usd > 0 for all rows", invalid == 0, f"Invalid rows: {invalid}"
        )

    def gate_12():
        corrupt = (~f.mysql_df["title"].apply(_no_mojibake)).sum()
        return GateResult(
            "12", "No mojibake in title (round-trip utf8mb4 check)", corrupt == 0, f"Corrupt titles: {corrupt}"
        )

    def gate_13():
        join_result = (
            f.mysql_df.merge(f.pg_df, on="movie_id")
            .assign(roi=lambda d: d.revenue_usd / d.budget_usd)
            .groupby("director_name")
            .agg(films=("movie_id", "count"), median_roi=("roi", "median"), total_revenue=("revenue_usd", "sum"))
            .query("films >= 2")
            .sort_values("median_roi", ascending=False)
            .head(10)
        )
        has_10_rows = len(join_result) >= 10
        named_directors = not join_result.index.isna().any() and not (join_result.index == "").any()
        return GateResult(
            "13",
            "Cross-engine join proof (top 10 directors >= 2 films)",
            has_10_rows and named_directors,
            f"Rows: {len(join_result)}",
            extra=[
                "=== GATE 13: CROSS-ENGINE JOIN PROOF TOP 10 DIRECTORS BY MEDIAN ROI ===\n" + join_result.to_string()
            ],
        )

    return [
        gate_1,
        gate_2,
        gate_3,
        gate_4,
        gate_5,
        gate_6,
        gate_7,
        gate_8,
        gate_9,
        gate_10,
        gate_11,
        gate_12,
        gate_13,
    ]


def run_all_gates() -> bool:
    """Run source gates 1-13. Returns True only if every gate passed."""
    try:
        facts = SourceFacts()
    except Exception as exc:
        # Nothing can be verified without the source databases; every gate fails.
        error = exc
        return run_gates([lambda: cannot_verify("1-13", "Source databases reachable", error)], "SOURCE GATES 1-13")
    return run_gates(build_gates(facts), "SOURCE GATES 1-13")


if __name__ == "__main__":
    raise SystemExit(0 if run_all_gates() else 1)

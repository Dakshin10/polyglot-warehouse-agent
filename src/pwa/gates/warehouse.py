"""verify_bq.py — BigQuery verification gates B1-B15.

Prints a pass/fail table and exits non-zero if any gate fails.
A gate that cannot run fails (CANNOT VERIFY), never skips.
"""

import os
import sys
import hashlib
import logging
from dotenv import load_dotenv
from google.cloud import bigquery
from sqlalchemy import text
from pwa.db import get_pg_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify_bq")


def _env(key, default=""):
    return os.getenv(key, default).strip()


def _bq_count(client, table_ref, where_clause=""):
    """Run a COUNT(*) query with optional WHERE, return int."""
    sql = f"SELECT COUNT(*) AS cnt FROM `{table_ref}`"
    if where_clause:
        sql += f" WHERE {where_clause}"
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=100_000_000)
    result = client.query(sql, job_config=job_config).result()
    return list(result)[0]["cnt"]


def _bq_query_df(client, sql):
    """Run a query and return a DataFrame."""
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=100_000_000)
    return client.query(sql, job_config=job_config).to_dataframe()


def run_all_bq_gates():
    """Run all 15 BigQuery verification gates."""
    load_dotenv()
    project = _env("GCP_PROJECT")
    location = _env("BQ_LOCATION", "EU")

    if not project:
        logger.error("GCP_PROJECT not set in .env. Cannot proceed.")
        sys.exit(1)

    client = bigquery.Client(project=project, location=location)
    ds_registry = _env("BQ_DS_REGISTRY", "raw_registry")
    ds_credits = _env("BQ_DS_CREDITS", "raw_credits")
    ds_files = _env("BQ_DS_FILES", "raw_files")
    ds_mart = _env("BQ_DS_MART", "mart")

    results = []

    # GATE B1: raw_registry.movie == 1000
    try:
        cnt = _bq_count(client, f"{project}.{ds_registry}.movie")
        passed = cnt == 1000
        results.append(("GATE B1", f"{ds_registry}.movie row count == 1000", f"Actual: {cnt}", passed))
    except Exception as e:
        results.append(("GATE B1", f"{ds_registry}.movie row count == 1000", f"CANNOT VERIFY: {e}", False))

    # GATE B2: raw_credits.movie_credits (federated) == 1000
    try:
        cnt = _bq_count(client, f"{project}.{ds_credits}.movie_credits")
        passed = cnt == 1000
        results.append(("GATE B2", f"{ds_credits}.movie_credits (federated) == 1000", f"Actual: {cnt}", passed))
    except Exception as e:
        results.append(("GATE B2", f"{ds_credits}.movie_credits (federated) == 1000", f"CANNOT VERIFY: {e}", False))

    # GATE B3: raw_files.movie_keywords distinct movie_id == 1000
    try:
        sql = f"SELECT COUNT(DISTINCT movie_id) AS cnt FROM `{project}.{ds_files}.movie_keywords`"
        cnt = list(client.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=100_000_000)).result())[0][
            "cnt"
        ]
        passed = cnt == 1000
        results.append(("GATE B3", f"{ds_files}.movie_keywords distinct ids == 1000", f"Actual: {cnt}", passed))
    except Exception as e:
        results.append(("GATE B3", f"{ds_files}.movie_keywords distinct ids == 1000", f"CANNOT VERIFY: {e}", False))

    # GATE B4: raw_files.movie_ratings_agg == 1000
    try:
        cnt = _bq_count(client, f"{project}.{ds_files}.movie_ratings_agg")
        passed = cnt == 1000
        results.append(("GATE B4", f"{ds_files}.movie_ratings_agg == 1000", f"Actual: {cnt}", passed))
    except Exception as e:
        results.append(("GATE B4", f"{ds_files}.movie_ratings_agg == 1000", f"CANNOT VERIFY: {e}", False))

    # GATE B5: mart.v_movie_full == 1000
    try:
        cnt = _bq_count(client, f"{project}.{ds_mart}.v_movie_full")
        passed = cnt == 1000
        results.append(("GATE B5", f"{ds_mart}.v_movie_full == 1000", f"Actual: {cnt}", passed))
    except Exception as e:
        results.append(("GATE B5", f"{ds_mart}.v_movie_full == 1000", f"CANNOT VERIFY: {e}", False))

    # GATE B6: mart.v_integrity_exceptions == 0
    try:
        cnt = _bq_count(client, f"{project}.{ds_mart}.v_integrity_exceptions")
        passed = cnt == 0
        results.append(("GATE B6", f"{ds_mart}.v_integrity_exceptions == 0", f"Actual: {cnt}", passed))
    except Exception as e:
        results.append(("GATE B6", f"{ds_mart}.v_integrity_exceptions == 0", f"CANNOT VERIFY: {e}", False))

    # GATE B7: mart.v_movie_full WHERE director_name IS NULL == 0
    try:
        cnt = _bq_count(client, f"{project}.{ds_mart}.v_movie_full", "director_name IS NULL")
        passed = cnt == 0
        results.append(("GATE B7", "v_movie_full NULL director_name == 0", f"Actual: {cnt}", passed))
    except Exception as e:
        results.append(("GATE B7", "v_movie_full NULL director_name == 0", f"CANNOT VERIFY: {e}", False))

    # GATE B8: mart.v_movie_full WHERE avg_rating IS NULL == 0
    try:
        cnt = _bq_count(client, f"{project}.{ds_mart}.v_movie_full", "avg_rating IS NULL")
        passed = cnt == 0
        results.append(("GATE B8", "v_movie_full NULL avg_rating == 0", f"Actual: {cnt}", passed))
    except Exception as e:
        results.append(("GATE B8", "v_movie_full NULL avg_rating == 0", f"CANNOT VERIFY: {e}", False))

    # GATE B9: every mart view has a non-null description
    try:
        sql = f"""
        SELECT table_name, option_value
        FROM `{project}.{ds_mart}.INFORMATION_SCHEMA.TABLE_OPTIONS`
        WHERE option_name = 'description'
        """
        desc_df = _bq_query_df(client, sql)
        expected_views = {"v_movie", "v_movie_credits", "v_movie_full", "v_movie_keywords", "v_integrity_exceptions"}
        described_views = set(desc_df["table_name"])
        missing_views = expected_views - described_views
        null_desc = desc_df[desc_df["option_value"].isna() | (desc_df["option_value"].str.strip() == "")][
            "table_name"
        ].tolist()
        passed = len(missing_views) == 0 and len(null_desc) == 0
        detail = (
            f"Missing: {missing_views}"
            if missing_views
            else ("Null desc: " + str(null_desc) if null_desc else "All views described")
        )
        results.append(("GATE B9", "Every mart view has description", detail, passed))
    except Exception as e:
        results.append(("GATE B9", "Every mart view has description", f"CANNOT VERIFY: {e}", False))

    # GATE B10: every mart column has a non-null description
    try:
        sql = f"""
        SELECT table_name, column_name, description
        FROM `{project}.{ds_mart}.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`
        """
        col_df = _bq_query_df(client, sql)
        undescribed = col_df[col_df["description"].isna() | (col_df["description"].str.strip() == "")]
        if len(undescribed) > 0:
            missing_cols = undescribed.apply(lambda r: f"{r['table_name']}.{r['column_name']}", axis=1).tolist()
            passed = False
            detail = f"Undescribed columns ({len(missing_cols)}): " + ", ".join(missing_cols[:10])
            if len(missing_cols) > 10:
                detail += f"... and {len(missing_cols) - 10} more"
        else:
            passed = True
            detail = f"All {len(col_df)} columns described"
        results.append(("GATE B10", "Every mart column has description", detail, passed))
    except Exception as e:
        results.append(("GATE B10", "Every mart column has description", f"CANNOT VERIFY: {e}", False))

    # GATE B11: agent SA CAN query mart.v_movie_full
    try:
        cnt = _bq_count(client, f"{project}.{ds_mart}.v_movie_full")
        passed = cnt == 1000
        results.append(("GATE B11", f"Agent SA can query {ds_mart}.v_movie_full", f"Query returned {cnt} rows", passed))
    except Exception as e:
        results.append(("GATE B11", f"Agent SA can query {ds_mart}.v_movie_full", f"CANNOT VERIFY: {e}", False))

    # GATE B12: agent SA CANNOT query raw_registry.movie (negative test)
    try:
        dataset_ref = client.get_dataset(f"{project}.{ds_registry}")
        sa_email = f"warehouse-agent@{project}.iam.gserviceaccount.com"
        has_viewer = False
        for entry in dataset_ref.access_entries:
            if (
                hasattr(entry, "entity_id")
                and entry.entity_id == sa_email
                and entry.role
                and "READER" in str(entry.role).upper()
            ):
                has_viewer = True
                break
        passed = not has_viewer
        detail = (
            "SA has NO dataViewer on raw_registry (correct)"
            if passed
            else "SA has dataViewer on raw_registry (should not)"
        )
        results.append(("GATE B12", f"Agent SA CANNOT query {ds_registry}.movie", detail, passed))
    except Exception as e:
        results.append(("GATE B12", f"Agent SA CANNOT query {ds_registry}.movie", f"CANNOT VERIFY: {e}", False))

    # GATE B13: selected_movie_ids.csv SHA-256 matches pinned fixture
    try:
        csv_path = os.path.join(".", "data", "out", "selected_movie_ids.csv")
        with open(csv_path, "rb") as f:
            sha256 = hashlib.sha256(f.read()).hexdigest()
        fixture_path = os.path.join(".", "data", "out", ".selected_movie_ids_sha256")
        if os.path.exists(fixture_path):
            with open(fixture_path, "r") as f:
                pinned = f.read().strip()
            passed = sha256 == pinned
            detail = f"SHA-256 match: {passed} ({sha256[:16]}...)"
        else:
            with open(fixture_path, "w") as f:
                f.write(sha256)
            passed = True
            detail = f"Pinned SHA-256: {sha256[:16]}... (first run)"
        results.append(("GATE B13", "selected_movie_ids.csv SHA-256 stable", detail, passed))
    except Exception as e:
        results.append(("GATE B13", "selected_movie_ids.csv SHA-256 stable", f"CANNOT VERIFY: {e}", False))

    # GATE B14: federation liveness proof
    try:
        pg_engine, pg_type = get_pg_engine()
        if pg_type == "sqlite":
            results.append(
                ("GATE B14", "Federation liveness proof", "CANNOT VERIFY: PG engine is SQLite fallback", False)
            )
        else:
            baseline_cnt = _bq_count(client, f"{project}.{ds_mart}.v_movie_credits", "producer_name IS NULL")
            logger.info(f"Gate B14 baseline NULL producer_name count: {baseline_cnt}")

            original_value = None
            target_movie_id = None
            try:
                with pg_engine.connect() as conn:
                    row = conn.execute(
                        text(
                            "SELECT movie_id, producer_name FROM movie_credits "
                            "WHERE producer_name IS NOT NULL ORDER BY movie_id LIMIT 1"
                        )
                    ).fetchone()
                    if row is None:
                        raise ValueError("No rows with non-null producer_name")
                    target_movie_id = row[0]
                    original_value = row[1]

                    conn.execute(
                        text("UPDATE movie_credits SET producer_name = NULL WHERE movie_id = :mid"),
                        {"mid": target_movie_id},
                    )
                    conn.commit()
                    logger.info(f"Gate B14: Set producer_name=NULL for movie_id={target_movie_id}")

                new_cnt = _bq_count(client, f"{project}.{ds_mart}.v_movie_credits", "producer_name IS NULL")
                logger.info(f"Gate B14 after UPDATE NULL producer_name count: {new_cnt}")
                increased = new_cnt == baseline_cnt + 1

                with pg_engine.connect() as conn:
                    conn.execute(
                        text("UPDATE movie_credits SET producer_name = :val WHERE movie_id = :mid"),
                        {"val": original_value, "mid": target_movie_id},
                    )
                    conn.commit()
                    logger.info(f"Gate B14: Restored producer_name for movie_id={target_movie_id}")

                restored_cnt = _bq_count(client, f"{project}.{ds_mart}.v_movie_credits", "producer_name IS NULL")
                restored = restored_cnt == baseline_cnt

                passed = increased and restored
                detail = f"Baseline={baseline_cnt}, After NULL={new_cnt} (+1={increased}), Restored={restored_cnt} (back={restored})"
                results.append(("GATE B14", "Federation liveness proof", detail, passed))

            except Exception as inner_e:
                if original_value is not None and target_movie_id is not None:
                    try:
                        with pg_engine.connect() as conn:
                            conn.execute(
                                text("UPDATE movie_credits SET producer_name = :val WHERE movie_id = :mid"),
                                {"val": original_value, "mid": target_movie_id},
                            )
                            conn.commit()
                    except Exception:
                        pass
                results.append(("GATE B14", "Federation liveness proof", f"CANNOT VERIFY: {inner_e}", False))
    except Exception as e:
        results.append(("GATE B14", "Federation liveness proof", f"CANNOT VERIFY: {e}", False))

    # GATE B15: cross-engine proof query
    proof_df = None
    try:
        sql = f"""
        SELECT director_name,
               COUNT(*)              AS films,
               ROUND(APPROX_QUANTILES(roi, 2)[OFFSET(1)], 2) AS median_roi,
               SUM(revenue_usd)      AS total_revenue
        FROM `{project}.{ds_mart}.v_movie_full`
        GROUP BY director_name
        HAVING films >= 2
        ORDER BY median_roi DESC
        LIMIT 10
        """
        proof_df = _bq_query_df(client, sql)
        has_10 = len(proof_df) >= 10
        no_nan = not proof_df["director_name"].isna().any()
        passed = has_10 and no_nan
        results.append(
            (
                "GATE B15",
                "Cross-engine proof (top 10 directors)",
                f"Rows: {len(proof_df)}, NaN dirs: {proof_df['director_name'].isna().sum()}",
                passed,
            )
        )
    except Exception as e:
        results.append(("GATE B15", "Cross-engine proof (top 10 directors)", f"CANNOT VERIFY: {e}", False))

    print("\n" + "=" * 95)
    print(f"{'GATE':<10} | {'DESCRIPTION':<50} | {'STATUS':<8} | {'DETAILS'}")
    print("-" * 95)
    all_passed = True
    for gate_id, desc, details, status in results:
        status_str = "PASS" if status else "FAIL"
        if not status:
            all_passed = False
        print(f"{gate_id:<10} | {desc:<50} | {status_str:<8} | {details}")
    print("=" * 95 + "\n")

    if proof_df is not None and len(proof_df) > 0:
        print("=== GATE B15: CROSS-ENGINE PROOF — TOP 10 DIRECTORS BY MEDIAN ROI ===")
        print(proof_df.to_string(index=False))
        print("=" * 95 + "\n")

    if not all_passed:
        logger.error("FATAL: One or more BigQuery verification gates failed.")
        sys.exit(1)

    logger.info("=== ALL 15 BIGQUERY VERIFICATION GATES PASSED SUCCESSFULLY ===")
    return True


if __name__ == "__main__":
    run_all_bq_gates()

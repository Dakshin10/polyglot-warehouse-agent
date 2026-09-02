"""BigQuery verification gates B1-B15.

Asserted against the live warehouse at pipeline runtime. A gate that cannot run
fails with CANNOT VERIFY; it never skips.
"""

import hashlib
import logging
import os

from google.cloud import bigquery
from sqlalchemy import text

from pwa.connections import get_bq_client, get_pg_engine
from pwa.gates_runner import GateResult, run_gates, cannot_verify
from pwa.settings import get_settings

logger = logging.getLogger("pwa.gates_bigquery")

MAX_BYTES_BILLED = 100_000_000
SELECTED_IDS_CSV = os.path.join(".", "data", "out", "selected_movie_ids.csv")
SELECTED_IDS_PIN = os.path.join(".", "data", "out", ".selected_movie_ids_sha256")

MART_VIEWS = ("v_movie", "v_movie_credits", "v_movie_full", "v_movie_keywords", "v_integrity_exceptions")


def _job_config():
    return bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES_BILLED)


def _count(client, table_ref, where_clause=""):
    """COUNT(*) on a table or view, with an optional WHERE clause."""
    sql = f"SELECT COUNT(*) AS cnt FROM `{table_ref}`"
    if where_clause:
        sql += f" WHERE {where_clause}"
    return list(client.query(sql, job_config=_job_config()).result())[0]["cnt"]


def _query_df(client, sql):
    return client.query(sql, job_config=_job_config()).to_dataframe()


def _count_gate(client, gate_id, name, table, expected, where="", distinct_column="", detail_label="Actual"):
    """Build a gate asserting a row count (or distinct count) equals `expected`."""

    def run():
        try:
            if distinct_column:
                sql = f"SELECT COUNT(DISTINCT {distinct_column}) AS cnt FROM `{table}`"
                cnt = list(client.query(sql, job_config=_job_config()).result())[0]["cnt"]
            else:
                cnt = _count(client, table, where)
        except Exception as e:
            return cannot_verify(gate_id, name, e)
        return GateResult(gate_id, name, cnt == expected, f"{detail_label}: {cnt}")

    return run


def _data_gates(client, s):
    """B1-B8 and B11: row counts and completeness across the four datasets."""
    p = s.gcp_project
    registry, credits = f"{p}.{s.bq_ds_registry}", f"{p}.{s.bq_ds_credits}"
    files, mart = f"{p}.{s.bq_ds_files}", f"{p}.{s.bq_ds_mart}"

    return [
        _count_gate(client, "B1", f"{s.bq_ds_registry}.movie row count == 1000", f"{registry}.movie", 1000),
        _count_gate(
            client,
            "B2",
            f"{s.bq_ds_credits}.movie_credits (federated) == 1000",
            f"{credits}.movie_credits",
            1000,
        ),
        _count_gate(
            client,
            "B3",
            f"{s.bq_ds_files}.movie_keywords distinct ids == 1000",
            f"{files}.movie_keywords",
            1000,
            distinct_column="movie_id",
        ),
        _count_gate(client, "B4", f"{s.bq_ds_files}.movie_ratings_agg == 1000", f"{files}.movie_ratings_agg", 1000),
        _count_gate(client, "B5", f"{s.bq_ds_mart}.v_movie_full == 1000", f"{mart}.v_movie_full", 1000),
        _count_gate(client, "B6", f"{s.bq_ds_mart}.v_integrity_exceptions == 0", f"{mart}.v_integrity_exceptions", 0),
        _count_gate(
            client,
            "B7",
            "v_movie_full NULL director_name == 0",
            f"{mart}.v_movie_full",
            0,
            where="director_name IS NULL",
        ),
        _count_gate(
            client,
            "B8",
            "v_movie_full NULL avg_rating == 0",
            f"{mart}.v_movie_full",
            0,
            where="avg_rating IS NULL",
        ),
        # B11 asserts the mart view is readable and complete with the pipeline's
        # own credentials. It deliberately does NOT claim to prove the agent
        # service account's access path: that needs impersonation and is
        # reported as its own line item by `pwa audit`.
        _count_gate(
            client,
            "B11",
            f"{s.bq_ds_mart}.v_movie_full readable (pipeline creds) == 1000",
            f"{mart}.v_movie_full",
            1000,
            detail_label="Query returned rows",
        ),
    ]


def _governance_gates(client, s):
    """B9, B10, B12, B13: documentation, least privilege and selection stability."""
    p = s.gcp_project
    mart = f"{p}.{s.bq_ds_mart}"
    registry = f"{p}.{s.bq_ds_registry}"

    def gate_b9():
        name = "Every mart view has description"
        try:
            desc_df = _query_df(
                client,
                f"SELECT table_name, option_value FROM `{mart}.INFORMATION_SCHEMA.TABLE_OPTIONS` "
                "WHERE option_name = 'description'",
            )
        except Exception as e:
            return cannot_verify("B9", name, e)
        missing = set(MART_VIEWS) - set(desc_df["table_name"])
        null_desc = desc_df[desc_df["option_value"].isna() | (desc_df["option_value"].str.strip() == "")][
            "table_name"
        ].tolist()
        if missing:
            detail = f"Missing: {missing}"
        elif null_desc:
            detail = f"Null desc: {null_desc}"
        else:
            detail = "All views described"
        return GateResult("B9", name, not missing and not null_desc, detail)

    def gate_b10():
        name = "Every mart column has description"
        try:
            col_df = _query_df(
                client,
                f"SELECT table_name, column_name, description FROM `{mart}.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`",
            )
        except Exception as e:
            return cannot_verify("B10", name, e)
        undescribed = col_df[col_df["description"].isna() | (col_df["description"].str.strip() == "")]
        if len(undescribed) == 0:
            return GateResult("B10", name, True, f"All {len(col_df)} columns described")
        missing_cols = undescribed.apply(lambda r: f"{r['table_name']}.{r['column_name']}", axis=1).tolist()
        detail = f"Undescribed columns ({len(missing_cols)}): " + ", ".join(missing_cols[:10])
        if len(missing_cols) > 10:
            detail += f"... and {len(missing_cols) - 10} more"
        return GateResult("B10", name, False, detail)

    def gate_b12():
        name = f"Agent SA CANNOT query {s.bq_ds_registry}.movie"
        sa_email = f"warehouse-agent@{p}.iam.gserviceaccount.com"
        try:
            dataset_ref = client.get_dataset(registry)
        except Exception as e:
            return cannot_verify("B12", name, e)
        has_viewer = any(
            getattr(entry, "entity_id", None) == sa_email and entry.role and "READER" in str(entry.role).upper()
            for entry in dataset_ref.access_entries
        )
        detail = (
            f"{sa_email} has NO dataViewer on {s.bq_ds_registry} (correct)"
            if not has_viewer
            else f"{sa_email} has dataViewer on {s.bq_ds_registry} (should not)"
        )
        return GateResult("B12", name, not has_viewer, detail)

    def gate_b13():
        name = "selected_movie_ids.csv SHA-256 stable"
        try:
            with open(SELECTED_IDS_CSV, "rb") as fh:
                sha256 = hashlib.sha256(fh.read()).hexdigest()
        except OSError as e:
            return cannot_verify("B13", name, e)
        if not os.path.exists(SELECTED_IDS_PIN):
            with open(SELECTED_IDS_PIN, "w", encoding="utf-8") as fh:
                fh.write(sha256)
            return GateResult("B13", name, True, f"Pinned SHA-256: {sha256[:16]}... (first run)")
        with open(SELECTED_IDS_PIN, "r", encoding="utf-8") as fh:
            pinned = fh.read().strip()
        matched = sha256 == pinned
        return GateResult("B13", name, matched, f"SHA-256 match: {matched} ({sha256[:16]}...)")

    return [gate_b9, gate_b10, gate_b12, gate_b13]


def _federation_liveness_gate(client, s):
    """B14: mutating. NULLs one producer_name in Postgres, proves BigQuery sees it, restores it."""
    name = "Federation liveness proof"
    view = f"{s.gcp_project}.{s.bq_ds_mart}.v_movie_credits"

    def run():
        try:
            pg_engine, _ = get_pg_engine()
            baseline = _count(client, view, "producer_name IS NULL")
            logger.info(f"Gate B14 baseline NULL producer_name count: {baseline}")

            with pg_engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT movie_id, producer_name FROM movie_credits "
                        "WHERE producer_name IS NOT NULL ORDER BY movie_id LIMIT 1"
                    )
                ).fetchone()
            if row is None:
                return cannot_verify("B14", name, "no movie_credits row has a non-null producer_name", mutating=True)
            target_movie_id, original_value = row[0], row[1]

            try:
                with pg_engine.connect() as conn:
                    conn.execute(
                        text("UPDATE movie_credits SET producer_name = NULL WHERE movie_id = :mid"),
                        {"mid": target_movie_id},
                    )
                    conn.commit()
                logger.info(f"Gate B14: set producer_name=NULL for movie_id={target_movie_id}")

                after_null = _count(client, view, "producer_name IS NULL")
                logger.info(f"Gate B14 after UPDATE NULL producer_name count: {after_null}")
                increased = after_null == baseline + 1
            finally:
                # The restore runs whatever happened above, and a failed restore
                # is loud: it would otherwise leave a NULLed row in Postgres.
                with pg_engine.connect() as conn:
                    conn.execute(
                        text("UPDATE movie_credits SET producer_name = :val WHERE movie_id = :mid"),
                        {"val": original_value, "mid": target_movie_id},
                    )
                    conn.commit()
                logger.info(f"Gate B14: restored producer_name for movie_id={target_movie_id}")

            restored_cnt = _count(client, view, "producer_name IS NULL")
            restored = restored_cnt == baseline
            return GateResult(
                "B14",
                name,
                increased and restored,
                f"Baseline={baseline}, After NULL={after_null} (+1={increased}), "
                f"Restored={restored_cnt} (back={restored})",
                mutating=True,
            )
        except Exception as e:
            return cannot_verify("B14", name, e, mutating=True)

    return run


def _cross_engine_proof_gate(client, s):
    """B15: the whole point of the warehouse, asserted as a query."""
    name = "Cross-engine proof (top 10 directors)"
    sql = f"""
    SELECT director_name,
           COUNT(*)              AS films,
           ROUND(APPROX_QUANTILES(roi, 2)[OFFSET(1)], 2) AS median_roi,
           SUM(revenue_usd)      AS total_revenue
    FROM `{s.gcp_project}.{s.bq_ds_mart}.v_movie_full`
    GROUP BY director_name
    HAVING films >= 2
    ORDER BY median_roi DESC
    LIMIT 10
    """

    def run():
        try:
            proof_df = _query_df(client, sql)
        except Exception as e:
            return cannot_verify("B15", name, e)
        nan_dirs = proof_df["director_name"].isna().sum()
        return GateResult(
            "B15",
            name,
            len(proof_df) >= 10 and nan_dirs == 0,
            f"Rows: {len(proof_df)}, NaN dirs: {nan_dirs}",
            extra=[
                "=== GATE B15: CROSS-ENGINE PROOF - TOP 10 DIRECTORS BY MEDIAN ROI ===\n"
                + proof_df.to_string(index=False)
            ],
        )

    return run


def build_gates(client, s):
    """Return the 15 BigQuery gates, in reporting order."""
    data = _data_gates(client, s)
    governance = {g.__name__: g for g in _governance_gates(client, s)}
    b1_to_b8, b11 = data[:8], data[8]
    return [
        *b1_to_b8,
        governance["gate_b9"],
        governance["gate_b10"],
        b11,
        governance["gate_b12"],
        governance["gate_b13"],
        _federation_liveness_gate(client, s),
        _cross_engine_proof_gate(client, s),
    ]


def run_all_bq_gates() -> bool:
    """Run BigQuery gates B1-B15. Returns True only if every gate passed."""
    try:
        s = get_settings()
        client = get_bq_client()
    except Exception as exc:
        error = exc
        return run_gates([lambda: cannot_verify("B1-B15", "BigQuery client available", error)], "BIGQUERY GATES B1-B15")
    return run_gates(build_gates(client, s), "BIGQUERY GATES B1-B15")


if __name__ == "__main__":
    raise SystemExit(0 if run_all_bq_gates() else 1)

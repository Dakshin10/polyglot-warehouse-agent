"""Unit tests for Phase 2 Quality Gate failure blocking."""

import pandas as pd
import pytest
from pwa.quality.quality_gates import Phase1QualityFramework, QualityGateException, QualityResult


def test_quality_gate_exception_raised_on_duplicate_pk():
    qf = Phase1QualityFramework(strict=True)

    # DataFrame with duplicate primary keys (id 101 duplicated)
    df_corrupted = pd.DataFrame(
        [
            {"id": 101, "name": "Alpha"},
            {"id": 101, "name": "Alpha Duplicate"},
            {"id": 102, "name": "Beta"},
        ]
    )

    with pytest.raises(QualityGateException) as exc_info:
        qf.gate_7_pk_uniqueness(source_id="test_db", table_name="users", df=df_corrupted, pk_cols=["id"])

    assert "Gate 7: PK Uniqueness" in str(exc_info.value)
    assert exc_info.value.result.status == "FAIL"


def test_quality_gate_exception_raised_on_null_constraint():
    qf = Phase1QualityFramework(strict=True)

    # DataFrame with null violation in NOT NULL column "email"
    df_null_violation = pd.DataFrame(
        [
            {"id": 1, "email": "user1@test.com"},
            {"id": 2, "email": None},
        ]
    )

    with pytest.raises(QualityGateException) as exc_info:
        qf.gate_8_null_constraint(
            source_id="test_db", table_name="users", df=df_null_violation, not_null_cols=["email"]
        )

    assert "Gate 8: Null Constraint" in str(exc_info.value)
    assert exc_info.value.result.status == "FAIL"


def test_quality_gate_pass_no_exception():
    qf = Phase1QualityFramework(strict=True)

    df_clean = pd.DataFrame([{"id": 1, "name": "A"}, {"id": 2, "name": "B"}])
    res = qf.gate_7_pk_uniqueness(source_id="test_db", table_name="users", df=df_clean, pk_cols=["id"])
    assert res.status == "PASS"

"""Unit tests for Post-Remediation Follow-Up Tasks 1 through 4."""

import pandas as pd
import pytest
from pwa.agent.pipeline.exec_agent import _extract_source_tables
from pwa.agent.router import QueryCategory, QueryRouter
from pwa.agent.semantic_cache import semantic_cache
from pwa.quality.quality_gates import Phase1QualityFramework, QualityGateException


# ─── Task 1: Router Mutation Regex Hardening ──────────────────────────────────


def test_task1_adversarial_mutation_keywords_blocked():
    router = QueryRouter()

    adversarial_queries = [
        "drop table sales",
        "drop the customers table",
        "DROP TABLE fact_sales_order",
        "drop view customer_summary",
        "drop database production",
        "delete from users",
        "insert into orders values (1, 2)",
        "alter table dim_product add column test string",
        "truncate table stg_sales",
        "run shell rm -rf /",
        "drop customers table now",
        "please drop the orders table",
        "can you delete from the sales table",
        "TRUNCATE TABLE fact_sales_order",
        "ALTER TABLE customer_orders DROP COLUMN email",
    ]

    for q in adversarial_queries:
        decision = router.route(q)
        assert decision.category == QueryCategory.UNSUPPORTED, f"Query '{q}' should be classified UNSUPPORTED"


def test_task1_analytical_queries_with_drop_allowed():
    router = QueryRouter()

    legitimate_queries = [
        "why did revenue drop in Q3",
        "show me the drop in customer signups",
        "analyse monthly revenue decline diagnostic",
        "what caused the drop in Q3 revenue",
        "show me the revenue decline",
    ]

    for q in legitimate_queries:
        decision = router.route(q)
        assert decision.category != QueryCategory.UNSUPPORTED, f"Query '{q}' should NOT be classified UNSUPPORTED"


# ─── Task 2: PII Masking Order Before Caching ────────────────────────────────


def test_task2_pii_masking_before_caching_two_pass():
    import os
    from unittest.mock import MagicMock, patch
    from pwa.agent.pipeline.orchestrator import MultiAgentPipelineOrchestrator
    from pwa.semantic.result_contract import QueryResult

    os.environ["PWA_SEMANTIC_CACHE_ENABLED"] = "1"
    semantic_cache.clear()

    question = "Show customer emails and phone numbers for top orders"

    # Mock raw query execution returning raw unmasked PII
    raw_query_res = QueryResult(
        query_id="q101",
        sql="SELECT email, phone FROM customer_orders",
        columns=["email", "phone"],
        rows=[
            {"email": "alice@company.com", "phone": "+1-555-0199"},
            {"email": "bob@enterprise.org", "phone": "+1-555-0288"},
        ],
        row_count=2,
        bytes_processed=1024,
        execution_time_seconds=0.1,
        semantic_objects_used=["dim_customer"],
        source_tables=["customer_orders"],
    )

    orch = MultiAgentPipelineOrchestrator()

    with (
        patch.object(orch.router, "route") as mock_route,
        patch.object(orch.fast_path, "match_and_execute", return_value=None),
        patch.object(orch.grounding_agent, "ground_question") as mock_ground,
        patch.object(
            orch.sql_agent, "generate_sql_from_intent", return_value="SELECT email, phone FROM customer_orders"
        ),
        patch.object(orch.exec_agent, "validate_and_execute", return_value=raw_query_res),
    ):
        mock_route.return_value = MagicMock(category=MagicMock(value="ANALYTICAL"), workflow_template_hint=None)
        mock_ground.return_value = MagicMock(clarification_required=False, analytical_intent=MagicMock())

        # Pass 1: Uncached run -> should mask PII before synthesis & cache put
        res1 = orch.run_pipeline(question)
        assert res1.exec_status == "SUCCESS"
        assert res1.cache_hit is False or res1.cache_hit is None
        assert "a***@company.com" in str(res1.answer) or "***" in str(res1.rows)
        assert "alice@company.com" not in str(res1.answer)
        assert "alice@company.com" not in str(res1.rows)

        # Pass 2: Cached run -> should return masked answer directly from semantic cache
        res2 = orch.run_pipeline(question)
        assert res2.routing_category == "SEMANTIC_CACHE" or res2.cache_hit is True
        assert res2.exec_status == "SUCCESS"
        assert "alice@company.com" not in str(res2.answer)
        assert "***" in str(res2.answer)


# ─── Task 3: Federated EXTERNAL_QUERY AST Table Extraction ───────────────────


def test_task3_federated_external_query_lineage_extraction():
    federated_sql = """
    SELECT
        o.order_id,
        o.order_date,
        c.customer_name,
        c.email
    FROM EXTERNAL_QUERY(
        "projects/my-gcp-project/locations/eu/connections/mysql_conn",
        "SELECT order_id, order_date, customer_name, email FROM mysql_orders JOIN mysql_customers ON mysql_orders.cust_id = mysql_customers.id"
    ) AS o
    """

    tables = _extract_source_tables(federated_sql)
    # Must extract inner federated tables from the string literal inside EXTERNAL_QUERY(...)
    assert any("mysql_orders" in t for t in tables), f"Expected mysql_orders in extracted tables {tables}"
    assert any("mysql_customers" in t for t in tables), f"Expected mysql_customers in extracted tables {tables}"


# ─── Task 4: Quality Gate Audit (Blocking vs Advisory) ────────────────────────


def test_task4_quality_gates_blocking_vs_advisory_contract():
    qf = Phase1QualityFramework(strict=True)

    # 1. Blocking Gate 1 Connectivity
    class MockFailingConnector:
        def test_connection(self):
            return False

    with pytest.raises(QualityGateException):
        qf.gate_1_connectivity("test_db", MockFailingConnector())

    # 2. Blocking Gate 12 Reconciliation Mismatch
    with pytest.raises(QualityGateException):
        qf.gate_12_reconciliation("test_db", "orders", source_cnt=1000, target_cnt=950)

    # 3. Advisory Gate 4 Extraction Boundary (does NOT raise on execution)
    res_g4 = qf.gate_4_extraction_boundary("test_db", "orders", batch_size=5000)
    assert res_g4.status == "PASS"

    # 4. Advisory Gate 9 Value Range (does NOT raise on execution)
    df_sample = pd.DataFrame([{"val": 100}])
    res_g9 = qf.gate_9_value_range("test_db", "orders", df_sample)
    assert res_g9.status == "PASS"

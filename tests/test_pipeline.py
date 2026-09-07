"""Pipeline-level integration tests & unit tests for 4-agent pipeline."""

from unittest.mock import patch

import pytest

from pwa.agent.pipeline.exec_agent import ast_validate_sql
from pwa.agent.pipeline.orchestrator import run_query


def test_exec_agent_static_validation_allows_valid_select():
    """Verify AST SQL validator permits read-only SELECT queries on mart views."""
    valid_sqls = [
        "SELECT movie_id, title FROM `salitsteel-502008.mart.v_movie` LIMIT 10",
        "SELECT director_name, COUNT(*) FROM `salitsteel-502008.mart.v_movie_credits` GROUP BY director_name LIMIT 50",
        "SELECT title, revenue_usd FROM `salitsteel-502008.mart.v_movie_full` LIMIT 5",
    ]
    for sql in valid_sqls:
        ast_validate_sql(sql)  # Should not raise


def test_exec_agent_static_validation_rejects_forbidden_keywords():
    """Verify AST SQL validator blocks DDL/DML statements at the AST level."""
    forbidden_sqls = [
        "DELETE FROM `salitsteel-502008.mart.v_movie` WHERE movie_id = 11",
        "DROP TABLE `salitsteel-502008.mart.v_movie`",
        "UPDATE `salitsteel-502008.mart.v_movie` SET title = 'Hacked'",
        "CREATE TABLE `salitsteel-502008.mart.hacked` AS SELECT 1",
        "TRUNCATE TABLE `salitsteel-502008.mart.v_movie`",
    ]
    for sql in forbidden_sqls:
        with pytest.raises(ValueError, match="Only SELECT statements are allowed"):
            ast_validate_sql(sql)


def test_exec_agent_static_validation_rejects_unauthorized_tables():
    """Verify AST SQL validator blocks queries targeting staging/raw tables."""
    unauthorized_sqls = [
        "SELECT title FROM `salitsteel-502008.raw_registry.movie` LIMIT 10",
        "SELECT name FROM `salitsteel-502008.staging.movie_credits` LIMIT 5",
    ]
    for sql in unauthorized_sqls:
        with pytest.raises(ValueError, match="Access denied"):
            ast_validate_sql(sql)


def test_pipeline_retry_mechanism():
    """Verify Stage 5 orchestrator performs exactly ONE retry attempt on Stage 3 failure."""
    # Mock Stage 1 schema grounding
    mock_ground = {"relevant_views": [{"view_name": "mart.v_movie", "columns": ["title"]}]}

    # Mock Stage 2 SQL generation (first attempt returns bad SQL, second attempt returns valid SQL)
    sqls = [
        "SELECT title FROM `mart.v_movie` WHERE bad_col = 1;",
        "SELECT title FROM `mart.v_movie` WHERE release_year = 2010 LIMIT 1;",
    ]

    # Mock Stage 3 execution (first attempt fails with ERROR, second attempt succeeds)
    exec_results = [
        {"status": "ERROR", "error": "Unrecognized name: bad_col", "sql": sqls[0], "rows": []},
        {"status": "SUCCESS", "sql": sqls[1], "rows": [{"title": "Toy Story 3"}], "count": 1},
    ]

    with patch("pwa.agent.pipeline.orchestrator.ground_schema", return_value=mock_ground):
        with patch("pwa.agent.pipeline.orchestrator.generate_sql", side_effect=sqls) as mock_gen:
            with patch(
                "pwa.agent.pipeline.orchestrator.validate_and_execute_sql", side_effect=exec_results
            ) as mock_exec:
                with patch(
                    "pwa.agent.pipeline.orchestrator.synthesize_answer",
                    return_value="In 2010, the top movie was Toy Story 3.",
                ):
                    answer = run_query("Which movie in 2010?")

                    # Verify 2 calls to SQL generation (initial + 1 retry)
                    assert mock_gen.call_count == 2
                    # Verify retry call passed error feedback
                    assert "Unrecognized name: bad_col" in mock_gen.call_args_list[1].kwargs.get("retry_error", "")

                    # Verify 2 calls to execution
                    assert mock_exec.call_count == 2

                    assert answer == "In 2010, the top movie was Toy Story 3."


@pytest.mark.integration
def test_pipeline_highest_revenue_movie_2010():
    """Integration Test 1: Verify 4-agent pipeline queries top 2010 revenue movie."""
    answer = run_query("Which movie had the highest revenue in 2010?")
    assert answer is not None
    assert isinstance(answer, str)
    assert "Toy Story 3" in answer or "1,066,969,703" in answer or "1066969703" in answer


@pytest.mark.integration
def test_pipeline_director_query():
    """Integration Test 2: Verify 4-agent pipeline identifies director of Inception."""
    answer = run_query("Who directed Inception?")
    assert answer is not None
    assert isinstance(answer, str)
    assert "Christopher Nolan" in answer


@pytest.mark.integration
def test_pipeline_unanswerable_out_of_scope_query():
    """Integration Test 3: Verify 4-agent pipeline declines out-of-scope personal address question."""
    answer = run_query("What is Christopher Nolan's personal home address and phone number?")
    assert answer is not None
    assert isinstance(answer, str)
    answer_lower = answer.lower()
    assert any(
        phrase in answer_lower
        for phrase in [
            "cannot be answered",
            "not available",
            "do not have",
            "don't have",
            "unavailable",
            "mart",
            "address",
            "no information",
        ]
    )

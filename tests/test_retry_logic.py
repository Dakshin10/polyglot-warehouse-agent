"""Unit tests for pipeline retry logic (Task P1-4).

Tests verify:
- An actual SQL execution error triggers exactly ONE retry pass through SQL generation.
- A zero-row (EMPTY) result does NOT trigger retry and reaches Answer Synthesis.

All LLM and BigQuery calls are mocked.
"""

from unittest.mock import patch

from pwa.agent.pipeline.orchestrator import _run_pipeline_stages


def _mock_result(status: str, sql: str = "SELECT 1", error: str = "", rows=None):
    return {
        "status": status,
        "sql": sql,
        "error": error,
        "rows": rows or [],
        "count": len(rows) if rows else 0,
    }


class TestErrorRetry:
    def test_execution_error_triggers_exactly_one_retry(self):
        """When Stage 3 returns ERROR, generate_sql and validate_and_execute_sql
        must each be called exactly twice (attempt 1 + 1 retry)."""

        with (
            patch("pwa.agent.pipeline.orchestrator.run_step_with_fallback") as mock_fallback,
            patch("pwa.agent.pipeline.orchestrator.validate_and_execute_sql") as mock_exec,
        ):
            # Stage 1 (schema): return grounded schema
            # Stage 2 attempt 1 (sql): return sql string
            # Stage 3 attempt 1: return ERROR
            # Stage 2 attempt 2 (sql retry): return sql string
            # Stage 3 attempt 2: return SUCCESS
            # Stage 4 (answer): return answer string

            mock_fallback.side_effect = [
                ({"relevant_views": [], "reasoning": "ok"}, None),  # schema stage
                ("SELECT title FROM mart.v_movie LIMIT 10", None),  # sql attempt 1
                ("SELECT title FROM mart.v_movie LIMIT 10", None),  # sql retry attempt 2
                ("The top movies are ...", None),  # answer stage
            ]
            mock_exec.side_effect = [
                _mock_result("ERROR", error="Syntax error: unexpected token"),
                _mock_result("SUCCESS", rows=[{"title": "Inception"}]),
            ]

            result = _run_pipeline_stages("what are the top movies?")

            assert result.answer == "The top movies are ..."
            assert mock_exec.call_count == 2, "validate_and_execute_sql must be called exactly twice"
            # SQL fallback called for schema (1) + sql attempt1 (2) + sql retry (3) + answer (4)
            assert mock_fallback.call_count == 4

    def test_error_on_retry_still_reaches_synthesis(self):
        """Even if the retry also returns ERROR, synthesis is still called (graceful failure)."""
        with (
            patch("pwa.agent.pipeline.orchestrator.run_step_with_fallback") as mock_fallback,
            patch("pwa.agent.pipeline.orchestrator.validate_and_execute_sql") as mock_exec,
        ):
            mock_fallback.side_effect = [
                ({"relevant_views": [], "reasoning": "ok"}, None),  # schema
                ("SELECT 1", None),  # sql attempt 1
                ("SELECT 1", None),  # sql retry
                ("Sorry, unable to answer.", None),  # answer
            ]
            mock_exec.side_effect = [
                _mock_result("ERROR", error="First error"),
                _mock_result("ERROR", error="Second error"),
            ]
            result = _run_pipeline_stages("impossible question")
            assert "Sorry" in result.answer
            assert mock_exec.call_count == 2


class TestEmptyNoRetry:
    def test_zero_row_result_does_not_trigger_retry(self):
        """When Stage 3 returns EMPTY, it must NOT call validate_and_execute_sql again."""
        with (
            patch("pwa.agent.pipeline.orchestrator.run_step_with_fallback") as mock_fallback,
            patch("pwa.agent.pipeline.orchestrator.validate_and_execute_sql") as mock_exec,
        ):
            mock_fallback.side_effect = [
                ({"relevant_views": [], "reasoning": "ok"}, None),  # schema
                ("SELECT title FROM mart.v_movie WHERE 1=0", None),  # sql
                ("No movies matched your criteria.", None),  # answer
            ]
            mock_exec.return_value = _mock_result("EMPTY", error="Query executed successfully but returned 0 rows.")

            result = _run_pipeline_stages("find movies from the year 1800")

            assert result.answer == "No movies matched your criteria."
            assert mock_exec.call_count == 1, "EMPTY should NOT trigger retry"
            assert mock_fallback.call_count == 3, "schema + sql + answer only (no retry sql call)"

    def test_empty_result_passed_to_synthesis_correctly(self):
        """The EMPTY result dict must be forwarded to synthesize_answer intact."""
        empty_result = _mock_result("EMPTY", error="Query executed successfully but returned 0 rows.")

        with (
            patch("pwa.agent.pipeline.orchestrator.run_step_with_fallback") as mock_fallback,
            patch("pwa.agent.pipeline.orchestrator.validate_and_execute_sql") as mock_exec,
        ):
            mock_exec.return_value = empty_result
            # We need 3 side effects: schema, sql, answer
            mock_fallback.side_effect = [
                ({"relevant_views": [], "reasoning": "ok"}, None),
                ("SELECT 1", None),
                ("No data found.", None),
            ]
            _run_pipeline_stages("test question")

            # The answer call (3rd) should have received the EMPTY result
            answer_call_args = mock_fallback.call_args_list[2]
            # run_step_with_fallback(step_name, step_fn, question, result, ...)
            passed_result = answer_call_args[0][3]  # positional arg index 3
            assert passed_result["status"] == "EMPTY"

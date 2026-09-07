"""Unit tests for AST-based SQL validation (Task P0-1).

Tests confirm that sqlglot AST-based allowlisting catches all attack vectors that the
old keyword-blocklist missed (write ops inside CTEs, malformed SQL, etc.) while still
passing valid SELECTs including EXTERNAL_QUERY federated patterns.

All tests are fully offline — no BigQuery or LLM calls are made.
"""

import pytest

from pwa.agent.pipeline.exec_agent import ast_validate_sql


# ---------------------------------------------------------------------------
# Valid SELECTs — must all PASS
# ---------------------------------------------------------------------------

class TestValidSelects:
    def test_simple_select_passes(self):
        sql = "SELECT title, revenue_usd FROM `salitsteel-502008.mart.v_movie` LIMIT 10"
        ast_validate_sql(sql)  # Should not raise

    def test_select_with_where_passes(self):
        sql = (
            "SELECT title, release_year FROM `salitsteel-502008.mart.v_movie` "
            "WHERE release_year = 2010 LIMIT 5"
        )
        ast_validate_sql(sql)

    def test_select_with_join_passes(self):
        sql = (
            "SELECT m.title, c.director_name "
            "FROM `salitsteel-502008.mart.v_movie` m "
            "JOIN `salitsteel-502008.mart.v_movie_credits` c ON m.movie_id = c.movie_id "
            "LIMIT 10"
        )
        ast_validate_sql(sql)

    def test_aggregate_select_passes(self):
        sql = (
            "SELECT primary_genre, COUNT(*) AS cnt, ROUND(AVG(revenue_usd), 2) AS avg_rev "
            "FROM `salitsteel-502008.mart.v_movie` "
            "GROUP BY primary_genre ORDER BY cnt DESC LIMIT 5"
        )
        ast_validate_sql(sql)

    def test_external_query_federated_select_passes(self):
        """EXTERNAL_QUERY federated patterns must survive AST validation."""
        sql = (
            "SELECT * FROM EXTERNAL_QUERY("
            "'salitsteel-502008.EU.movie-credits-conn', "
            "'SELECT movie_id, director_name FROM movie_credits LIMIT 10')"
        )
        ast_validate_sql(sql)

    def test_cte_select_passes(self):
        sql = (
            "WITH top_movies AS ("
            "  SELECT movie_id, title, revenue_usd "
            "  FROM `salitsteel-502008.mart.v_movie` "
            "  ORDER BY revenue_usd DESC LIMIT 10"
            ") "
            "SELECT t.title, c.director_name "
            "FROM top_movies t "
            "JOIN `salitsteel-502008.mart.v_movie_credits` c ON t.movie_id = c.movie_id"
        )
        ast_validate_sql(sql)

    def test_subquery_select_passes(self):
        sql = (
            "SELECT title FROM ("
            "  SELECT title, revenue_usd FROM `salitsteel-502008.mart.v_movie`"
            ") sub ORDER BY revenue_usd DESC LIMIT 3"
        )
        ast_validate_sql(sql)


# ---------------------------------------------------------------------------
# Forbidden top-level statements — must all RAISE ValueError
# ---------------------------------------------------------------------------

class TestTopLevelForbiddenStatements:
    def test_drop_table_rejected(self):
        sql = "DROP TABLE `salitsteel-502008.mart.v_movie`"
        with pytest.raises(ValueError, match="Only SELECT statements are allowed"):
            ast_validate_sql(sql)

    def test_delete_rejected(self):
        sql = "DELETE FROM `salitsteel-502008.mart.v_movie` WHERE 1=1"
        with pytest.raises(ValueError, match="Only SELECT statements are allowed"):
            ast_validate_sql(sql)

    def test_update_rejected(self):
        sql = "UPDATE `salitsteel-502008.mart.v_movie` SET title = 'Hacked' WHERE movie_id = 1"
        with pytest.raises(ValueError, match="Only SELECT statements are allowed"):
            ast_validate_sql(sql)

    def test_insert_rejected(self):
        sql = "INSERT INTO `salitsteel-502008.mart.v_movie` (title) VALUES ('Evil Row')"
        with pytest.raises(ValueError, match="Only SELECT statements are allowed"):
            ast_validate_sql(sql)

    def test_create_table_rejected(self):
        sql = "CREATE TABLE `salitsteel-502008.mart.exfil` AS SELECT * FROM `salitsteel-502008.mart.v_movie`"
        with pytest.raises(ValueError, match="Only SELECT statements are allowed"):
            ast_validate_sql(sql)

    def test_truncate_rejected(self):
        sql = "TRUNCATE TABLE `salitsteel-502008.mart.v_movie`"
        with pytest.raises(ValueError, match="Only SELECT statements are allowed"):
            ast_validate_sql(sql)


# ---------------------------------------------------------------------------
# Write ops HIDDEN inside CTEs — the keyword-blocklist would have missed these
# ---------------------------------------------------------------------------

class TestWriteHiddenInCTE:
    def test_delete_inside_cte_rejected(self):
        """A DELETE smuggled inside a CTE must be rejected by the AST walker."""
        sql = (
            "WITH evil AS ("
            "  DELETE FROM `salitsteel-502008.mart.v_movie` WHERE 1=1"
            ") "
            "SELECT 1"
        )
        with pytest.raises(ValueError):
            ast_validate_sql(sql)

    def test_insert_inside_cte_rejected(self):
        sql = (
            "WITH evil AS ("
            "  INSERT INTO `salitsteel-502008.mart.v_movie` (title) VALUES ('x')"
            ") "
            "SELECT 1"
        )
        with pytest.raises(ValueError):
            ast_validate_sql(sql)

    def test_drop_inside_subquery_rejected(self):
        """Demonstrates AST catch of DROP nested in a sub-expression."""
        sql = (
            "SELECT (DROP TABLE `salitsteel-502008.mart.v_movie`)"
        )
        with pytest.raises(ValueError):
            ast_validate_sql(sql)


# ---------------------------------------------------------------------------
# Malformed / unparseable SQL — must raise ValueError
# ---------------------------------------------------------------------------

class TestMalformedSQL:
    def test_empty_string_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ast_validate_sql("")

    def test_whitespace_only_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ast_validate_sql("   ")

    def test_garbage_string_rejected(self):
        with pytest.raises(ValueError):
            ast_validate_sql("NOT VALID SQL AT ALL ;;; ???")

    def test_semicolon_only_rejected(self):
        with pytest.raises(ValueError):
            ast_validate_sql(";")

    def test_partial_select_rejected(self):
        with pytest.raises(ValueError):
            ast_validate_sql("SELECT FROM")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_select_with_comment_passes(self):
        """SQL with comments must still parse and pass."""
        sql = (
            "-- get top movies\n"
            "SELECT title, revenue_usd FROM `salitsteel-502008.mart.v_movie` LIMIT 5"
        )
        ast_validate_sql(sql)

    def test_backtick_wrapped_sql_passes(self):
        sql = "SELECT `title` FROM `salitsteel-502008.mart.v_movie` LIMIT 1"
        ast_validate_sql(sql)

    def test_select_1_passes(self):
        """Connectivity-check query must pass."""
        ast_validate_sql("SELECT 1")

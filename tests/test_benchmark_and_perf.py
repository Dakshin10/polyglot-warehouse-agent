from pwa.agent.pipeline.orchestrator import PipelineResult
from pwa.eval.benchmark import evaluate_expected_check, evaluate_query_conditions, load_benchmark_queries
from pwa.eval.performance import compute_cost, generate_perf_report


def test_load_benchmark_queries():
    """Verify loading 50 benchmark queries dataset."""
    queries = load_benchmark_queries()
    assert len(queries) == 50
    categories = set(q["category"] for q in queries)
    assert "aggregation" in categories
    assert "top_n" in categories
    assert "filtering" in categories
    assert "group_by" in categories
    assert "federated" in categories
    assert "date_time" in categories
    assert "ambiguous_edge" in categories


def test_evaluate_query_conditions_pass():
    """Test 5 strict conditions pass on a valid PipelineResult."""
    entry = {"id": "q01", "category": "top_n", "question": "which 3 movies had highest revenue?"}
    res = PipelineResult(
        answer="Avatar is top.",
        sql="SELECT title FROM mart.v_movie LIMIT 3",
        rows=[{"title": "Avatar"}],
        bytes_scanned=100,
        exec_status="SUCCESS",
        row_count=1,
    )
    is_pass, failed_stage, err = evaluate_query_conditions(entry, res)
    assert is_pass is True
    assert failed_stage == "none"
    assert err == ""


def test_evaluate_query_conditions_ast_fail():
    """Test 5 strict conditions fail when SQL violates AST validation."""
    entry = {"id": "q02", "category": "top_n", "question": "test"}
    res = PipelineResult(
        answer="Done",
        sql="DROP TABLE mart.v_movie",
        rows=[],
        exec_status="SUCCESS",
    )
    is_pass, failed_stage, err = evaluate_query_conditions(entry, res)
    assert is_pass is False
    assert failed_stage == "validation"
    assert "AST validation failed" in err


def test_evaluate_expected_check():
    """Test expected_check assertion evaluator."""
    entry = {"expected_check": {"type": "answer_contains", "value": "Avatar"}}
    res = PipelineResult(answer="The top movie is Avatar ($2.9B).")
    assert evaluate_expected_check(entry, res) is True

    entry_fail = {"expected_check": {"type": "answer_contains", "value": "Titanic"}}
    assert evaluate_expected_check(entry_fail, res) is False


def test_compute_cost():
    """Test BigQuery and LLM cost calculation math."""
    costs = compute_cost(bytes_scanned=1024 * 1024 * 1024, prompt_tokens=1000, completion_tokens=500)
    # 1 GB at $6.25/TB = $0.005960
    assert costs["bq_cost_usd"] > 0
    assert costs["llm_cost_usd"] > 0
    assert costs["total_cost_usd"] == round(costs["bq_cost_usd"] + costs["llm_cost_usd"], 6)


def test_generate_perf_report():
    """Test report generation statistics formatting."""
    record = {
        "id": "q01",
        "category": "top_n",
        "question": "test",
        "is_error": False,
        "total_latency_ms": 500.0,
        "stage_latencies_ms": {"schema": 100.0, "sql": 200.0, "exec": 100.0, "answer": 100.0},
        "bytes_scanned": 1048576,
        "actual_bytes_processed": 1048576,
        "bq_cost_usd": 0.0001,
        "llm_cost_usd": 0.0001,
        "total_cost_usd": 0.0002,
    }
    metrics, report_md = generate_perf_report([record], [record], [record], [{"concurrency": 1, "total_wall_seconds": 0.5, "p50_ms": 500.0, "p90_ms": 500.0, "error_rate_pct": 0.0}])
    assert "Performance & Cost Report" in report_md
    assert metrics["total_cost_usd"] > 0

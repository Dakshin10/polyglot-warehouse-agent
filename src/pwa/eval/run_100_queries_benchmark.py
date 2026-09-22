"""100-Query Benchmark Test Runner for Polyglot Warehouse Agent (PWA).

Executes 100 queries across all warehouse entities, evaluating:
1. Intent & Router Grounding
2. Governed SQL Generation & AST Validation
3. Local SQLite Real Dataset Execution & Row Counts
4. Answer Synthesis & Latency
"""

import datetime
import json
import logging
import pathlib
import sys
import time
from typing import Any, Dict, List

# Add src/ to Python path
_SRC_DIR = pathlib.Path(__file__).parent.parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from pwa.agent.pipeline.orchestrator import PipelineResult, run_query_verbose
from pwa.eval.benchmark import evaluate_query_conditions, evaluate_expected_check

logger = logging.getLogger("pwa.eval.run_100")
_QUERIES_FILE = pathlib.Path(__file__).parent / "benchmark_100_queries.json"
_RESULTS_DIR = pathlib.Path(__file__).parent / "results"


def run_100_benchmark() -> Dict[str, Any]:
    queries = json.loads(_QUERIES_FILE.read_text(encoding="utf-8"))
    total_queries = len(queries)

    print("\n" + "=" * 80)
    print(f"  PWA 100-QUERY COMPREHENSIVE PIPELINE & STREAMLIT BENCHMARK")
    print(f"  Total Queries: {total_queries} | Timestamp: {datetime.datetime.now().isoformat()}")
    print("=" * 80 + "\n")

    results_data: List[Dict[str, Any]] = []
    passed_count = 0
    failed_count = 0
    cat_summary: Dict[str, Dict[str, int]] = {}

    t0_suite = time.perf_counter()

    for idx, entry in enumerate(queries, 1):
        qid = entry.get("id", f"q{idx:03d}")
        category = entry.get("category", "unknown")
        question = entry.get("question", "")

        if category not in cat_summary:
            cat_summary[category] = {"total": 0, "passed": 0, "failed": 0}
        cat_summary[category]["total"] += 1

        t0_q = time.perf_counter()

        try:
            res = run_query_verbose(question, timeout_seconds=120.0)
        except Exception as exc:
            res = f"[EXCEPTION] {exc}"

        latency_ms = round((time.perf_counter() - t0_q) * 1000, 1)

        is_pass, failed_at_stage, error_msg = evaluate_query_conditions(entry, res)
        expected_match = evaluate_expected_check(entry, res)

        if is_pass:
            passed_count += 1
            cat_summary[category]["passed"] += 1
            status_str = "PASS"
        else:
            failed_count += 1
            cat_summary[category]["failed"] += 1
            status_str = f"FAIL ({failed_at_stage})"

        answer_str = res.answer if isinstance(res, PipelineResult) else str(res)
        sql_str = res.sql if isinstance(res, PipelineResult) else None
        rows_cnt = res.row_count if isinstance(res, PipelineResult) else 0

        print(
            f"[{idx:03d}/{total_queries:03d}] {qid:<5} | {category:<15} | {status_str:<18} | "
            f"rows:{rows_cnt:<4} | {latency_ms:>6.0f}ms | '{question[:38]}...'"
        )

        results_data.append(
            {
                "id": qid,
                "category": category,
                "question": question,
                "pass": is_pass,
                "failed_at_stage": failed_at_stage,
                "error_message": error_msg,
                "generated_sql": sql_str,
                "row_count": rows_cnt,
                "answer": answer_str[:300] if answer_str else "",
                "latency_ms": latency_ms,
            }
        )

    total_suite_latency_s = round(time.perf_counter() - t0_suite, 2)
    pass_rate = round(100.0 * passed_count / total_queries, 1) if total_queries else 0.0

    print("\n" + "-" * 80)
    print(" 100-QUERY BENCHMARK SUMMARY REPORT")
    print(
        f" Total Queries: {total_queries} | Passed: {passed_count} | Failed: {failed_count} | Pass Rate: {pass_rate}%"
    )
    print(f" Total Wall-Clock Latency: {total_suite_latency_s}s")
    print("-" * 80)
    print(f"{'Category':<20} | {'Total':<8} | {'Passed':<8} | {'Failed':<8} | {'Pass Rate':<10}")
    print("-" * 64)

    for cat, stats in cat_summary.items():
        cat_pass_rate = round(100.0 * stats["passed"] / stats["total"], 1) if stats["total"] else 0.0
        print(f"{cat:<20} | {stats['total']:<8} | {stats['passed']:<8} | {stats['failed']:<8} | {cat_pass_rate:>8.1f}%")

    # Write JSON results
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = _RESULTS_DIR / f"benchmark_100_run_{timestamp}.json"

    run_payload = {
        "timestamp": timestamp,
        "total_queries": total_queries,
        "passed": passed_count,
        "failed": failed_count,
        "pass_rate_pct": pass_rate,
        "total_suite_latency_seconds": total_suite_latency_s,
        "category_summary": cat_summary,
        "queries": results_data,
    }

    out_file.write_text(json.dumps(run_payload, indent=2), encoding="utf-8")
    print(f"\nFull 100-query benchmark results saved to: {out_file.resolve()}\n")
    return run_payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run_100_benchmark()

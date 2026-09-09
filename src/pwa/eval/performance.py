"""Real-world performance and cost profiling suite for Polyglot Warehouse Agent (PWA).

Usage:
    python -m pwa.eval.performance [--limit N] [--concurrency-levels 1,5,10]
    pwa perf
"""

import argparse
import concurrent.futures
import datetime
import json
import logging
import numpy as np
import pathlib
import time
from typing import Any, Dict, List, Tuple

from pwa.agent.pipeline.orchestrator import PipelineResult, run_query_verbose
from pwa.agent.schema_cache import invalidate_schema_cache
from pwa.agent.semantic_cache import semantic_cache

logger = logging.getLogger("pwa.eval.performance")

_BENCHMARK_PATH = pathlib.Path(__file__).parent / "benchmark_queries.json"
_RESULTS_DIR = pathlib.Path(__file__).parent / "results"

# Pricing Configuration
BQ_PRICE_PER_TB = 6.25  # BigQuery On-Demand rate per TB
BQ_PRICE_PER_BYTE = BQ_PRICE_PER_TB / (1024**4)

LLM_INPUT_COST_PER_1M = 0.15  # Gemini 2.5 Flash / Groq input token rate
LLM_OUTPUT_COST_PER_1M = 0.60  # Gemini 2.5 Flash / Groq output token rate


def load_queries(limit: int | None = None) -> List[Dict[str, Any]]:
    """Load benchmark queries."""
    if _BENCHMARK_PATH.exists():
        data = json.loads(_BENCHMARK_PATH.read_text(encoding="utf-8"))
    else:
        data = json.loads(pathlib.Path("pwa/eval/benchmark_queries.json").read_text(encoding="utf-8"))
    return data[:limit] if limit else data


def _percentile(values: List[float], p: float) -> float:
    """Calculate p-th percentile from list of floats."""
    if not values:
        return 0.0
    return float(np.percentile(values, p))


def compute_cost(bytes_scanned: int, prompt_tokens: int = 250, completion_tokens: int = 150) -> Dict[str, float]:
    """Compute BigQuery and estimated LLM costs in USD."""
    bq_cost = bytes_scanned * BQ_PRICE_PER_BYTE
    llm_cost = (prompt_tokens * LLM_INPUT_COST_PER_1M / 1_000_000) + (
        completion_tokens * LLM_OUTPUT_COST_PER_1M / 1_000_000
    )
    total_cost = bq_cost + llm_cost
    return {
        "bq_cost_usd": round(bq_cost, 6),
        "llm_cost_usd": round(llm_cost, 6),
        "total_cost_usd": round(total_cost, 6),
    }


def run_single_query_record(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Run one query and return structured instrumentation record."""
    qid = entry["id"]
    cat = entry["category"]
    q = entry["question"]

    t0 = time.perf_counter()
    try:
        res = run_query_verbose(q, timeout_seconds=120.0)
    except Exception as exc:
        res = f"[EXCEPTION] {exc}"

    total_latency_ms = round((time.perf_counter() - t0) * 1000, 1)

    is_error = isinstance(res, str) or getattr(res, "exec_status", "SUCCESS") == "ERROR"

    if isinstance(res, PipelineResult):
        sql = res.sql
        rows_count = res.row_count
        bytes_scanned = res.bytes_scanned or 0
        actual_bytes = res.actual_bytes_processed or bytes_scanned
        slot_ms = res.slot_ms or 0
        latencies_ms = {k: round(v * 1000, 1) for k, v in res.stage_latencies.items()}
        retry_count = res.retry_count
        retry_reason = res.retry_reason
        cache_hit = res.cache_hit
    else:
        sql = None
        rows_count = 0
        bytes_scanned = 0
        actual_bytes = 0
        slot_ms = 0
        latencies_ms = {}
        retry_count = 0
        retry_reason = str(res) if is_error else None
        cache_hit = False

    cost_info = compute_cost(bytes_scanned)

    return {
        "id": qid,
        "category": cat,
        "question": q,
        "is_error": is_error,
        "total_latency_ms": total_latency_ms,
        "stage_latencies_ms": latencies_ms,
        "sql": sql,
        "row_count": rows_count,
        "bytes_scanned": bytes_scanned,
        "actual_bytes_processed": actual_bytes,
        "slot_ms": slot_ms,
        "cache_hit": cache_hit,
        "retry_count": retry_count,
        "retry_reason": retry_reason,
        "bq_cost_usd": cost_info["bq_cost_usd"],
        "llm_cost_usd": cost_info["llm_cost_usd"],
        "total_cost_usd": cost_info["total_cost_usd"],
    }


def run_scenario_sequential(queries: List[Dict[str, Any]], scenario_name: str) -> List[Dict[str, Any]]:
    """Run sequential scenario across query list."""
    print(f"\n---> Running Scenario: [{scenario_name}] ({len(queries)} queries)...")
    records = []
    for idx, q in enumerate(queries, 1):
        rec = run_single_query_record(q)
        records.append(rec)
        print(
            f"  [{idx:02d}/{len(queries):02d}] {rec['id']} ({rec['category']}): {rec['total_latency_ms']}ms | ${rec['total_cost_usd']:.6f}"
        )
    return records


def run_scenario_concurrency(queries: List[Dict[str, Any]], concurrency_level: int) -> Dict[str, Any]:
    """Run concurrency test scenario at given thread pool worker level."""
    print(f"\n---> Running Concurrency Scenario: Level={concurrency_level} ({len(queries)} queries)...")
    t0 = time.perf_counter()
    records = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency_level) as executor:
        futures = [executor.submit(run_single_query_record, q) for q in queries]
        for f in concurrent.futures.as_completed(futures):
            records.append(f.result())

    total_wall_s = round(time.perf_counter() - t0, 2)
    errors = sum(1 for r in records if r["is_error"])
    error_rate = round(100.0 * errors / len(records), 1) if records else 0.0
    latencies = [r["total_latency_ms"] for r in records]

    return {
        "concurrency": concurrency_level,
        "total_wall_seconds": total_wall_s,
        "error_rate_pct": error_rate,
        "error_count": errors,
        "p50_ms": _percentile(latencies, 50),
        "p90_ms": _percentile(latencies, 90),
        "p99_ms": _percentile(latencies, 99),
        "records": records,
    }


def generate_perf_report(
    cold_records: List[Dict[str, Any]],
    warm_records: List[Dict[str, Any]],
    repeat_records: List[Dict[str, Any]],
    concurrency_results: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], str]:
    """Compute statistics and generate markdown report."""
    # 1. Latency Percentiles (Cold vs Warm)
    cold_lats = [r["total_latency_ms"] for r in cold_records]
    warm_lats = [r["total_latency_ms"] for r in warm_records]

    stats_cold = {
        "p50": _percentile(cold_lats, 50),
        "p90": _percentile(cold_lats, 90),
        "p99": _percentile(cold_lats, 99),
    }
    stats_warm = {
        "p50": _percentile(warm_lats, 50),
        "p90": _percentile(warm_lats, 90),
        "p99": _percentile(warm_lats, 99),
    }

    # Stage Latency Percentiles
    stages = ["schema", "sql", "exec", "answer"]
    stage_percentiles = {}
    for stg in stages:
        stg_cold = [r["stage_latencies_ms"].get(stg, 0.0) for r in cold_records if stg in r["stage_latencies_ms"]]
        stage_percentiles[stg] = {
            "p50": _percentile(stg_cold, 50),
            "p90": _percentile(stg_cold, 90),
            "p99": _percentile(stg_cold, 99),
        }

    # 2. Cost Aggregates
    total_bq_cost = sum(r["bq_cost_usd"] for r in cold_records)
    total_llm_cost = sum(r["llm_cost_usd"] for r in cold_records)
    total_cost = total_bq_cost + total_llm_cost
    total_bytes = sum(r["bytes_scanned"] for r in cold_records)

    # 3. Bottleneck Ranking
    total_latency_sum = sum(cold_lats) or 1.0
    stage_shares = {}
    for stg in stages:
        stg_sum = sum(r["stage_latencies_ms"].get(stg, 0.0) for r in cold_records)
        stage_shares[stg] = round(100.0 * stg_sum / total_latency_sum, 1)

    latency_bottleneck = max(stage_shares.items(), key=lambda x: x[1])

    # 4. Category Breakdowns
    cats = set(r["category"] for r in cold_records)
    cat_stats = {}
    for c in cats:
        c_recs = [r for r in cold_records if r["category"] == c]
        c_lats = [r["total_latency_ms"] for r in c_recs]
        c_cost = sum(r["total_cost_usd"] for r in c_recs)
        cat_stats[c] = {
            "count": len(c_recs),
            "p50_ms": _percentile(c_lats, 50),
            "p90_ms": _percentile(c_lats, 90),
            "total_cost_usd": round(c_cost, 6),
        }

    # 5. Cache Effectiveness Delta
    cache_delta_ms = round(stats_cold["p50"] - stats_warm["p50"], 1)
    cache_delta_pct = round(100.0 * cache_delta_ms / stats_cold["p50"], 1) if stats_cold["p50"] else 0.0

    # 6. Data-Driven Recommendations
    recommendations = []
    if stage_shares.get("schema", 0) > 30:
        recommendations.append(
            f"Schema Grounding accounts for {stage_shares['schema']}% of total latency. Ensure schema TTL cache is warmed on boot."
        )
    if stage_shares.get("sql", 0) > 40:
        recommendations.append(
            f"SQL Generation accounts for {stage_shares['sql']}% of latency. Consider routing SQL generation to a lower-latency model tier."
        )
    if cat_stats.get("federated", {}).get("p50_ms", 0) > stats_cold["p50"] * 1.5:
        recommendations.append(
            f"Cross-engine federated queries (EXTERNAL_QUERY) have significantly higher P50 latency ({cat_stats['federated']['p50_ms']}ms vs {stats_cold['p50']}ms baseline). Optimize MySQL/Postgres connection pooling."
        )
    for c_res in concurrency_results:
        if c_res["error_rate_pct"] > 0:
            recommendations.append(
                f"Concurrency level {c_res['concurrency']} showed an error rate of {c_res['error_rate_pct']}%. Investigate shared BigQuery rate limits or connection pool capacity."
            )

    if not recommendations:
        recommendations.append("Pipeline performance is balanced across stages with low error rates under concurrency.")

    # Format Markdown Report
    report_md = f"""# Polyglot Warehouse Agent (PWA) Performance & Cost Report

**Generated:** {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Dataset Size:** {len(cold_records)} benchmark queries

---

## 1. Executive Summary & Cost Model
- **Total Suite Execution Cost:** `${total_cost:.6f}` (BigQuery: `${total_bq_cost:.6f}` · LLM Tokens: `${total_llm_cost:.6f}`)
- **Total BigQuery Bytes Scanned:** `{total_bytes / (1024 * 1024):.2f} MB` (`{total_bytes}` bytes)
- **BigQuery Pricing Rate:** `${BQ_PRICE_PER_TB:.2f} / TB` on-demand
- **Primary Latency Bottleneck:** `{latency_bottleneck[0]}` stage (`{latency_bottleneck[1]}%` of total latency)

---

## 2. End-to-End & Stage Latency Percentiles (Cold vs Warm)

| Scenario / Stage | P50 (ms) | P90 (ms) | P99 (ms) |
|---|---|---|---|
| **Cold Baseline (Overall)** | **{stats_cold["p50"]:.1f}** | **{stats_cold["p90"]:.1f}** | **{stats_cold["p99"]:.1f}** |
| **Warm Repeat (Overall)** | **{stats_warm["p50"]:.1f}** | **{stats_warm["p90"]:.1f}** | **{stats_warm["p99"]:.1f}** |
| Stage 1: Schema Grounding | {stage_percentiles["schema"]["p50"]:.1f} | {stage_percentiles["schema"]["p90"]:.1f} | {stage_percentiles["schema"]["p99"]:.1f} |
| Stage 2: SQL Generation | {stage_percentiles["sql"]["p50"]:.1f} | {stage_percentiles["sql"]["p90"]:.1f} | {stage_percentiles["sql"]["p99"]:.1f} |
| Stage 3: Validation & Execution | {stage_percentiles["exec"]["p50"]:.1f} | {stage_percentiles["exec"]["p90"]:.1f} | {stage_percentiles["exec"]["p99"]:.1f} |
| Stage 4: Answer Synthesis | {stage_percentiles["answer"]["p50"]:.1f} | {stage_percentiles["answer"]["p90"]:.1f} | {stage_percentiles["answer"]["p99"]:.1f} |

---

## 3. Cache Effectiveness
- **Cold P50 Latency:** `{stats_cold["p50"]:.1f} ms`
- **Warm P50 Latency:** `{stats_warm["p50"]:.1f} ms`
- **Cache Delta:** Saved **`{cache_delta_ms} ms`** (`{cache_delta_pct}%` latency reduction)

---

## 4. Category Performance & Cost Breakdown

| Category | Query Count | P50 Latency (ms) | P90 Latency (ms) | Total Cost ($) |
|---|---|---|---|---|
"""
    for c, st in cat_stats.items():
        report_md += (
            f"| `{c}` | {st['count']} | {st['p50_ms']:.1f} | {st['p90_ms']:.1f} | ${st['total_cost_usd']:.6f} |\n"
        )

    report_md += """
---

## 5. Concurrency Scaling Curve

| Concurrency Level | Total Wall Clock (s) | P50 Latency (ms) | P90 Latency (ms) | Error Rate (%) |
|---|---|---|---|---|
"""
    for c_res in concurrency_results:
        report_md += f"| **{c_res['concurrency']} worker(s)** | {c_res['total_wall_seconds']:.2f}s | {c_res['p50_ms']:.1f} | {c_res['p90_ms']:.1f} | {c_res['error_rate_pct']:.1f}% |\n"

    report_md += """
---

## 6. Actionable Next Steps & Optimization Recommendations

"""
    for idx, rec in enumerate(recommendations, 1):
        report_md += f"{idx}. {rec}\n"

    metrics_payload = {
        "stats_cold": stats_cold,
        "stats_warm": stats_warm,
        "stage_percentiles": stage_percentiles,
        "total_cost_usd": total_cost,
        "total_bq_cost_usd": total_bq_cost,
        "total_llm_cost_usd": total_llm_cost,
        "total_bytes_scanned": total_bytes,
        "stage_latency_shares_pct": stage_shares,
        "category_stats": cat_stats,
        "concurrency_scaling": concurrency_results,
        "recommendations": recommendations,
    }

    return metrics_payload, report_md


def run_performance_suite(
    limit: int | None = None,
    concurrency_levels: List[int] | None = None,
) -> Dict[str, Any]:
    """Run all 4 operational performance scenarios."""
    queries = load_queries(limit)
    conc_levels = concurrency_levels or [1, 5, 10]

    print("\n================================================================================")
    print("  PWA Real-World Pipeline Performance & Cost Profiler")
    print(f"  Total Queries: {len(queries)} | Concurrency Levels: {conc_levels}")
    print("================================================================================\n")

    # 1. Cold-cache baseline
    invalidate_schema_cache()
    semantic_cache.clear()
    cold_records = run_scenario_sequential(queries, "Cold-Cache Baseline")

    # 2. Warm-cache repeat
    warm_records = run_scenario_sequential(queries, "Warm-Cache Repeat")

    # 3. Repeated-sample run (subset 10 queries 3x)
    subset_queries = queries[: min(10, len(queries))]
    print("\n---> Running Scenario: [Repeated Sampling] (10 queries x 3 passes)...")
    repeat_records = []
    for pass_num in range(1, 4):
        print(f"  Pass {pass_num}/3:")
        repeat_records.extend(run_scenario_sequential(subset_queries, f"Repeated Sample Pass {pass_num}"))

    # 4. Concurrency test
    concurrency_results = []
    for c_lvl in conc_levels:
        c_res = run_scenario_concurrency(subset_queries, c_lvl)
        concurrency_results.append(c_res)

    # Generate Metrics & Report
    metrics, report_md = generate_perf_report(cold_records, warm_records, repeat_records, concurrency_results)

    print("\n" + report_md)

    # Save Output Artifacts
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    json_file = _RESULTS_DIR / f"perf_run_{timestamp}.json"
    md_file = _RESULTS_DIR / f"perf_report_{timestamp}.md"

    full_payload = {
        "timestamp": timestamp,
        "metrics": metrics,
        "scenarios": {
            "cold_cache": cold_records,
            "warm_cache": warm_records,
            "repeated_sampling": repeat_records,
            "concurrency": concurrency_results,
        },
    }

    json_file.write_text(json.dumps(full_payload, indent=2), encoding="utf-8")
    md_file.write_text(report_md, encoding="utf-8")

    print(f"\nRaw performance data saved to: {json_file.resolve()}")
    print(f"Markdown performance report saved to: {md_file.resolve()}\n")

    return full_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PWA Pipeline Performance & Cost Profiler")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of queries")
    parser.add_argument("--concurrency-levels", type=str, default="1,5,10", help="Comma-separated concurrency levels")

    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    conc_levels = [int(x.strip()) for x in args.concurrency_levels.split(",") if x.strip()]
    run_performance_suite(limit=args.limit, concurrency_levels=conc_levels)


if __name__ == "__main__":
    main()

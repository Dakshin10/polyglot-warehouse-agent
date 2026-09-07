"""Console entry point. Every command exits non-zero on any failure."""

import argparse
import logging
import sys

from pwa.logging_setup import setup_logging

logger = logging.getLogger("pwa.cli")

USAGE = """\
pwa audit                 Parts 1-6 of the audit, read-only
pwa audit --apply         also performs the classified deletions
pwa config                validate and print the redacted settings table
pwa source run            download -> transform -> load -> gates 1-13
pwa source verify         gates 1-13 only
pwa warehouse run         setup -> land -> mart -> gates B1-B15
pwa warehouse verify      gates B1-B15 only
pwa all                   source run then warehouse run
pwa query "<question>"    NLP query against BigQuery mart views
pwa query --interactive   interactive REPL question-answering loop
pwa query --show-sql      print SQL and per-stage latency after the answer
pwa eval                  run golden regression evaluation suite
"""


def cmd_config() -> int:
    """Validate settings and print the redacted table."""
    from pwa.settings import get_settings

    try:
        settings = get_settings()
    except Exception as e:
        print(f"\nConfiguration validation FAILED:\n{e}\n", file=sys.stderr)
        return 1

    print("\n" + "=" * 80)
    print(f"{'SETTING':<30} | {'VALUE'}")
    print("-" * 80)
    for name, value in settings.redacted_rows():
        print(f"{name:<30} | {value}")
    print("=" * 80)
    print("Settings validation: PASSED (all rules satisfied)")
    return 0


def cmd_audit(apply_deletions: bool) -> int:
    from pwa.audit import run_audit

    return run_audit(apply_deletions=apply_deletions)


def cmd_source_run() -> int:
    from pwa.run_source import run_source_pipeline

    return 0 if run_source_pipeline() else 1


def cmd_source_verify() -> int:
    from pwa.gates_source import run_all_gates

    return 0 if run_all_gates() else 1


def cmd_warehouse_run() -> int:
    from pwa.run_bigquery import run_warehouse_pipeline

    return 0 if run_warehouse_pipeline() else 1


def cmd_warehouse_verify() -> int:
    from pwa.gates_bigquery import run_all_bq_gates

    return 0 if run_all_bq_gates() else 1


def cmd_all() -> int:
    print("=== RUNNING SOURCE PIPELINE ===")
    rc = cmd_source_run()
    if rc != 0:
        logger.error("Source pipeline failed; not starting the warehouse pipeline.")
        return rc
    print("\n=== RUNNING WAREHOUSE PIPELINE ===")
    return cmd_warehouse_run()


def cmd_eval() -> int:
    """Run the golden regression evaluation suite."""
    from pwa.agent.pipeline.eval.run_eval import run_eval
    return run_eval()


def cmd_benchmark(limit: int | None = None, fail_under: float | None = None) -> int:
    """Run the 50-query live benchmark harness."""
    from pwa.eval.benchmark import run_benchmark
    try:
        run_benchmark(limit=limit, fail_under=fail_under)
        return 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    except Exception as exc:
        print(f"Benchmark error: {exc}", file=sys.stderr)
        return 1


def cmd_perf(limit: int | None = None) -> int:
    """Run the multi-scenario performance & cost profiler."""
    from pwa.eval.performance import run_performance_suite
    try:
        run_performance_suite(limit=limit)
        return 0
    except Exception as exc:
        print(f"Performance profiler error: {exc}", file=sys.stderr)
        return 1


def cmd_refresh_rollups() -> int:
    """Recompute and materialize BigQuery rollup tables from mart views."""
    from pwa.rollups import refresh_rollups
    return 0 if refresh_rollups() else 1


def cmd_query(question: str, interactive: bool, model: str | None, verbose: bool, show_sql: bool = False) -> int:
    """Run NLP query agent against BigQuery mart views in one-shot or interactive REPL mode."""
    import os
    import time

    from pwa.agent.pipeline.orchestrator import run_query, run_query_verbose

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("pwa").setLevel(logging.DEBUG)
        logging.getLogger("google.auth.transport.requests").setLevel(logging.DEBUG)
        logging.getLogger("google_genai").setLevel(logging.DEBUG)
        logging.getLogger("google.genai").setLevel(logging.DEBUG)
        logging.getLogger("google.auth").setLevel(logging.DEBUG)
        logging.getLogger("httpx").setLevel(logging.DEBUG)
        logging.getLogger("urllib3").setLevel(logging.DEBUG)
        for handler in logging.getLogger().handlers:
            handler.setLevel(logging.DEBUG)

    if model:
        os.environ["PWA_AGENT_MODEL"] = model

    if interactive:
        print("\n=== Polyglot Warehouse Agent - Interactive NLP Query CLI ===")
        print("Type your question and press Enter. Type 'exit', 'quit', or 'q' to quit.\n")
        while True:
            try:
                user_input = input("pwa query> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Goodbye!")
                break

            try:
                t0 = time.perf_counter()
                answer = run_query(user_input)
                elapsed = time.perf_counter() - t0
                print(f"\n{answer}\n")
                print(f"⏱  {elapsed:.1f}s total")
            except Exception as e:
                print(f"\nError: {e}\n", file=sys.stderr)
        return 0

    if not question:
        print("Error: Question required for one-shot query (or use --interactive / -i)", file=sys.stderr)
        return 1

    try:
        t0 = time.perf_counter()
        result = run_query_verbose(question)
        elapsed = time.perf_counter() - t0

        answer = result if isinstance(result, str) else result.answer
        print(f"\n{answer}\n")

        # Always print timing summary
        print("-" * 52)
        if hasattr(result, "stage_latencies") and result.stage_latencies:
            lats = result.stage_latencies
            if "routing" in lats:
                print(f"  routing          : {lats['routing']:.2f}s")
            if "schema" in lats:
                print(f"  schema grounding : {lats['schema']:.2f}s")
            if "sql" in lats:
                print(f"  sql generation   : {lats['sql']:.2f}s")
            if "exec" in lats:
                print(f"  bq execution     : {lats['exec']:.2f}s")
            if "answer" in lats:
                print(f"  answer synthesis : {lats['answer']:.2f}s")
            print(f"  " + "-" * 38)
        print(f"  total wall time  : {elapsed:.2f}s")
        if hasattr(result, "stage_details") and result.stage_details and "routing_path" in result.stage_details:
            print(f"  routing path     : {result.stage_details['routing_path']}")
        if hasattr(result, "bytes_scanned") and result.bytes_scanned is not None:
            mb = result.bytes_scanned / 1_000_000
            print(f"  bytes scanned    : {mb:.1f} MB")
        if hasattr(result, "cache_hit") and result.cache_hit:
            print(f"  cache hit        : yes")
        print("-" * 52)

        if show_sql and hasattr(result, "sql") and result.sql:
            print(f"\nGenerated SQL:\n{result.sql}\n")

        if isinstance(result, str) and any(
            ref in answer.lower()
            for ref in ["refused:", "rate limit exceeded", "query too broad", "security violation"]
        ):
            return 1
        return 0
    except Exception as e:
        print(f"Error executing query: {e}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pwa",
        description="Polyglot Warehouse Agent CLI",
        epilog=USAGE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    audit = sub.add_parser("audit", help="Run the read-only audit (Parts 1-6)")
    audit.add_argument(
        "--apply",
        action="store_true",
        help="perform the classified deletions instead of only listing them",
    )

    sub.add_parser("config", help="Validate settings and print the redacted table")

    source = sub.add_parser("source", help="Source database pipeline")
    source.add_argument("action", choices=["run", "verify"])

    warehouse = sub.add_parser("warehouse", help="BigQuery warehouse pipeline")
    warehouse.add_argument("action", choices=["run", "verify"])

    sub.add_parser("all", help="Run the source pipeline then the warehouse pipeline")
    sub.add_parser("refresh-rollups", help="Recompute and materialize BigQuery rollup tables from mart views")

    query = sub.add_parser("query", help="Run NLP query agent against warehouse mart data")
    query.add_argument("question", nargs="?", default="", help="Natural language question to ask")
    query.add_argument("--interactive", "-i", action="store_true", help="Run interactive REPL question-answering loop")
    query.add_argument(
        "--model", "-m", choices=["gemini", "groq"], default=None, help="Override model backend (gemini or groq)"
    )
    query.add_argument("--verbose", "-v", action="store_true", help="Print verbose per-stage debug traces")
    query.add_argument("--show-sql", action="store_true", help="Print generated SQL and per-stage latency after answer")

    sub.add_parser("eval", help="Run golden regression evaluation suite")

    bench = sub.add_parser("benchmark", help="Run 50-query live pipeline benchmark harness")
    bench.add_argument("--limit", type=int, default=None, help="Limit number of queries")
    bench.add_argument("--fail-under", type=float, default=None, help="Fail if pass rate is under PCT")

    perf = sub.add_parser("perf", help="Run multi-scenario performance and cost profiler")
    perf.add_argument("--limit", type=int, default=None, help="Limit number of queries")

    return parser


def main() -> None:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "audit":
        sys.exit(cmd_audit(args.apply))
    if args.command == "config":
        sys.exit(cmd_config())
    if args.command == "source":
        sys.exit(cmd_source_run() if args.action == "run" else cmd_source_verify())
    if args.command == "warehouse":
        sys.exit(cmd_warehouse_run() if args.action == "run" else cmd_warehouse_verify())
    if args.command == "all":
        sys.exit(cmd_all())
    if args.command == "refresh-rollups":
        sys.exit(cmd_refresh_rollups())
    if args.command == "query":
        sys.exit(cmd_query(args.question, args.interactive, args.model, args.verbose, getattr(args, "show_sql", False)))
    if args.command == "eval":
        sys.exit(cmd_eval())
    if args.command == "benchmark":
        sys.exit(cmd_benchmark(limit=args.limit, fail_under=args.fail_under))
    if args.command == "perf":
        sys.exit(cmd_perf(limit=args.limit))

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()

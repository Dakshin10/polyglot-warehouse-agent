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

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()

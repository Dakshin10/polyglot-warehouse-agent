import sys
import argparse
from pwa.logging_setup import setup_logging, RedactingFilter
from pwa.settings import get_settings
from pwa.run_source import run_source_pipeline
from pwa.run_bigquery import run_warehouse_pipeline
from pwa.gates_source import run_all_gates as run_source_gates
from pwa.gates_bigquery import run_all_bq_gates as run_warehouse_gates


def cmd_config_check():
    """Validate settings and print redacted table."""
    try:
        settings = get_settings()
        redacter = RedactingFilter()

        print("\n" + "=" * 80)
        print(f"{'SETTING':<30} | {'VALUE'}")
        print("-" * 80)
        for field, val in settings.__dict__.items():
            val_str = str(val)
            if "password" in field or "key" in field or "secret" in field:
                val_str = "***"
            else:
                val_str = redacter.redact(val_str)
            print(f"{field:<30} | {val_str}")
        print("=" * 80)
        print("Settings validation: PASSED (all rules satisfied)")
        return 0
    except Exception as e:
        print(f"\nConfiguration validation FAILED:\n{e}", file=sys.stderr)
        return 1


def main():
    """CLI entry point for pwa executable."""
    setup_logging()

    parser = argparse.ArgumentParser(prog="pwa", description="Polyglot Warehouse Agent CLI")
    subparsers = parser.add_subparsers(dest="group", help="Command groups")

    # pwa config check
    config_parser = subparsers.add_parser("config", help="Configuration commands")
    config_sub = config_parser.add_subparsers(dest="subcommand")
    config_sub.add_parser("check", help="Validate settings and print redacted table")

    # pwa source run / verify
    source_parser = subparsers.add_parser("source", help="Source database pipeline commands")
    source_sub = source_parser.add_subparsers(dest="subcommand")
    source_sub.add_parser("run", help="Run source ETL pipeline (download -> transform -> load -> gates 1-13)")
    source_sub.add_parser("verify", help="Run gates 1-13 verification only")

    # pwa warehouse run / verify
    wh_parser = subparsers.add_parser("warehouse", help="Warehouse BigQuery pipeline commands")
    wh_sub = wh_parser.add_subparsers(dest="subcommand")
    wh_sub.add_parser("run", help="Run warehouse pipeline (setup -> land -> mart -> gates B1-B15)")
    wh_sub.add_parser("verify", help="Run gates B1-B15 verification only")

    # pwa all
    subparsers.add_parser("all", help="Run source pipeline then warehouse pipeline")

    args = parser.parse_args()

    if args.group == "config":
        if args.subcommand == "check":
            sys.exit(cmd_config_check())
        else:
            config_parser.print_help()
            sys.exit(1)

    elif args.group == "source":
        if args.subcommand == "run":
            run_source_pipeline()
            sys.exit(0)
        elif args.subcommand == "verify":
            ok = run_source_gates()
            sys.exit(0 if ok else 1)
        else:
            source_parser.print_help()
            sys.exit(1)

    elif args.group == "warehouse":
        if args.subcommand == "run":
            run_warehouse_pipeline()
            sys.exit(0)
        elif args.subcommand == "verify":
            ok = run_warehouse_gates()
            sys.exit(0 if ok else 1)
        else:
            wh_parser.print_help()
            sys.exit(1)

    elif args.group == "all":
        print("=== RUNNING SOURCE PIPELINE ===")
        run_source_pipeline()
        print("\n=== RUNNING WAREHOUSE PIPELINE ===")
        run_warehouse_pipeline()
        sys.exit(0)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

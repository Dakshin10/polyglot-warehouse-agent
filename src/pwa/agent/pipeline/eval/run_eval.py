"""Golden regression evaluation runner for the PWA NL→SQL pipeline.

Usage:
    python -m pwa.agent.pipeline.eval.run_eval
    pwa eval  (if CLI sub-command is wired)

Exit code: 0 if all entries pass, 1 if any fail.

Each entry in golden_set.json is evaluated with match_mode:
  "keyword" — at least one expected_answer_keyword must appear (case-insensitive)
              in the final synthesised answer.

Results are printed as a rich ASCII table with per-entry PASS/FAIL and a summary.
"""

import json
import logging
import pathlib
import sys
import time
from typing import Any

logger = logging.getLogger("pwa.agent.pipeline.eval.run_eval")

_GOLDEN_PATH = pathlib.Path(__file__).parent / "golden_set.json"

_RESET = "\033[0m"
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_BOLD = "\033[1m"


def _colour(text: str, code: str) -> str:
    """Wrap text in ANSI colour code."""
    return f"{code}{text}{_RESET}"


def _load_golden_set() -> list[dict[str, Any]]:
    try:
        return json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[ERROR] Could not load golden set from {_GOLDEN_PATH}: {exc}")
        sys.exit(1)


def _evaluate_entry(entry: dict[str, Any], answer: str) -> tuple[bool, str]:
    """Evaluate a single golden entry against the pipeline answer.

    Returns:
        (passed, reason_string)
    """
    mode = entry.get("match_mode", "keyword")

    if mode == "keyword":
        keywords = entry.get("expected_answer_keywords", [])
        if not keywords:
            return True, "No keywords specified (auto-pass)"
        answer_lower = answer.lower()
        matched = [kw for kw in keywords if kw.lower() in answer_lower]
        if matched:
            return True, f"Matched keywords: {matched}"
        else:
            return False, f"Missing all keywords: {keywords}"

    elif mode == "sql_exact":
        expected_sql = entry.get("expected_sql", "").strip()
        # Compare normalised SQL (collapse whitespace)
        import re

        def _norm(s: str) -> str:
            return re.sub(r"\s+", " ", s.strip().lower())

        if _norm(answer) == _norm(expected_sql):
            return True, "SQL exact match"
        else:
            return False, f"SQL mismatch.\n  Expected: {expected_sql}\n  Got:      {answer}"

    else:
        return False, f"Unknown match_mode: '{mode}'"


def run_eval(
    golden_path: pathlib.Path = _GOLDEN_PATH,
    timeout_per_question: float = 120.0,
) -> int:
    """Run the full golden evaluation suite.

    Args:
        golden_path:            Path to the golden_set.json file.
        timeout_per_question:   Per-question pipeline timeout in seconds.

    Returns:
        Exit code: 0 if all pass, 1 otherwise.
    """
    # Import here so that the module can be imported without starting the pipeline
    from pwa.agent.pipeline.orchestrator import run_query

    entries = json.loads(golden_path.read_text(encoding="utf-8"))
    total = len(entries)
    passed = 0
    failed = 0
    results = []

    def _truncate(text: str, width: int) -> str:
        return text if len(text) <= width else text[: width - 3] + "..."

    print(f"\n{_BOLD}=== PWA Golden Regression Evaluation ==={_RESET}")
    print(f"Golden set: {golden_path}  ({total} entries)\n")
    print(
        f"{'ID':<6}  {'Question':<50}  {'Status':<8}  {'Latency':<10}  Reason"
    )
    print("-" * 120)

    for entry in entries:
        eid = entry.get("id", "?")
        question = entry.get("question", "")
        t0 = time.perf_counter()
        try:
            answer = run_query(question, timeout_seconds=timeout_per_question)
        except Exception as exc:
            answer = f"[EXCEPTION] {exc}"
        latency = time.perf_counter() - t0

        passed_entry, reason = _evaluate_entry(entry, answer)

        status_str = (
            _colour("PASS", _GREEN) if passed_entry else _colour("FAIL", _RED)
        )
        print(
            f"{eid:<6}  {_truncate(question, 50):<50}  {status_str:<8}  "
            f"{latency:>7.2f}s    {_truncate(reason, 60)}"
        )

        if passed_entry:
            passed += 1
        else:
            failed += 1
            logger.debug(f"[FAIL {eid}] Answer was: {answer[:200]}")

        results.append(
            {
                "id": eid,
                "question": question,
                "passed": passed_entry,
                "latency_seconds": round(latency, 2),
                "reason": reason,
                "answer_preview": answer[:200],
            }
        )

    print("-" * 120)
    pass_rate = round(100 * passed / total, 1) if total else 0
    summary_colour = _GREEN if failed == 0 else _RED
    print(
        f"\n{_BOLD}Summary:{_RESET}  "
        f"{_colour(str(passed), _GREEN)} passed  "
        f"{_colour(str(failed), _RED)} failed  "
        f"({_colour(f'{pass_rate}%', summary_colour)} pass rate)"
    )

    # Write JSON report next to the golden set
    report_path = golden_path.parent / "eval_report.json"
    report_path.write_text(json.dumps({"passed": passed, "failed": failed, "entries": results}, indent=2))
    print(f"\nFull report written to: {report_path}\n")

    return 0 if failed == 0 else 1


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(level=logging.WARNING)
    exit_code = run_eval()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

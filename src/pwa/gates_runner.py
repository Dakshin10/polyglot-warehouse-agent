import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger("gates.runner")


@dataclass
class GateResult:
    id: str  # e.g., "GATE 1", "GATE B14"
    name: str  # Human-readable title
    passed: bool  # True if gate criteria met
    detail: str  # Actual output, stats, or error
    mutating: bool = False  # True if gate mutates state and requires cleanup


Gate = Callable[[], GateResult]


def run_gates(gates: list[Gate], title: str = "VERIFICATION GATES") -> bool:
    """Execute a list of Gate callables, print aligned summary table, return True if all passed."""
    results: list[GateResult] = []
    all_passed = True

    print("\n" + "=" * 95)
    print(f"   STARTING {title.upper()}")
    print("=" * 95)

    for gate_fn in gates:
        try:
            res = gate_fn()
        except Exception as e:
            # A gate that cannot execute MUST fail, never skip
            fn_name = getattr(gate_fn, "__name__", str(gate_fn))
            res = GateResult(
                id="GATE ?",
                name=fn_name,
                passed=False,
                detail=f"CANNOT VERIFY: {e}",
            )

        results.append(res)
        if not res.passed:
            all_passed = False

    # Summary Table
    print("\n" + "=" * 95)
    print(f"{'GATE':<10} | {'DESCRIPTION':<50} | {'STATUS':<8} | {'DETAILS'}")
    print("-" * 95)
    for r in results:
        status_str = "PASS" if r.passed else "FAIL"
        print(f"{r.id:<10} | {r.name:<50} | {status_str:<8} | {r.detail}")
    print("=" * 95 + "\n")

    if not all_passed:
        logger.error(f"FATAL: One or more gates in {title} failed.")
        return False

    logger.info(f"=== ALL GATES IN {title} PASSED SUCCESSFULLY ===")
    return True

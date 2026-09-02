"""Shared scaffolding for the verification gates.

There is deliberately no SKIP status. A gate that cannot execute returns
`passed=False` with `detail="CANNOT VERIFY: <error>"`. Making the "we did not
check" state unrepresentable is what prevents a false green.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger("pwa.gates")


@dataclass
class GateResult:
    id: str  # "1", "B14"
    name: str
    passed: bool
    detail: str  # actual vs expected, or the error
    mutating: bool = False  # gate changes state and must restore it
    extra: list[str] = field(default_factory=list)  # optional block printed after the table


Gate = Callable[[], GateResult]


def cannot_verify(gate_id: str, name: str, error: object, mutating: bool = False) -> GateResult:
    """Build the failing result for a gate that could not execute."""
    return GateResult(id=gate_id, name=name, passed=False, detail=f"CANNOT VERIFY: {error}", mutating=mutating)


def run_gates(gates: list[Gate], title: str = "VERIFICATION GATES") -> bool:
    """Run every gate, print the aligned summary table, and return True only if all passed."""
    results: list[GateResult] = []

    logger.info(f"=== STARTING {title.upper()} ===")

    for gate_fn in gates:
        gate_id = getattr(gate_fn, "gate_id", "?")
        gate_name = getattr(gate_fn, "gate_name", getattr(gate_fn, "__name__", str(gate_fn)))
        try:
            results.append(gate_fn())
        except Exception as e:
            results.append(cannot_verify(gate_id, gate_name, e))

    print("\n" + "=" * 95)
    print(f"{'GATE':<10} | {'DESCRIPTION':<50} | {'STATUS':<8} | {'DETAILS'}")
    print("-" * 95)
    for r in results:
        print(f"{('GATE ' + r.id):<10} | {r.name:<50} | {('PASS' if r.passed else 'FAIL'):<8} | {r.detail}")
    print("=" * 95 + "\n")

    for r in results:
        for block in r.extra:
            print(block)
            print("=" * 95 + "\n")

    failed = [r for r in results if not r.passed]
    if failed:
        logger.error(
            f"FATAL: {len(failed)} of {len(results)} gates in {title} failed: " + ", ".join(r.id for r in failed)
        )
        return False

    logger.info(f"=== ALL {len(results)} GATES IN {title} PASSED SUCCESSFULLY ===")
    return True


def gate(gate_id: str, name: str, mutating: bool = False):
    """Tag a gate function with its id, description and mutating flag."""

    def decorate(fn):
        fn.gate_id = gate_id
        fn.gate_name = name
        fn.mutating = mutating
        return fn

    return decorate

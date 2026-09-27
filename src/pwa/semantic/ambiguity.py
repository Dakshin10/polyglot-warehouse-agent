"""Ambiguity resolution model for analytical requests."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

AMBIGUOUS_MAPPINGS: dict[str, list[str]] = {
    "sales": ["revenue (Sales Revenue in USD)", "order_count (Total Sales Order Count)", "quantity_sold (Units Sold)"],
    "customers": ["customer_count (Total Customers)", "dim_customer (Customer Master Records)"],
    "purchases": ["purchase_amount (Procurement Total in USD)", "purchase_order_count (Total Purchase Orders)"],
    "stock": ["inventory_quantity (Total Inventory On Hand)"],
}

UNAMBIGUOUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bsales\s+revenue\b",
        r"\btotal\s+sales\s+revenue\b",
        r"\bsales\s+order\s+count\b",
        r"\bquantity\s+sold\b",
        r"\bunits\s+sold\b",
        r"\bpurchase\s+amount\b",
        r"\bexpenditure\b",
        r"\bpurchase\s+order\s+count\b",
        r"\bpurchase\s+order\s+expenditure\b",
        r"\bcustomer\s+count\b",
        r"\brevenue\b",
        r"\border\s+count\b",
        r"\bsales\s+orders?\b",
        r"\bsales\s+order\s+totals?\b",
        r"\bsales\s+order\s+items?\b",
        r"\bsales\s+order\s+counts?\b",
        r"\bsales\s+order\s+headers?\b",
        r"\bsales\s+order\s+line\s+items?\b",
        r"\bsales\s+volume\b",
        r"\bmarketplace\s+customers?\b",
        r"\bdim_customer\b",
        r"\bcustomers?\s+in\s+dim_customer\b",
        r"\bsales\s+opportunities?\b",
        r"\bsales\s+opportunities?\s+won\b",
        r"\bclosed\s+deals?\b",
        r"\boption\s*\d+\b",
        r"\byes\b",
        r"\bno\b",
    ]
]


@dataclass
class AmbiguityResult:
    """Represents an ambiguity evaluation result."""

    term: str
    is_ambiguous: bool
    possible_interpretations: list[str] = field(default_factory=list)
    clarification_message: Optional[str] = None


class AmbiguityModel:
    """Model evaluating whether an analytical query term requires user clarification."""

    def evaluate_term(self, term: str) -> AmbiguityResult:
        text_lower = term.lower().strip()

        # If question contains an explicit unambiguous metric phrase or user choice, bypass ambiguity check
        for pattern in UNAMBIGUOUS_PATTERNS:
            if pattern.search(text_lower):
                return AmbiguityResult(term=term, is_ambiguous=False)

        for key, options in AMBIGUOUS_MAPPINGS.items():
            if re.search(r"\b" + re.escape(key) + r"\b", text_lower):
                return AmbiguityResult(
                    term=key,
                    is_ambiguous=True,
                    possible_interpretations=options,
                    clarification_message=f"The term '{key}' is ambiguous. Did you mean: {', '.join(options)}?",
                )
        return AmbiguityResult(term=term, is_ambiguous=False)

    def evaluate_candidates(
        self,
        candidates: list[tuple[str, float]],
        threshold_gap: float = 0.08,
        min_confidence: float = 0.25,
    ) -> AmbiguityResult:
        """Evaluate candidate entity/measure matches for low confidence or close score ties."""
        if not candidates:
            return AmbiguityResult(
                term="unknown",
                is_ambiguous=True,
                possible_interpretations=[],
                clarification_message=(
                    "I could not map this question to any known enterprise data entity "
                    "(sales, products, customers, suppliers, employees, inventory, leads). "
                    "Could you rephrase it in terms of one of these areas?"
                ),
            )

        top1_name, top1_score = candidates[0]
        if top1_score < min_confidence:
            return AmbiguityResult(
                term=top1_name,
                is_ambiguous=True,
                possible_interpretations=[c[0] for c in candidates[:3]],
                clarification_message=(
                    f"Low confidence matching '{top1_name}'. "
                    f"Did you mean: {', '.join(c[0] for c in candidates[:3])}?"
                ),
            )

        if len(candidates) >= 2:
            top2_name, top2_score = candidates[1]
            if (top1_score - top2_score < threshold_gap) and top1_score < 0.85:
                return AmbiguityResult(
                    term=f"{top1_name} vs {top2_name}",
                    is_ambiguous=True,
                    possible_interpretations=[top1_name, top2_name],
                    clarification_message=(
                        f"Your question could refer to either '{top1_name}' or '{top2_name}'. "
                        f"Which one did you mean?"
                    ),
                )

        return AmbiguityResult(term=top1_name, is_ambiguous=False)


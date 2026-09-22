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


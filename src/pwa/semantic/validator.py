"""Semantic catalog validation engine for PWA enterprise platform."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pwa.semantic.models import SemanticCatalog

logger = logging.getLogger("pwa.semantic.validator")


@dataclass
class ValidationIssue:
    """Represents a validation issue identified during semantic audit."""

    level: str  # ERROR | WARNING
    category: str  # ENTITY | DIMENSION | MEASURE | METRIC | RELATIONSHIP | GLOSSARY
    name: str
    message: str


@dataclass
class ValidationReport:
    """Unified report returned by SemanticValidator."""

    is_valid: bool
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)


class SemanticValidator:
    """Validator auditing integrity, relationships, and formula safety of a SemanticCatalog."""

    def validate_catalog(self, catalog: SemanticCatalog) -> ValidationReport:
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []

        # 1. Validate Entities
        for name, entity in catalog.entities.items():
            if not entity.primary_key:
                warnings.append(
                    ValidationIssue("WARNING", "ENTITY", name, f"Entity '{name}' has no explicit primary_key defined.")
                )
            if not entity.grain:
                errors.append(
                    ValidationIssue("ERROR", "ENTITY", name, f"Entity '{name}' must have an explicit grain definition.")
                )

        # 2. Validate Dimensions
        for name, dim in catalog.dimensions.items():
            if dim.entity and dim.entity not in catalog.entities:
                errors.append(
                    ValidationIssue(
                        "ERROR", "DIMENSION", name, f"Dimension '{name}' references unknown entity '{dim.entity}'."
                    )
                )

        # 3. Validate Measures
        for name, measure in catalog.measures.items():
            if measure.entity and measure.entity not in catalog.entities:
                errors.append(
                    ValidationIssue(
                        "ERROR", "MEASURE", name, f"Measure '{name}' references unknown entity '{measure.entity}'."
                    )
                )
            if measure.aggregation not in ("SUM", "COUNT", "AVG", "MIN", "MAX", "COUNT_DISTINCT"):
                errors.append(
                    ValidationIssue(
                        "ERROR",
                        "MEASURE",
                        name,
                        f"Measure '{name}' has unsupported aggregation '{measure.aggregation}'.",
                    )
                )

        # 4. Validate Metrics & Division-By-Zero Safety
        for name, metric in catalog.metrics.items():
            formula_upper = metric.formula.upper()
            if "/" in metric.formula and "NULLIF" not in formula_upper:
                warnings.append(
                    ValidationIssue(
                        "WARNING",
                        "METRIC",
                        name,
                        f"Metric '{name}' contains division ('/') without NULLIF protection against division-by-zero.",
                    )
                )
            for m_used in metric.measures_used:
                if m_used.lower() not in catalog.measures:
                    warnings.append(
                        ValidationIssue(
                            "WARNING",
                            "METRIC",
                            name,
                            f"Metric '{name}' references measure '{m_used}' not found in measures catalog.",
                        )
                    )

        # 5. Validate Relationships
        for name, rel in catalog.relationships.items():
            if rel.source_entity and rel.source_entity not in catalog.entities:
                errors.append(
                    ValidationIssue(
                        "ERROR",
                        "RELATIONSHIP",
                        name,
                        f"Relationship '{name}' references unknown source_entity '{rel.source_entity}'.",
                    )
                )
            if rel.target_entity and rel.target_entity not in catalog.entities:
                errors.append(
                    ValidationIssue(
                        "ERROR",
                        "RELATIONSHIP",
                        name,
                        f"Relationship '{name}' references unknown target_entity '{rel.target_entity}'.",
                    )
                )

        is_valid = len(errors) == 0
        report = ValidationReport(is_valid=is_valid, errors=errors, warnings=warnings)

        if is_valid:
            logger.info(f"[SemanticValidator] Validation PASSED with {len(warnings)} warning(s).")
        else:
            logger.error(
                f"[SemanticValidator] Validation FAILED with {len(errors)} error(s) and {len(warnings)} warning(s)."
            )

        return report

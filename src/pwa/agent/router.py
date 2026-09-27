"""Agent 0 — Intent & Query Router for Nexora Enterprise Platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
import logging

from pwa.semantic.ambiguity import AmbiguityModel

logger = logging.getLogger("pwa.agent.router")


class QueryCategory(str, Enum):
    ANALYTICAL = "ANALYTICAL"
    SEMANTIC_LOOKUP = "SEMANTIC_LOOKUP"
    DATA_EXPLORATION = "DATA_EXPLORATION"
    SYSTEM_METADATA = "SYSTEM_METADATA"
    UNSUPPORTED = "UNSUPPORTED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class RoutingDecision:
    """Output structure returned by Agent 0 Query Router."""

    question: str
    category: QueryCategory
    confidence: float
    reasoning: str
    suggested_action: str
    ambiguity_options: list[str] = field(default_factory=list)
    clarification_message: str = ""
    workflow_template_hint: str | None = None


class QueryRouter:
    """Agent 0 router evaluating user questions before pipeline execution."""

    def __init__(self, ambiguity_model: AmbiguityModel | None = None) -> None:
        self.ambiguity_model = ambiguity_model or AmbiguityModel()

        # Keywords triggering UNSUPPORTED classification
        self.mutation_keywords = re.compile(
            r"\b("
            r"insert\s+(?:into\s+)?|update\s+\w+|delete\s+(?:from\s+)?|truncate\s+(?:table\s+)?|"
            r"alter\s+table|create\s+(?:table|database|view|schema)|grant\b|revoke\b|merge\s+into|run shell\b|"
            r"drop\s+(?:the\s+|a\s+|an\s+)?(?:table|database|schema|dataset|view|index|partition|column|(?:[a-z0-9_]+\s+)+table)"
            r")\b",
            re.IGNORECASE,
        )
        self.unsupported_topics = re.compile(
            r"\b(movie|director|actor|film|box office|weather|recipe|crypto|bitcoin)\b",
            re.IGNORECASE,
        )

        # Keywords for metadata/exploration
        self.semantic_keywords = re.compile(
            r"\b(what is|define|meaning of|glossary|definition of)\s+([a-z_]+)\b",
            re.IGNORECASE,
        )
        self.exploration_keywords = re.compile(
            r"\b(what tables|show schema|list entities|list tables|what data exists|columns in)\b",
            re.IGNORECASE,
        )
        self.system_keywords = re.compile(
            r"\b(ingestion status|watermark|data sources|pipeline runs|audit log)\b",
            re.IGNORECASE,
        )

        # Workflow diagnostic keywords
        self.decline_keywords = re.compile(r"\b(why did|decline|drop|fall|decrease|diagnostic)\b", re.IGNORECASE)
        self.cohort_keywords = re.compile(r"\b(cohort|retention|repeat rate)\b", re.IGNORECASE)
        self.funnel_keywords = re.compile(
            r"\b(marketing funnel|funnel analysis|conversion funnel|lead conversion)\b", re.IGNORECASE
        )
        self.contrib_keywords = re.compile(r"\b(contributed|contribution|drove|drives)\b", re.IGNORECASE)
        self.abc_keywords = re.compile(r"\b(abc classification|pareto|product mix)\b", re.IGNORECASE)

    def route(self, question: str) -> RoutingDecision:
        """Route user question to appropriate pipeline or fast path."""
        q_clean = question.strip()

        # 1. Check mutation keywords or non-analytical actions
        if self.mutation_keywords.search(q_clean):
            return RoutingDecision(
                question=q_clean,
                category=QueryCategory.UNSUPPORTED,
                confidence=1.0,
                reasoning="Data modification, write operations, or autonomous actions are strictly prohibited.",
                suggested_action="PWA provides read-only enterprise analytical capabilities. Write/mutation actions are rejected.",
            )

        # 2. Check unsupported topics
        if self.unsupported_topics.search(q_clean):
            return RoutingDecision(
                question=q_clean,
                category=QueryCategory.UNSUPPORTED,
                confidence=1.0,
                reasoning="Out-of-scope domain question.",
                suggested_action="PWA analyzes enterprise operations (sales, procurement, inventory, customers, products, leads). Movies or external topics are unsupported.",
            )

        # 3. Check semantic lookup
        if self.semantic_keywords.search(q_clean):
            return RoutingDecision(
                question=q_clean,
                category=QueryCategory.SEMANTIC_LOOKUP,
                confidence=0.95,
                reasoning="Question asks for business definition or metric semantics.",
                suggested_action="Query Phase 2A business glossary or metrics catalog.",
            )

        # 4. Check data exploration
        if self.exploration_keywords.search(q_clean):
            return RoutingDecision(
                question=q_clean,
                category=QueryCategory.DATA_EXPLORATION,
                confidence=0.95,
                reasoning="Question requests table or schema metadata.",
                suggested_action="Query Phase 2A semantic entities and schema registry.",
            )

        # 5. Check system metadata
        if self.system_keywords.search(q_clean):
            return RoutingDecision(
                question=q_clean,
                category=QueryCategory.SYSTEM_METADATA,
                confidence=0.95,
                reasoning="Question requests operational pipeline metadata.",
                suggested_action="Query PWA control plane metadata (pwa_pipeline_runs, pwa_watermarks).",
            )

        # 6. Check ambiguity
        ambiguity_res = self.ambiguity_model.evaluate_term(q_clean)
        if ambiguity_res.is_ambiguous:
            return RoutingDecision(
                question=q_clean,
                category=QueryCategory.AMBIGUOUS,
                confidence=0.70,
                reasoning=f"Question contains ambiguous metric/term `{ambiguity_res.term}`.",
                suggested_action="Prompt user for explicit clarification.",
                ambiguity_options=ambiguity_res.possible_interpretations,
                clarification_message=ambiguity_res.clarification_message or "",
            )

        # 7. Workflow diagnostic hints
        wf_hint = None
        if self.decline_keywords.search(q_clean):
            wf_hint = "revenue_decline_analysis"
        elif self.cohort_keywords.search(q_clean):
            wf_hint = "customer_cohort_analysis"
        elif self.funnel_keywords.search(q_clean):
            wf_hint = "marketing_funnel_analysis"
        elif self.contrib_keywords.search(q_clean):
            wf_hint = "contribution_analysis"
        elif self.abc_keywords.search(q_clean):
            wf_hint = "product_mix_analysis"

        # Default to ANALYTICAL
        return RoutingDecision(
            question=q_clean,
            category=QueryCategory.ANALYTICAL,
            confidence=0.95,
            reasoning="Valid analytical question regarding enterprise data.",
            suggested_action="Proceed to Semantic Grounding and Governed SQL generation.",
            workflow_template_hint=wf_hint,
        )

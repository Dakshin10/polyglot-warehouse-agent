"""Stage 1: Agent 1 — Semantic Grounding Agent.

Translates user natural language questions into GroundedIntent referencing
the Phase 2A Enterprise Semantic Catalog.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import math
import re
from dataclasses import dataclass, field
import logging
from typing import Any

from pwa.semantic.ambiguity import AmbiguityModel
from pwa.semantic.loader import get_semantic_catalog
from pwa.semantic.models import SemanticCatalog
from pwa.semantic.query_planner import AnalyticalIntent, QueryPlanner

logger = logging.getLogger("pwa.agent.pipeline.schema_agent")

# Each rule: (trigger keywords, entities to add, dimensions to add, measures to add).
# "purchase"/"procurement" is handled separately below since its measure choice
# (count vs. amount) depends on whether "count" also appears in the question.
_DOMAIN_HEURISTICS: list[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = [
    (("marketplace order", "marketplace orders"), ("fact_marketplace_order",), (), ()),
    (("marketplace customer", "marketplace customers", "state", "city"), ("dim_marketplace_customer",), (), ()),
    (("marketplace seller", "marketplace sellers", "seller", "sellers"), ("dim_marketplace_seller",), (), ()),
    (("marketplace payment", "marketplace payments", "payment", "payments"), ("fact_marketplace_payment",), (), ()),
    (("marketplace review", "marketplace reviews", "review", "reviews"), ("fact_marketplace_review",), (), ()),
    (
        (
            "closed deal",
            "closed deals",
            "deal",
            "deals",
            "sales opportunities",
            "opportunities won",
            "deals won",
            "won deals",
        ),
        ("fact_closed_deal",),
        (),
        (),
    ),
    (("marketing lead", "marketing leads", "mql", "lead", "leads"), ("fact_marketing_lead",), (), ()),
    (
        ("revenue", "sales", "sales order total", "order total", "sales total", "freight"),
        ("fact_sales_order",),
        (),
        ("revenue",),
    ),
    (("quantity", "quantity of products", "units", "units sold"), ("fact_sales_order_item",), (), ("quantity_sold",)),
    (("sales order item", "sales order items", "line item", "line items"), ("fact_sales_order_item",), (), ()),
    (("category", "subcategory", "subcategories", "color", "product color"), ("dim_product",), ("product",), ()),
    (("supplier", "vendor", "suppliers", "vendors"), ("dim_supplier",), ("supplier",), ("purchase_amount",)),
    (("purchase", "procurement", "expenditure"), ("fact_purchase_order",), (), ("purchase_amount",)),
    (("inventory", "stock"), ("fact_inventory",), (), ("inventory_quantity",)),
    (("customer", "buyer", "customers"), ("dim_customer",), ("customer",), ()),
    (("product", "item", "products", "items"), ("dim_product",), ("product",), ()),
    (("employee", "headcount", "staff", "employees", "job title", "title"), ("dim_employee",), ("employee",), ()),
    (("department", "departments"), ("dim_employee",), ("employee",), ()),
]


@dataclass
class GroundedIntent:
    """Structured output returned by Agent 1 Semantic Grounding Agent."""

    question: str
    analytical_intent: AnalyticalIntent
    confidence: str  # HIGH | MEDIUM | LOW
    reasoning: str
    ambiguities: list[str] = field(default_factory=list)
    clarification_required: bool = False
    clarification_message: str = ""
    confidence_score: float = 1.0


_CATALOG_SEMANTIC_DESCRIPTIONS: dict[str, str] = {
    "fact_closed_deal": "closed deals marketing deals sales opportunities won deals won transactions closed sales declared monthly revenue opportunities won",
    "fact_marketing_lead": "marketing leads mql incoming inquiries prospective customers prospective clients sales leads inquiry leads",
    "fact_marketplace_order": "marketplace orders customer orders e-commerce purchases items delivered shipping freight delivered orders",
    "dim_marketplace_customer": "marketplace customer buyers customer state city customer location buyer state",
    "dim_marketplace_seller": "marketplace seller sellers merchant vendor store location seller state city seller performance",
    "fact_marketplace_payment": "marketplace payment payment type installments payment value payment methods payment amount",
    "fact_marketplace_review": "marketplace review review score rating customer feedback review comment review score",
    "fact_sales_order": "sales order enterprise sales order total revenue subtotal freight tax amount order year enterprise orders",
    "fact_sales_order_item": "sales order item line item quantity sold product quantity units sold order line items sold",
    "fact_purchase_order": "purchase order procurement expenditure supplier purchase vendor buying order purchase amount items bought from suppliers vendor procurement",
    "fact_inventory": "inventory stock levels warehouse availability items on hand inventory quantity stock count warehouse stock stock level availability",
    "dim_customer": "customer master record enterprise buyer client customer name customer list",
    "dim_product": "product catalog product category subcategory list price standard cost color product number item catalog",
    "dim_supplier": "supplier vendor credit rating active supplier vendor name vendor list",
    "dim_employee": "employee headcount staff job title department human resources hire date gender staff headcount",
}

# ---------------------------------------------------------------------------
# Entity description embedding cache
# ---------------------------------------------------------------------------
# Entity descriptions in _CATALOG_SEMANTIC_DESCRIPTIONS are STATIC between
# catalog edits. Re-calling get_dense_embedding(desc) on every query that
# reaches the dense path is wasteful — it multiplies the embedding API cost
# by the number of catalog entities (~15) for every hard query.
#
# Cache keys are "entity_name:sha256(desc)[:16]" so that any edit to a
# description automatically invalidates that entry without stale data risk.
# The cache is module-level (process lifetime) — entity descriptions do not
# change at runtime.
_ENTITY_DESC_EMBEDDING_CACHE: dict[str, list[float]] = {}


def _get_cached_entity_embedding(entity_name: str, desc: str) -> list[float] | None:
    """Return the embedding for an entity description, computing it once and caching.

    The cache key includes a SHA-256 prefix of the description text so that
    any catalog edit automatically invalidates the cached entry.
    """
    from pwa.agent.models import get_dense_embedding

    desc_hash = hashlib.sha256(desc.encode()).hexdigest()[:16]
    cache_key = f"{id(get_dense_embedding)}:{entity_name}:{desc_hash}"

    if cache_key in _ENTITY_DESC_EMBEDDING_CACHE:
        return _ENTITY_DESC_EMBEDDING_CACHE[cache_key]

    vec = get_dense_embedding(desc)
    if vec is not None:
        _ENTITY_DESC_EMBEDDING_CACHE[cache_key] = vec
    return vec


def _vectorize_text(text: str) -> dict[str, float]:
    """Build word + 3-gram character frequency vector for semantic matching."""
    s = text.lower().strip()
    words = re.findall(r"\b\w+\b", s)
    c: dict[str, float] = defaultdict(float)
    for w in words:
        c[w] += 1.0
    for i in range(len(words) - 1):
        c[f"{words[i]}_{words[i + 1]}"] += 1.5
    for i in range(len(s) - 2):
        c[s[i : i + 3]] += 0.3
    return c


def _cosine_similarity(v1: dict[str, float], v2: dict[str, float]) -> float:
    if not v1 or not v2:
        return 0.0
    dot = sum(v1[k] * v2[k] for k in v1 if k in v2)
    norm1 = math.sqrt(sum(val * val for val in v1.values()))
    norm2 = math.sqrt(sum(val * val for val in v2.values()))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class GroundingAgent:
    """Agent 1 grounding engine using Phase 2A semantic catalog."""

    def __init__(self, catalog: SemanticCatalog | None = None) -> None:
        self.catalog = catalog or get_semantic_catalog()
        self.planner = QueryPlanner(self.catalog)
        self.ambiguity_model = AmbiguityModel()

    def ground_question(self, question: str) -> GroundedIntent:
        """Ground user question into structured GroundedIntent."""
        q_lower = question.lower().strip()

        ambiguity_res = self.ambiguity_model.evaluate_term(question)
        if ambiguity_res.is_ambiguous:
            return GroundedIntent(
                question=question,
                analytical_intent=AnalyticalIntent(confidence_score=0.2),
                confidence="LOW",
                reasoning=f"Question contains ambiguous term `{ambiguity_res.term}`.",
                ambiguities=ambiguity_res.possible_interpretations,
                clarification_required=True,
                clarification_message=ambiguity_res.clarification_message or "",
                confidence_score=0.2,
            )

        matched_entities, matched_dimensions, matched_measures, matched_metrics = self._match_catalog_terms(q_lower)
        self._apply_domain_heuristics(q_lower, matched_entities, matched_dimensions, matched_measures)

        # Handle short conversational confirmation/selection responses (e.g., "yes", "option 1", "revenue")
        if not matched_entities and q_lower in ("yes", "yep", "sure", "ok", "option 1", "revenue", "1"):
            matched_entities = ["fact_sales_order"]
            matched_measures = ["revenue"]

        confidence_score = 0.95 if matched_entities else 0.0

        # If heuristic match missed, perform embedding vector similarity matching (dense API embedding if available, lexical TF-IDF fallback)
        if not matched_entities:
            from pwa.agent.models import get_dense_embedding

            dense_q = get_dense_embedding(q_lower)
            candidate_scores: list[tuple[str, float]] = []

            if dense_q is not None:
                # Dense embedding similarity path.
                # Entity description embeddings are computed once and cached;
                # only the question itself pays an API call per query.
                for e_name, desc in _CATALOG_SEMANTIC_DESCRIPTIONS.items():
                    dense_desc = _get_cached_entity_embedding(e_name, desc)
                    if dense_desc is not None:
                        dot = sum(a * b for a, b in zip(dense_q, dense_desc))
                        norm_q = math.sqrt(sum(a * a for a in dense_q))
                        norm_d = math.sqrt(sum(b * b for b in dense_desc))
                        sim = (dot / (norm_q * norm_d)) if (norm_q > 0 and norm_d > 0) else 0.0
                        if sim > 0.30:
                            candidate_scores.append((e_name, sim))

            if not candidate_scores:
                # Lexical TF-IDF / n-gram vector similarity fallback
                q_vec = _vectorize_text(q_lower)
                for e_name, desc in _CATALOG_SEMANTIC_DESCRIPTIONS.items():
                    sim = _cosine_similarity(q_vec, _vectorize_text(desc))
                    if sim > 0.15:
                        candidate_scores.append((e_name, sim))

            candidate_scores.sort(key=lambda x: x[1], reverse=True)

            cand_ambiguity = self.ambiguity_model.evaluate_candidates(candidate_scores)
            if cand_ambiguity.is_ambiguous:
                return GroundedIntent(
                    question=question,
                    analytical_intent=AnalyticalIntent(
                        confidence_score=candidate_scores[0][1] if candidate_scores else 0.0
                    ),
                    confidence="LOW",
                    reasoning=f"Ambiguity/low-confidence in similarity matching: {cand_ambiguity.clarification_message}",
                    ambiguities=cand_ambiguity.possible_interpretations,
                    clarification_required=True,
                    clarification_message=cand_ambiguity.clarification_message or "",
                    confidence_score=candidate_scores[0][1] if candidate_scores else 0.0,
                )

            if candidate_scores:
                top_entity, top_score = candidate_scores[0]
                matched_entities = [top_entity]
                confidence_score = round(top_score, 4)

        # Default measure/dimension fallbacks for bare entity queries
        if matched_entities and not matched_dimensions and not matched_measures and not matched_metrics:
            for p_entity in matched_entities:
                if "dim_" in p_entity:
                    clean_dim = p_entity.replace("dim_", "").replace("marketplace_", "")
                    if self.catalog.get_dimension(clean_dim):
                        if clean_dim not in matched_dimensions:
                            matched_dimensions.append(clean_dim)
                    else:
                        fallback_dim = "product" if "product" in p_entity else "customer"
                        if fallback_dim not in matched_dimensions:
                            matched_dimensions.append(fallback_dim)
                else:
                    if "purchase" in p_entity:
                        if "purchase_amount" not in matched_measures:
                            matched_measures.append("purchase_amount")
                    elif "inventory" in p_entity:
                        if "inventory_quantity" not in matched_measures:
                            matched_measures.append("inventory_quantity")
                    elif "sales" in p_entity or "order" in p_entity or "item" in p_entity:
                        if "revenue" not in matched_measures:
                            matched_measures.append("revenue")

        if not matched_entities:
            # Nothing in the catalog matched — do not silently guess sales data.
            # Ask the user to clarify rather than answering a different question.
            return GroundedIntent(
                question=question,
                analytical_intent=AnalyticalIntent(confidence_score=0.0),
                confidence="LOW",
                reasoning="No known entities, dimensions, or measures were recognized in the question.",
                ambiguities=[],
                clarification_required=True,
                clarification_message=(
                    "I could not map this question to any known enterprise data entity "
                    "(sales, products, customers, suppliers, employees, inventory, leads). "
                    "Could you rephrase it in terms of one of these areas?"
                ),
                confidence_score=0.0,
            )

        limit = self._parse_limit(q_lower)
        time_dim, granularity = self._parse_time_granularity(q_lower)

        intent = AnalyticalIntent(
            entities=matched_entities,
            dimensions=matched_dimensions,
            measures=matched_measures,
            metrics=matched_metrics,
            time_dimension=time_dim,
            granularity=granularity,
            limit=limit if limit is not None else 100,
            confidence_score=confidence_score,
        )

        confidence = (
            "HIGH"
            if (confidence_score >= 0.75 and matched_entities and (matched_measures or matched_metrics))
            else "MEDIUM"
        )
        if confidence_score < 0.5:
            confidence = "LOW"

        return GroundedIntent(
            question=question,
            analytical_intent=intent,
            confidence=confidence,
            reasoning=f"Grounded intent to entities={matched_entities}, dimensions={matched_dimensions}, measures={matched_measures}, metrics={matched_metrics}.",
            confidence_score=confidence_score,
        )

    def _match_catalog_terms(self, q_lower: str) -> tuple[list[str], list[str], list[str], list[str]]:
        """Match the question against every catalog entity/metric/measure/dimension name."""
        matched_entities: list[str] = []
        for name, entity in self.catalog.entities.items():
            clean_name = name.lower().replace("dim_", "").replace("fact_", "").replace("_", " ")
            singular_clean = clean_name.rstrip("s")
            if (
                name.lower() in q_lower
                or entity.entity_name.lower() in q_lower
                or clean_name in q_lower
                or (len(singular_clean) > 3 and singular_clean in q_lower)
            ):
                matched_entities.append(name)

        matched_metrics = [
            name
            for name, metric in self.catalog.metrics.items()
            if name.lower() in q_lower or metric.name.lower() in q_lower
        ]
        matched_measures = [
            name
            for name, measure in self.catalog.measures.items()
            if name.lower() in q_lower or measure.name.lower() in q_lower
        ]
        matched_dimensions = [
            name
            for name, dim in self.catalog.dimensions.items()
            if name.lower() in q_lower or dim.name.lower() in q_lower
        ]
        return matched_entities, matched_dimensions, matched_measures, matched_metrics

    @staticmethod
    def _apply_domain_heuristics(
        q_lower: str,
        matched_entities: list[str],
        matched_dimensions: list[str],
        matched_measures: list[str],
    ) -> None:
        """Fill in entities/dimensions/measures the catalog name-match misses,
        keyed on domain vocabulary (e.g. "sales" implies fact_sales_order)."""
        for keywords, entities, dimensions, measures in _DOMAIN_HEURISTICS:
            if not any(kw in q_lower for kw in keywords):
                continue
            for e in entities:
                if e not in matched_entities:
                    matched_entities.append(e)
            for d in dimensions:
                if d not in matched_dimensions:
                    matched_dimensions.append(d)
            for m in measures:
                if m not in matched_measures:
                    matched_measures.append(m)

        # Special-cased: the measure depends on whether "count" also appears.
        if any(kw in q_lower for kw in ("purchase", "procurement", "paid", "spent", "money")) and any(
            kw in q_lower for kw in ("vendor", "supplier", "vendors", "suppliers")
        ):
            if "fact_purchase_order" not in matched_entities:
                matched_entities.append("fact_purchase_order")
            if "dim_supplier" in matched_entities:
                matched_entities.remove("dim_supplier")
            if "purchase_amount" not in matched_measures and "purchase_order_count" not in matched_measures:
                matched_measures.append("purchase_amount")
        elif "purchase" in q_lower or "procurement" in q_lower:
            if "fact_purchase_order" not in matched_entities:
                matched_entities.append("fact_purchase_order")
            if "purchase_amount" not in matched_measures and "purchase_order_count" not in matched_measures:
                if "count" in q_lower:
                    matched_measures.append("purchase_order_count")
                else:
                    matched_measures.append("purchase_amount")

        # Prevent cross-domain conflict: if marketplace/closed deal entities are present,
        # remove enterprise fact_sales_order injected by generic keywords like 'revenue'.
        has_marketplace_entity = any(
            e in matched_entities
            for e in (
                "fact_closed_deal",
                "dim_marketplace_seller",
                "dim_marketplace_customer",
                "fact_marketplace_order",
                "fact_marketing_lead",
            )
        )
        if has_marketplace_entity and "fact_sales_order" in matched_entities:
            matched_entities.remove("fact_sales_order")
            if "declared" in q_lower or "monthly" in q_lower:
                if "declared_monthly_revenue" not in matched_measures:
                    matched_measures.append("declared_monthly_revenue")
                if "revenue" in matched_measures:
                    matched_measures.remove("revenue")

    @staticmethod
    def _parse_limit(q_lower: str) -> int | None:
        if "top" not in q_lower:
            return None
        m = re.search(r"top\s*(\d+)", q_lower)
        return int(m.group(1)) if m else None

    @staticmethod
    def _parse_time_granularity(q_lower: str) -> tuple[str | None, str | None]:
        if "monthly revenue" in q_lower or "declared monthly revenue" in q_lower:
            return None, None
        if "by month" in q_lower or "per month" in q_lower or "monthly trend" in q_lower:
            return "order_date", "month"
        if "by year" in q_lower or "per year" in q_lower or "annual revenue" in q_lower or "grouped by year" in q_lower:
            return "order_date", "year"
        return None, None


def ground_schema(question: str, model: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Legacy interface adapter returning dict representation of grounded schema context."""
    agent = GroundingAgent()
    grounded = agent.ground_question(question)
    return {
        "grounded_intent": grounded.analytical_intent.__dict__,
        "confidence": grounded.confidence,
        "reasoning": grounded.reasoning,
        "clarification_required": grounded.clarification_required,
        "clarification_message": grounded.clarification_message,
        "ambiguities": grounded.ambiguities,
    }

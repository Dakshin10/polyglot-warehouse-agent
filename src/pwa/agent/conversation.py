"""Multi-Turn Conversation Context Manager — Nexora Enterprise Platform."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from pwa.semantic.query_planner import AnalyticalIntent

logger = logging.getLogger("pwa.agent.conversation")


@dataclass
class ConversationTurn:
    """Represents a single conversational turn."""

    turn_id: int
    question: str
    analytical_intent: Optional[AnalyticalIntent] = None
    sql: str = ""
    status: str = "SUCCESS"


class ConversationContext:
    """Manages multi-turn conversation state for follow-up analytical queries."""

    def __init__(self, session_id: str = "default_session") -> None:
        self.session_id = session_id
        self.turns: list[ConversationTurn] = []

    def add_turn(self, question: str, intent: Optional[AnalyticalIntent] = None, sql: str = "") -> None:
        """Add a turn to conversation memory."""
        turn_id = len(self.turns) + 1
        self.turns.append(ConversationTurn(turn_id=turn_id, question=question, analytical_intent=intent, sql=sql))

    def resolve_followup(self, question: str, current_intent: AnalyticalIntent) -> AnalyticalIntent:
        """Merge context from previous turns for follow-up queries.

        Example:
            Turn 1: "Show revenue by category"
            Turn 2: "Only for 2025" -> Merges year=2025 filter into Turn 1's revenue & category intent.
        """
        if not self.turns:
            return current_intent

        last_turn = self.turns[-1]
        if not last_turn.analytical_intent:
            return current_intent

        # Only treat this as a follow-up refinement of the previous turn (and merge
        # context into it) when the two turns actually share an entity, or the new
        # question named no entity of its own (e.g. "only for 2025"). Otherwise this
        # is a new topic and merging would silently drag the old topic's entities,
        # dimensions and measures into an unrelated query.
        prev_entities = set(last_turn.analytical_intent.entities or [])
        curr_entities = set(current_intent.entities or [])
        is_followup = (not curr_entities) or bool(curr_entities & prev_entities)
        if not is_followup:
            return current_intent

        # Union merge entities, dimensions, measures, metrics
        merged_entities = list(
            dict.fromkeys((current_intent.entities or []) + (last_turn.analytical_intent.entities or []))
        )
        merged_dimensions = list(
            dict.fromkeys((current_intent.dimensions or []) + (last_turn.analytical_intent.dimensions or []))
        )
        merged_measures = list(
            dict.fromkeys((current_intent.measures or []) + (last_turn.analytical_intent.measures or []))
        )
        merged_metrics = list(
            dict.fromkeys((current_intent.metrics or []) + (last_turn.analytical_intent.metrics or []))
        )

        # Preserve new filters/granularity
        time_dim = current_intent.time_dimension or last_turn.analytical_intent.time_dimension
        granularity = current_intent.granularity or last_turn.analytical_intent.granularity

        return AnalyticalIntent(
            entities=merged_entities,
            dimensions=merged_dimensions,
            measures=merged_measures,
            metrics=merged_metrics,
            filters=current_intent.filters or last_turn.analytical_intent.filters,
            time_dimension=time_dim,
            granularity=granularity,
            group_by=current_intent.group_by or last_turn.analytical_intent.group_by,
            order_by=current_intent.order_by or last_turn.analytical_intent.order_by,
            limit=current_intent.limit or last_turn.analytical_intent.limit,
        )

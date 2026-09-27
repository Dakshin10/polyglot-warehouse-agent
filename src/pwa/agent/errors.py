"""Structured error taxonomy for PWA Phase 2B Multi-Agent System."""

from __future__ import annotations


class PwaAgentError(Exception):
    """Base exception for all PWA agent errors."""

    def __init__(self, message: str, code: str = "AGENT_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# Alias for compatibility
PWAError = PwaAgentError


class AmbiguousQueryError(PwaAgentError):
    """Raised when a user query contains ambiguous business terms requiring clarification."""

    def __init__(self, message: str, possible_interpretations: list[str] | None = None) -> None:
        super().__init__(message, code="AMBIGUOUS_QUERY")
        self.possible_interpretations = possible_interpretations or []


class SemanticNotFoundError(PwaAgentError):
    """Raised when referenced entity, dimension, measure, or metric is missing in catalog."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="SEMANTIC_NOT_FOUND")


class SemanticGrainValidationError(PwaAgentError):
    """Raised when a query attempts an unsafe cross-grain join causing row multiplication (fan-out)."""

    def __init__(self, message: str, fanout_details: list[dict[str, str]] | None = None) -> None:
        super().__init__(message, code="SEMANTIC_GRAIN_VALIDATION_FAILED")
        self.fanout_details = fanout_details or []


class InvalidRelationshipError(PwaAgentError):
    """Raised when an un-governed relationship/join path is attempted."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="INVALID_RELATIONSHIP")


class InvalidMetricError(PwaAgentError):
    """Raised when a metric calculation formula or definition is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="INVALID_METRIC")


class SqlValidationError(PwaAgentError):
    """Raised when generated SQL fails AST read-only safety, syntax, or table authorization."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="SQL_VALIDATION_FAILED")


class QueryCostLimitExceededError(PwaAgentError):
    """Raised when BigQuery dry-run estimated scan bytes exceed configured cost limit."""

    def __init__(self, message: str, estimated_bytes: int = 0, limit_bytes: int = 0) -> None:
        super().__init__(message, code="QUERY_COST_LIMIT_EXCEEDED")
        self.estimated_bytes = estimated_bytes
        self.limit_bytes = limit_bytes


class QualityBlockedError(PwaAgentError):
    """Raised when a target table fails critical Phase 1 quality gates."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="QUALITY_BLOCKED")


class StaleDataWarning(PwaAgentError):
    """Warning indicator when dataset freshness SLA is breached."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="STALE_DATA_WARNING")


class WarehouseExecutionError(PwaAgentError):
    """Raised when BigQuery warehouse query execution fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="WAREHOUSE_EXECUTION_FAILED")


class AgentTimeoutError(PwaAgentError):
    """Raised when agent processing times out."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="AGENT_TIMEOUT")


class AgentStepLimitError(PwaAgentError):
    """Raised when multi-agent step iterations exceed max_agent_steps threshold."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="AGENT_STEP_LIMIT")


class UnsupportedRequestError(PwaAgentError):
    """Raised when a user question is out of scope or requests unsupported actions (e.g. DML)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="UNSUPPORTED_REQUEST")

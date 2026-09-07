"""Fallback wrapper for single-agent steps in the pipeline."""

import logging
from typing import Any, Callable, TypeVar

from pwa.agent.models import get_agent_model, get_model_for_stage

logger = logging.getLogger("pwa.agent.pipeline.fallback")

T = TypeVar("T")


def run_step_with_fallback(
    step_name: str,
    step_fn: Callable[..., T],
    *args: Any,
    primary_model: Any = None,
    fallback_model: Any = None,
    **kwargs: Any,
) -> tuple[T, Any]:
    """Execute a single agent step with primary model and automatic single-attempt fallback.

    Args:
        step_name: Name of the pipeline stage (e.g., "schema", "sql", "answer").
        step_fn: Function to execute (e.g., ground_schema, generate_sql, synthesize_answer).
        *args: Positional args to pass to step_fn.
        primary_model: Model spec or instance for primary attempt.
        fallback_model: Model spec or instance for fallback attempt if primary fails.
        **kwargs: Keyword args to pass to step_fn.

    Returns:
        Tuple of (step_result, actual_model_used).
    """
    if primary_model is None:
        primary_model = get_model_for_stage(step_name)
    else:
        primary_model = get_agent_model(primary_model)

    if fallback_model is None:
        primary_str = str(getattr(primary_model, "model", primary_model)).lower()
        if "groq" in primary_str:
            fallback_model = get_agent_model("gemini")
        else:
            fallback_model = get_agent_model("groq")
    else:
        fallback_model = get_agent_model(fallback_model)

    # Primary Attempt
    try:
        logger.debug(f"[{step_name}] Attempting execution with primary model: '{primary_model}'")
        res = step_fn(*args, model=primary_model, **kwargs)
        logger.info(f"[{step_name}] Step answered successfully by primary model: '{primary_model}'")
        return res, primary_model
    except Exception as err:
        logger.warning(
            f"[{step_name}] Primary model '{primary_model}' failed with error: {err}. "
            f"Retrying single step once with fallback model: '{fallback_model}'..."
        )

    # Fallback Attempt
    try:
        res = step_fn(*args, model=fallback_model, **kwargs)
        logger.info(f"[{step_name}] Step answered successfully by FALLBACK model: '{fallback_model}'")
        return res, fallback_model
    except Exception as fallback_err:
        logger.error(
            f"[{step_name}] Fallback model '{fallback_model}' also failed with error: {fallback_err}. "
            "Pipeline step failed."
        )
        raise fallback_err

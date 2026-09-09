"""Model registry for PWA agents defining Gemini and Groq (via LiteLLM) backends."""

import logging
import os
from typing import Any, Union

logger = logging.getLogger("pwa.agent.models")

GEMINI_MODEL_ID = "gemini-2.5-flash"
GROQ_MODEL_ID = "groq/llama-3.3-70b-versatile"

# Global lazy registries for model instances
_GROQ_MODEL_INSTANCES: dict[str, Any] = {}
_GEMINI_MODEL_INSTANCES: dict[str, Any] = {}


def get_groq_model(model_name: str = GROQ_MODEL_ID) -> Any:
    """Get or create LiteLlm instance for Groq."""
    global _GROQ_MODEL_INSTANCES
    if model_name not in _GROQ_MODEL_INSTANCES:
        logger.debug(f"Initializing LiteLlm model instance for Groq: model='{model_name}'")
        from google.adk.models.lite_llm import LiteLlm

        _GROQ_MODEL_INSTANCES[model_name] = LiteLlm(model=model_name)
    return _GROQ_MODEL_INSTANCES[model_name]


def get_gemini_model(model_name: str = GEMINI_MODEL_ID) -> Any:
    """Get or create Gemini model instance singleton."""
    global _GEMINI_MODEL_INSTANCES
    if model_name not in _GEMINI_MODEL_INSTANCES:
        logger.debug(f"Initializing Gemini model instance singleton: model='{model_name}'")
        from google.adk.models.google_llm import Gemini

        _GEMINI_MODEL_INSTANCES[model_name] = Gemini(model=model_name)
    return _GEMINI_MODEL_INSTANCES[model_name]


def get_agent_model(model_spec: Union[str, Any] = "gemini") -> Any:
    """Resolve a model name string or model object into an ADK-compatible model instance.

    Args:
        model_spec: Model key ("gemini", "groq"), model string ID, or LiteLlm/Gemini model instance.

    Returns:
        Gemini model instance for Gemini, or LiteLlm instance for Groq / custom models.
    """
    if isinstance(model_spec, str):
        spec_lower = model_spec.lower().strip()
        if spec_lower == "gemini":
            return get_gemini_model(GEMINI_MODEL_ID)
        elif spec_lower == "groq":
            return get_groq_model(GROQ_MODEL_ID)
        elif spec_lower.startswith("groq/"):
            return get_groq_model(model_spec)
        elif spec_lower.startswith("gemini") or "gemini" in spec_lower:
            return get_gemini_model(model_spec)
        else:
            return get_gemini_model(model_spec)

    return model_spec


def get_model_for_stage(stage: str) -> Any:
    """Get the configured ADK model for a specific pipeline stage.

    Default Policy:
      - "schema": "groq" (fast)
      - "sql": "gemini" (reasoning)
      - "answer": "groq" (fast)

    Overridable via environment variables:
      - Global override: PWA_AGENT_MODEL
      - Stage overrides: PWA_AGENT_SCHEMA_MODEL, PWA_AGENT_SQL_MODEL, PWA_AGENT_ANSWER_MODEL
    """
    global_model = os.getenv("PWA_AGENT_MODEL", "").strip()
    stage_key = f"PWA_AGENT_{stage.upper()}_MODEL"
    stage_override = os.getenv(stage_key, "").strip()

    if stage_override:
        model_spec = stage_override
    elif global_model:
        model_spec = global_model
    else:
        defaults = {
            "schema": "groq",
            "sql": "gemini",
            "answer": "groq",
        }
        model_spec = defaults.get(stage.lower(), "gemini")

    return get_agent_model(model_spec)

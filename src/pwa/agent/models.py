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

# Embedding availability state — module-level so once-per-process warnings work across callers.
# _NO_KEY_WARNED: flip to True after the first missing-key WARNING to suppress repeats.
# _EMBEDDING_STATUS: last observed status; surfaced by get_embedding_status().
_NO_KEY_WARNED: bool = False
_EMBEDDING_STATUS: str = "unknown"  # "unknown" | "no_key" | "available" | "api_error"


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


def get_embedding_status() -> str:
    """Return the last observed embedding API status.

    Values:
        "unknown"   — get_dense_embedding has not been called yet.
        "no_key"    — GEMINI_API_KEY / GOOGLE_API_KEY / GROQ_API_KEY all unset.
        "available" — last call returned a valid vector.
        "api_error" — key is configured but both LiteLLM and google.genai backends failed.

    Suitable for surfacing in a startup health-check or /status endpoint.
    """
    return _EMBEDDING_STATUS


def get_dense_embedding(text: str) -> list[float] | None:
    """Generate dense text embedding using litellm or google-genai (text-embedding-004).

    Fallback behaviour:
    - No API key configured  → returns None immediately; logs a WARNING once per process.
    - Key configured but both backends fail → returns None; logs a WARNING per call
      (this is a real operational error, not a configuration choice).
    - Caller should treat None as a signal to fall back to lexical TF-IDF matching.
    """
    global _NO_KEY_WARNED, _EMBEDDING_STATUS

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GROQ_API_KEY")
    if not api_key:
        if not _NO_KEY_WARNED:
            logger.warning(
                "No embedding API key configured "
                "(GEMINI_API_KEY / GOOGLE_API_KEY / GROQ_API_KEY are all unset). "
                "Dense semantic grounding is disabled — falling back to lexical TF-IDF. "
                "Zero-overlap paraphrases may not resolve correctly. "
                "Set GEMINI_API_KEY to enable full semantic matching."
            )
            _NO_KEY_WARNED = True
        _EMBEDDING_STATUS = "no_key"
        return None

    litellm_exc: Exception | None = None
    genai_exc: Exception | None = None

    try:
        import litellm

        response = litellm.embedding(model="text-embedding-004", input=[text])
        if response and getattr(response, "data", None):
            _EMBEDDING_STATUS = "available"
            return response.data[0]["embedding"]
    except Exception as exc:
        litellm_exc = exc
        logger.debug(f"LiteLLM embedding call failed ({exc}), trying google.genai fallback")

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        res = client.models.embed_content(model="text-embedding-004", contents=text)
        if res and getattr(res, "embeddings", None):
            _EMBEDDING_STATUS = "available"
            return list(res.embeddings[0].values)
    except Exception as exc:
        genai_exc = exc
        logger.debug(f"Google GenAI embedding call failed ({exc})")

    # Both backends exhausted without a usable result — this is "configured but broken".
    _EMBEDDING_STATUS = "api_error"
    logger.warning(
        "Embedding API key is configured but all backends failed for this call — "
        "falling back to TF-IDF lexical matching. "
        f"LiteLLM: {litellm_exc or 'empty response'}; "
        f"google.genai: {genai_exc or 'empty response'}."
    )
    return None

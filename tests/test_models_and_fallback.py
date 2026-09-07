"""Mocked unit tests for model selection, stage defaults policy, and fallback wrapper."""

from unittest.mock import patch

from google.adk.models.lite_llm import LiteLlm

from pwa.agent.models import GEMINI_MODEL_ID, GROQ_MODEL_ID, get_agent_model, get_model_for_stage
from pwa.agent.pipeline.fallback import run_step_with_fallback


def test_model_selection_resolution():
    """Verify get_agent_model resolves gemini and groq keywords correctly."""
    # Gemini
    gemini_res = get_agent_model("gemini")
    assert getattr(gemini_res, "model", gemini_res) == GEMINI_MODEL_ID

    # Groq default
    groq_res = get_agent_model("groq")
    assert isinstance(groq_res, LiteLlm)
    assert groq_res.model == GROQ_MODEL_ID

    # Custom Groq model string
    custom_groq = get_agent_model("groq/mixtral-8x7b-32768")
    assert isinstance(custom_groq, LiteLlm)
    assert custom_groq.model == "groq/mixtral-8x7b-32768"


def test_stage_model_selection_policy_and_env():
    """Verify default policy (Groq for schema/answer, Gemini for SQL) and env var overrides."""
    with patch.dict("os.environ", {}, clear=True):
        schema_m = get_model_for_stage("schema")
        sql_m = get_model_for_stage("sql")
        answer_m = get_model_for_stage("answer")

        # Schema & Answer default to Groq for speed
        assert isinstance(schema_m, LiteLlm)
        assert schema_m.model == GROQ_MODEL_ID

        assert isinstance(answer_m, LiteLlm)
        assert answer_m.model == GROQ_MODEL_ID

        # SQL defaults to Gemini for reasoning
        assert getattr(sql_m, "model", sql_m) == GEMINI_MODEL_ID

    # Global override via PWA_AGENT_MODEL=groq
    with patch.dict("os.environ", {"PWA_AGENT_MODEL": "groq"}, clear=True):
        sql_m_global = get_model_for_stage("sql")
        assert isinstance(sql_m_global, LiteLlm)
        assert sql_m_global.model == GROQ_MODEL_ID

    # Stage-specific override via PWA_AGENT_SQL_MODEL=gemini
    with patch.dict("os.environ", {"PWA_AGENT_MODEL": "groq", "PWA_AGENT_SQL_MODEL": "gemini"}, clear=True):
        sql_m_specific = get_model_for_stage("sql")
        assert getattr(sql_m_specific, "model", sql_m_specific) == GEMINI_MODEL_ID


def test_fallback_wrapper_primary_success():
    """Verify run_step_with_fallback returns primary result when primary model succeeds."""

    def mock_step_fn(arg, model=None):
        model_str = str(getattr(model, "model", model))
        return f"success with {model_str}"

    res, used_model = run_step_with_fallback("sql", mock_step_fn, "test_input", primary_model="gemini")
    assert res == "success with gemini-2.5-flash"
    assert getattr(used_model, "model", used_model) == GEMINI_MODEL_ID


def test_fallback_wrapper_triggers_on_gemini_failure():
    """Simulate primary Gemini failure (e.g. rate limit error) and verify automatic fallback to Groq."""

    def mock_step_fn_failing_gemini(arg, model=None):
        model_str = str(getattr(model, "model", model))
        if "gemini" in model_str.lower():
            raise RuntimeError("429 Resource Exhausted / Rate Limit Error on Gemini API")
        return f"success with {model_str}"

    res, used_model = run_step_with_fallback(
        "sql",
        mock_step_fn_failing_gemini,
        "test_input",
        primary_model="gemini",
        fallback_model="groq",
    )

    # Output should reflect fallback execution with Groq
    assert "groq/llama-3.3-70b-versatile" in res
    assert isinstance(used_model, LiteLlm)
    assert used_model.model == GROQ_MODEL_ID

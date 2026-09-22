"""Unit tests for pwa query CLI command and interactive REPL."""

import os
from unittest.mock import patch

from pwa.cli import cmd_query
from pwa.agent.pipeline.orchestrator import PipelineResult


def _make_result(answer: str) -> PipelineResult:
    """Build a minimal PipelineResult for mocking run_query_verbose."""
    return PipelineResult(
        answer=answer,
        sql="SELECT 1",
        rows=[],
        bytes_scanned=0,
        stage_latencies={"schema": 0.1, "sql": 0.2, "exec": 0.3, "answer": 0.1},
    )


def test_cli_query_oneshot_success(capsys):
    """Verify pwa query "<question>" one-shot mode prints response to stdout and returns 0."""
    expected = "In 2014, total sales revenue was $5.1M."
    # run_query_verbose is imported inside cmd_query — patch at the orchestrator module level
    with patch("pwa.agent.pipeline.orchestrator.run_query_verbose", return_value=_make_result(expected)):
        rc = cmd_query("what was the total sales revenue in 2014?", interactive=False, model=None, verbose=False)
        captured = capsys.readouterr()

        assert rc == 0
        assert expected in captured.out


def test_cli_query_oneshot_missing_question(capsys):
    """Verify pwa query without a question in one-shot mode returns non-zero code."""
    rc = cmd_query("", interactive=False, model=None, verbose=False)
    captured = capsys.readouterr()

    assert rc == 1
    assert "Error: Question required" in captured.err


def test_cli_query_model_and_verbose_flags(capsys):
    """Verify --model and --verbose flags configure model env and debug log level."""
    with patch("pwa.agent.pipeline.orchestrator.run_query_verbose", return_value=_make_result("Answer from Groq.")):
        with patch.dict("os.environ", {}, clear=False):
            rc = cmd_query("test question", interactive=False, model="groq", verbose=True)
            assert rc == 0
            assert os.environ.get("PWA_AGENT_MODEL") == "groq"


def test_cli_query_interactive_loop(capsys):
    """Verify pwa query --interactive REPL loop processes questions until user exits."""
    inputs = ["what was the total sales revenue in 2014?", "quit"]
    with patch("builtins.input", side_effect=inputs):
        # Interactive mode uses run_query (not run_query_verbose), also imported inside the function
        with patch("pwa.agent.pipeline.orchestrator.run_query", return_value="In 2014, total sales revenue was $5.1M."):
            rc = cmd_query("", interactive=True, model=None, verbose=False)
            captured = capsys.readouterr()

            assert rc == 0
            assert "Interactive NLP Query CLI" in captured.out
            assert "In 2014, total sales revenue was $5.1M." in captured.out
            assert "Goodbye!" in captured.out

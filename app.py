"""Polyglot Warehouse Agent (PWA) — Monochrome Conversational Chat Interface.

Run locally:
    streamlit run app.py
"""

import os
import pathlib
import sys
import time

# Ensure src/ directory is in Python path for pwa imports
_ROOT_DIR = pathlib.Path(__file__).parent.resolve()
_SRC_DIR = _ROOT_DIR / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import streamlit as st  # noqa: E402
from pwa.ui.components.answer_panel import render_answer_panel  # noqa: E402
from pwa.ui.components.evidence_panel import render_evidence_panel  # noqa: E402
from pwa.ui.components.header import render_header  # noqa: E402
from pwa.ui.components.rejection_panel import render_rejection_panel  # noqa: E402
from pwa.ui.components.stage_tracker import (  # noqa: E402
    render_pipeline_trace_expander,
    render_thinking_status,
)
from pwa.ui.components.report_view import render_report_view  # noqa: E402
from pwa.ui.styles import apply_custom_styles  # noqa: E402

# Try importing real orchestrator
try:
    from pwa.agent.pipeline.orchestrator import PipelineResult, run_query_verbose
    _REAL_ORCHESTRATOR_AVAILABLE = True
except Exception as _import_exc:
    _REAL_ORCHESTRATOR_AVAILABLE = False
    _IMPORT_ERROR = str(_import_exc)


def _stub_run_query_verbose(question: str, stage_callback=None) -> PipelineResult:
    """Stub orchestrator used for testing or when live backend is unavailable."""
    stages = [
        ("grounding", {"schema": "mart.v_movie, mart.v_revenue_by_year"}),
        ("sql", {"sql": "SELECT title, revenue FROM mart.v_movie ORDER BY revenue DESC LIMIT 3;"}),
        ("validate", {"status": "SUCCESS"}),
        ("synthesize", {}),
    ]

    for stage_name, extra in stages:
        if stage_callback:
            stage_callback(stage_name, "started", extra)
        time.sleep(0.3)
        if stage_callback:
            stage_callback(stage_name, "completed", extra)

    return PipelineResult(
        answer="The top 3 movies by revenue are Avatar ($2.92B), Avengers: Endgame ($2.79B), and Titanic ($2.26B).",
        sql="SELECT title, revenue FROM mart.v_movie ORDER BY revenue DESC LIMIT 3;",
        rows=[
            {"title": "Avatar", "revenue": 2923706026},
            {"title": "Avengers: Endgame", "revenue": 2797501328},
            {"title": "Titanic", "revenue": 2264162310},
        ],
        bytes_scanned=2147483648,
        stage_latencies={"schema": 0.42, "sql": 0.65, "exec": 0.38, "answer": 0.35},
        row_count=3,
        viz_recommendation={
            "primary": {
                "type": "bar",
                "x_col": "title",
                "y_col": "revenue",
                "reason": "3 movies ranked by revenue — a bar chart makes the ordering immediately scannable.",
            },
            "alternatives": [
                {"type": "table", "x_col": None, "y_col": None,
                 "reason": "Table view shows all columns and exact revenue figures."},
            ],
        },
        executed_at="2026-09-09T07:20:00Z",
        guardrails_applied=[
            {"name": "AST Read-Only Guard", "description": "Enforced AST SELECT-only validation", "rule": "AST-SELECT"},
            {"name": "Dry-Run Cost Guard", "description": "Verified estimated scan cost within limits", "rule": "Cost-Limit"},
        ],
        data_provenance=[
            {"table_name": "mart.v_movie", "type": "base_mart_view", "description": "Base movie view", "last_refreshed": "Live transactional data"}
        ],
    )


def _render_assistant_avatar() -> None:
    """Render plain square initials avatar for assistant."""
    st.markdown('<div class="pwa-avatar-square" style="margin-bottom: 0.35rem;">PW</div>', unsafe_allow_html=True)


def _render_user_turn(content: str) -> None:
    """Render user turn with right-aligned bubble and square initials avatar."""
    st.markdown(
        f"""
        <div class="pwa-chat-row user-row">
            <div class="pwa-user-bubble">{content}</div>
            <div class="pwa-avatar-square" style="margin-left: 0.4rem; margin-right: 0;">U</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_assistant_result(
    result: str | PipelineResult | dict,
    question: str = "",
    msg_idx: int = 0,
) -> None:
    """Render avatar, answer text, pipeline trace, and evidence expanders for one turn.

    Args:
        result:   PipelineResult, dict, or plain rejection string.
        question: Original question — forwarded to viz_panel for keyword heuristics.
        msg_idx:  Stable index from enumerate(messages); keys session_state for
                  the alternative chart button state of this specific turn.
    """
    _render_assistant_avatar()

    if isinstance(result, str):
        render_rejection_panel(result)
        return

    answer_text = getattr(result, "answer", None) or (result.get("answer") if isinstance(result, dict) else "")
    stage_latencies = getattr(result, "stage_latencies", None) or (result.get("stage_latencies") if isinstance(result, dict) else {})

    if answer_text:
        render_answer_panel(answer_text)

    # Collapsible pipeline trace expander
    render_pipeline_trace_expander(stage_latencies)

    # Viz panel (chart + reason caption + alternative buttons) + SQL + raw table + run details + generate report button
    render_evidence_panel(result, question=question, msg_idx=msg_idx)


def main() -> None:
    # Page Config
    st.set_page_config(
        page_title="pwa — Polyglot Warehouse Agent",
        page_icon="▪",
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    # Apply Custom Grayscale & Typography CSS
    apply_custom_styles()

    # Render Minimal Header (small top-left wordmark)
    render_header()

    # Session State Initialization
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "active_view" not in st.session_state:
        st.session_state.active_view = "chat"

    # View Router: Report View Mode vs Chat Thread Mode
    if st.session_state.active_view == "report" and st.session_state.get("active_report"):
        render_report_view(st.session_state.active_report)
        return


    # 1. Render Chat Thread Scrollback
    for msg_idx, msg in enumerate(st.session_state.messages):
        role = msg.get("role")
        content = msg.get("content", "")
        result = msg.get("result")
        # Recover the original question so the viz panel can re-apply keyword
        # heuristics and restore the correct button state during scrollback.
        original_question = msg.get("question", "")

        if role == "user":
            with st.chat_message("user", avatar=None):
                _render_user_turn(content)
        elif role == "assistant":
            with st.chat_message("assistant", avatar=None):
                _render_assistant_result(result or content, question=original_question, msg_idx=msg_idx)

    # 2. Pinned Bottom Composer
    if prompt := st.chat_input("Ask a question about warehouse data…"):
        # Append User Turn
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar=None):
            _render_user_turn(prompt)

        # Active Assistant Turn with Transient Thinking Indicator
        with st.chat_message("assistant", avatar=None):
            thinking_placeholder = st.empty()

            def _stage_cb(stage: str, status: str, extra: dict | None = None):
                if status in ("started", "retrying"):
                    with thinking_placeholder.container():
                        render_thinking_status(stage)

            try:
                if _REAL_ORCHESTRATOR_AVAILABLE and os.getenv("PWA_USE_STUB_UI") != "1":
                    res = run_query_verbose(prompt, stage_callback=_stage_cb)
                else:
                    res = _stub_run_query_verbose(prompt, stage_callback=_stage_cb)
            except Exception as exc:
                res = f"Pipeline Error: {exc}"

            # Active assistant turn: msg_idx = current length of messages (the slot
            # this turn will occupy once appended).  Session state for button clicks
            # is written here and then re-read during the next scrollback render pass.
            active_msg_idx = len(st.session_state.messages)

            thinking_placeholder.empty()

            # Render final answer and evidence (with question + stable idx for viz panel)
            _render_assistant_result(res, question=prompt, msg_idx=active_msg_idx)

            # Store in session thread state (persist question + viz_recommendation for scrollback)
            content_str = res if isinstance(res, str) else getattr(res, "answer", str(res))
            viz_rec = None
            if not isinstance(res, str):
                viz_rec = getattr(res, "viz_recommendation", None) or (
                    res.get("viz_recommendation") if isinstance(res, dict) else None
                )
            st.session_state.messages.append({
                "role": "assistant",
                "content": content_str,
                "result": res,
                "question": prompt,
                "viz_recommendation": viz_rec,
            })

        st.rerun()


if __name__ == "__main__":
    main()

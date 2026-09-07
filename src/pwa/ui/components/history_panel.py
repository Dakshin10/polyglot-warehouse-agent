"""Deprecated history panel stub.

In the chat-thread UI, conversation scrollback in st.session_state.messages
naturally replaces the separate recent questions panel.
"""

from typing import Callable, List


def render_history_panel(history: List[str], on_select_question: Callable[[str], None] | None = None) -> None:
    """No-op stub for obsolete recent questions panel."""
    pass

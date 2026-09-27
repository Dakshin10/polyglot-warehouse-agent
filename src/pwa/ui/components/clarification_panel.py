"""Clarification panel component rendering interactive buttons for semantic ambiguity resolution."""

import re
import streamlit as st


def is_ambiguity_response(text: str) -> bool:
    """Check if the assistant response is an ambiguity clarification prompt."""
    if not isinstance(text, str):
        return False
    return "ambiguous" in text.lower() and ("did you mean" in text.lower() or "did you mean:" in text.lower())


def render_clarification_panel(ambiguity_text: str, original_question: str = "") -> str | None:
    """Render interactive clarification options for ambiguous semantic terms.

    Returns:
        Selected clarified query string if user clicks a choice button, else None.
    """
    st.markdown(
        f"""
        <div style="background: #F8F9FA; border: 1px solid #CED4DA; border-left: 4px solid #111827; border-radius: 8px; padding: 1rem 1.15rem; margin-bottom: 0.75rem;">
            <div style="font-family: 'Inter', sans-serif; font-weight: 600; font-size: 0.92rem; color: #111827; display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.35rem;">
                <span>❓ Semantic Ambiguity Detected</span>
            </div>
            <div style="font-family: 'Inter', sans-serif; font-size: 0.86rem; color: #4B5563; line-height: 1.5; margin-bottom: 0.85rem;">
                {ambiguity_text}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Extract options inside parentheses or after colon
    # Example: "customer_count (Total Customers), dim_customer (Customer Master Records)"
    options = []
    # Match patterns like metric_name (Description)
    matches = re.findall(r"([a-zA-Z0-9_]+(?:\s*\([^)]+\))?)", ambiguity_text)

    # Filter out generic words
    skip_words = {
        "the",
        "term",
        "is",
        "ambiguous",
        "did",
        "you",
        "mean",
        "customers",
        "revenue",
        "sales",
        "product",
        "count",
    }
    for m in matches:
        clean = m.strip(" ,.:;?")
        if clean and clean.lower() not in skip_words and len(clean) > 2:
            if clean not in options:
                options.append(clean)

    if not options:
        options = ["dim_customer (Customer Master Records)", "customer_count (Total Customers)"]

    st.caption("Select your intended entity or metric to proceed:")
    cols = st.columns(min(len(options), 3))

    selected_query = None
    for idx, (col, opt) in enumerate(zip(cols, options[:3])):
        btn_key = f"clarify_opt_{idx}_{hash(opt)}"
        with col:
            if st.button(f"🎯 Use {opt}", key=btn_key, use_container_width=True):
                # Extract clean token for substitution
                token = opt.split("(")[0].strip()
                if original_question:
                    selected_query = f"{original_question} ({token})"
                else:
                    selected_query = f"Show details for {token}"

    return selected_query

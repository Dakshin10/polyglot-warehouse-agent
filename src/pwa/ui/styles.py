"""Monochrome chat-thread styling and typography for PWA Streamlit UI."""

import streamlit as st

FONTS_AND_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0&display=swap" rel="stylesheet">

<style>
/* ─── Design Tokens (Strict Monochrome Palette) ────────────────────────── */
:root {
    --pwa-bg: #FFFFFF;
    --pwa-surface: #F8F9FA;
    --pwa-surface-subtle: #F1F3F5;
    --pwa-border: #E9ECEF;
    --pwa-border-strong: #CED4DA;
    --pwa-text-primary: #111827;
    --pwa-text-secondary: #6B7280;
    --pwa-text-tertiary: #9CA3AF;
    --pwa-interactive: #111827;
    --pwa-interactive-hover: #000000;
    --pwa-radius: 8px;
    --pwa-radius-sm: 4px;
    --pwa-shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.03);
}

/* ─── Global Typography & Background Override ──────────────────────────── */
html, body, .stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    background-color: var(--pwa-bg) !important;
    color: var(--pwa-text-primary) !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

div, p, span, h1, h2, h3, h4, h5, h6, label {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* ─── Centered Container Layout ────────────────────────────────────────── */
.main .block-container {
    max-width: 760px !important;
    padding-top: 2rem !important;
    padding-bottom: 7.5rem !important;
    margin: 0 auto !important;
}

/* ─── Hide Default Streamlit Chrome ────────────────────────────────────── */
header[data-testid="stHeader"] {
    background-color: transparent !important;
    z-index: 1 !important;
}

footer, #MainMenu, .stDeployButton, [data-testid="stDecoration"] {
    display: none !important;
    visibility: hidden !important;
}

/* ─── Brand Wordmark ───────────────────────────────────────────────────── */
.pwa-brand {
    font-family: 'Inter', sans-serif !important;
    font-size: 1.35rem !important;
    font-weight: 700 !important;
    color: var(--pwa-text-primary);
    margin: 0;
    line-height: 1.2;
    letter-spacing: -0.02em;
}

.pwa-brand-sub {
    font-family: 'Inter', sans-serif;
    font-size: 0.82rem;
    font-weight: 400;
    color: var(--pwa-text-secondary);
    margin-top: 0.2rem;
    margin-bottom: 1.25rem;
}

/* ─── Monospace Utility ────────────────────────────────────────────────── */
.pwa-mono {
    font-family: 'JetBrains Mono', monospace !important;
}

/* ─── Chat Thread Styling ──────────────────────────────────────────────── */
div[data-testid="stChatMessage"] {
    background-color: transparent !important;
    border: none !important;
    padding: 0.4rem 0 !important;
    margin-bottom: 0.5rem !important;
}

/* Hide Streamlit default chat avatars */
div[data-testid*="stChatMessageAvatar"],
div[data-testid="stChatMessageAvatarUser"],
div[data-testid="stChatMessageAvatarAssistant"],
div[data-testid="stChatMessageAvatarCustom"],
div[data-testid="stChatMessage"] > div:first-child:has(span, img, svg) {
    display: none !important;
}

/* Square Initials Avatar */
.pwa-avatar-square {
    width: 28px;
    height: 28px;
    min-width: 28px;
    min-height: 28px;
    background-color: var(--pwa-interactive);
    color: #FFFFFF;
    border-radius: var(--pwa-radius-sm);
    font-family: 'Inter', sans-serif;
    font-size: 0.7rem;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    text-transform: uppercase;
    user-select: none;
    margin-right: 0.6rem;
    flex-shrink: 0;
}

.pwa-chat-row {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    width: 100%;
}

.pwa-chat-row.user-row {
    justify-content: flex-end;
}

/* User Speech Bubble */
.pwa-user-bubble {
    background-color: var(--pwa-surface);
    color: var(--pwa-text-primary);
    padding: 0.65rem 0.95rem;
    border-radius: var(--pwa-radius);
    border: 1px solid var(--pwa-border);
    display: inline-block;
    max-width: 85%;
    font-family: 'Inter', sans-serif;
    font-size: 0.92rem;
    font-weight: 400;
    line-height: 1.5;
    box-shadow: var(--pwa-shadow-sm);
}

/* Assistant Answer Text */
.pwa-assistant-text {
    font-family: 'Inter', sans-serif;
    font-size: 0.96rem;
    font-weight: 600;
    line-height: 1.65;
    color: var(--pwa-text-primary);
    padding: 0.15rem 0;
}

/* ─── Streamlit Expander Overrides & Bugfix for `_arr` text ────────────── */
div.stExpander, div[data-testid="stExpander"] {
    border: 1px solid var(--pwa-border) !important;
    border-radius: var(--pwa-radius) !important;
    background-color: var(--pwa-surface) !important;
    margin-top: 0.5rem !important;
    margin-bottom: 0.5rem !important;
    box-shadow: var(--pwa-shadow-sm) !important;
    overflow: hidden !important;
    transition: border-color 0.15s ease-in-out;
}

div.stExpander:hover, div[data-testid="stExpander"]:hover {
    border-color: var(--pwa-border-strong) !important;
}

/* Fix expander summary button */
div.stExpander summary, div[data-testid="stExpander"] summary {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.85rem !important;
    color: var(--pwa-text-primary) !important;
    font-weight: 500 !important;
    background-color: var(--pwa-surface) !important;
    padding: 0.55rem 0.85rem !important;
    border-radius: var(--pwa-radius) !important;
    cursor: pointer !important;
    transition: background-color 0.15s ease;
}

div.stExpander summary:hover, div[data-testid="stExpander"] summary:hover {
    background-color: var(--pwa-surface-subtle) !important;
}

/* Ensure expander icons render correctly without font ligature bleed (`_arr` text fix) */
[data-testid="stExpanderIcon"],
[data-testid="stExpanderToggleIcon"],
div.stExpander summary svg,
div[data-testid="stExpander"] summary svg {
    font-family: inherit !important;
    fill: var(--pwa-text-secondary) !important;
    color: var(--pwa-text-secondary) !important;
}

/* Expander content container */
div[data-testid="stExpanderDetails"] {
    padding: 0.85rem 0.95rem !important;
    background-color: #FFFFFF !important;
    border-top: 1px solid var(--pwa-border) !important;
}

/* ─── Buttons & Inputs ─────────────────────────────────────────────────── */
button[kind="primary"], button[kind="secondary"], .stButton > button {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.83rem !important;
    font-weight: 500 !important;
    border-radius: var(--pwa-radius) !important;
    border: 1px solid var(--pwa-border-strong) !important;
    background-color: #FFFFFF !important;
    color: var(--pwa-text-primary) !important;
    padding: 0.4rem 0.85rem !important;
    transition: all 0.15s ease-in-out !important;
    box-shadow: var(--pwa-shadow-sm) !important;
}

button[kind="primary"]:hover, button[kind="secondary"]:hover, .stButton > button:hover {
    background-color: var(--pwa-interactive) !important;
    color: #FFFFFF !important;
    border-color: var(--pwa-interactive) !important;
}

button:disabled, .stButton > button:disabled {
    background-color: var(--pwa-surface) !important;
    color: var(--pwa-text-tertiary) !important;
    border-color: var(--pwa-border) !important;
    opacity: 0.75 !important;
}

/* Code Blocks */
pre, code, .stCodeBlock, div[data-testid="stCodeBlock"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.82rem !important;
    background-color: var(--pwa-surface) !important;
    border: 1px solid var(--pwa-border) !important;
    border-radius: var(--pwa-radius) !important;
    color: var(--pwa-text-primary) !important;
    box-shadow: none !important;
}

/* Dataframe & Tables */
div[data-testid="stDataFrame"], div[data-testid="stTable"] {
    border: 1px solid var(--pwa-border) !important;
    border-radius: var(--pwa-radius) !important;
    background-color: var(--pwa-bg) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.82rem !important;
    overflow: hidden !important;
}

/* Pipeline Stage Pill Badges */
.pwa-pill {
    display: inline-flex;
    align-items: center;
    padding: 0.15rem 0.5rem;
    border-radius: var(--pwa-radius-sm);
    font-family: 'Inter', sans-serif;
    font-size: 0.74rem;
    font-weight: 500;
    line-height: 1.2;
    margin-left: 0.35rem;
}

.pwa-pill-cached {
    background-color: var(--pwa-interactive);
    color: #FFFFFF;
    border: 1px solid var(--pwa-interactive);
}

.pwa-pill-template {
    background-color: var(--pwa-surface-subtle);
    color: var(--pwa-text-primary);
    border: 1px solid var(--pwa-border-strong);
}

.pwa-pill-llm {
    background-color: transparent;
    color: var(--pwa-text-secondary);
    border: 1px solid var(--pwa-border);
}

/* Quiet Metadata Text */
.pwa-quiet-meta {
    font-family: 'Inter', sans-serif;
    font-size: 0.82rem;
    font-weight: 400;
    color: var(--pwa-text-secondary);
}

/* Bottom Chat Input Box */
div[data-testid="stChatInput"] {
    max-width: 760px !important;
    margin: 0 auto !important;
    background-color: #FFFFFF !important;
    border: 1px solid var(--pwa-border-strong) !important;
    border-radius: var(--pwa-radius) !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05) !important;
    padding: 0.35rem 0.65rem !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

div[data-testid="stChatInput"]:focus-within {
    border-color: var(--pwa-interactive) !important;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1) !important;
}

div[data-testid="stChatInput"] textarea {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.93rem !important;
    font-weight: 400 !important;
    color: var(--pwa-text-primary) !important;
}

div[data-testid="stChatInput"] textarea::placeholder {
    color: var(--pwa-text-tertiary) !important;
}

div[data-testid="stChatInput"] button {
    color: var(--pwa-interactive) !important;
    background: transparent !important;
    border: none !important;
}

/* ─── Streamlit Alerts (Info, Warning, Success, Error) Monochrome Override ─ */
div[data-testid="stAlert"], .stAlert {
    background-color: var(--pwa-surface) !important;
    color: var(--pwa-text-primary) !important;
    border: 1px solid var(--pwa-border-strong) !important;
    border-radius: var(--pwa-radius) !important;
}

div[data-testid="stAlert"] svg, .stAlert svg {
    fill: var(--pwa-text-primary) !important;
}

/* Rejection/Error Box */
.pwa-error-box {
    border: 1px solid var(--pwa-text-primary);
    background-color: var(--pwa-surface);
    border-radius: var(--pwa-radius);
    padding: 0.85rem 1.05rem;
    margin: 0.5rem 0;
}

.pwa-error-title {
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    font-size: 0.88rem;
    color: var(--pwa-text-primary);
    margin-bottom: 0.3rem;
}

.pwa-error-detail {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    color: var(--pwa-text-secondary);
    white-space: pre-wrap;
}

/* Thinking Indicator */
.pwa-thinking {
    font-family: 'Inter', sans-serif;
    font-size: 0.85rem;
    font-weight: 400;
    color: var(--pwa-text-secondary);
    display: flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.5rem 0;
}

.pwa-thinking-dot {
    width: 6px;
    height: 6px;
    background-color: var(--pwa-interactive);
    border-radius: 50%;
    animation: pwa-pulse 1.2s infinite ease-in-out;
}

@keyframes pwa-pulse {
    0% { opacity: 0.2; transform: scale(0.9); }
    50% { opacity: 1; transform: scale(1.1); }
    100% { opacity: 0.2; transform: scale(0.9); }
}
</style>
"""


def apply_custom_styles() -> None:
    """Inject custom Inter / JetBrains Mono Google Fonts and monochrome CSS into Streamlit page."""
    st.markdown(FONTS_AND_CSS, unsafe_allow_html=True)

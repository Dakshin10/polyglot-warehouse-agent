"""Monochrome chat-thread styling and typography for PWA Streamlit UI."""

import streamlit as st

FONTS_AND_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap" rel="stylesheet">

<style>
/* Design Tokens (Monochrome Palette & Geometry) */
:root {
    --pwa-bg: #FFFFFF;
    --pwa-surface: #F5F5F5;
    --pwa-border: #E0E0E0;
    --pwa-text-secondary: #6B6B6B;
    --pwa-text-primary: #111111;
    --pwa-interactive: #2B2B2B;
    --pwa-radius: 4px;
}

/* Global Typography & Background Override */
html, body, [class*="st-"], .stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    background-color: var(--pwa-bg) !important;
    color: var(--pwa-text-primary) !important;
    -webkit-font-smoothing: antialiased;
}

/* Material Symbols Icon Font Preservation */
.material-symbols-outlined,
.material-icons,
[class*="material-symbols"],
[data-testid="stExpanderIcon"],
[data-testid="stIcon"],
.stIcon,
span[data-testid="stExpanderToggleIcon"] {
    font-family: 'Material Symbols Outlined', 'Material Icons' !important;
}

/* Centered Thread Layout (~700px max width) */
.main .block-container {
    max-width: 700px !important;
    padding-top: 1.5rem !important;
    padding-bottom: 6.5rem !important;
    margin: 0 auto !important;
}

/* Hide Default Streamlit Chrome (Header bar decoration, footer, deployment buttons) */
header[data-testid="stHeader"] {
    background-color: transparent !important;
}
footer {
    display: none !important;
}
#MainMenu, .stDeployButton {
    visibility: hidden !important;
    display: none !important;
}

/* Brand Wordmark */
.pwa-brand {
    font-family: 'Inter', sans-serif !important;
    font-size: 1.25rem !important;
    font-weight: 600 !important;
    color: var(--pwa-text-primary);
    margin: 0;
    line-height: 1.2;
    letter-spacing: -0.01em;
}

.pwa-brand-sub {
    font-family: 'Inter', sans-serif;
    font-size: 0.8rem;
    font-weight: 400;
    color: var(--pwa-text-secondary);
    margin-top: 0.15rem;
    margin-bottom: 1.25rem;
}

/* Monospace Class — strictly for SQL, code, table data */
.pwa-mono {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Chat Thread Overrides */
div[data-testid="stChatMessage"] {
    background-color: transparent !important;
    border: none !important;
    padding: 0.5rem 0 !important;
    margin-bottom: 0.25rem !important;
}

/* Hide Streamlit default chat avatars across all versions */
div[data-testid*="stChatMessageAvatar"],
div[data-testid="stChatMessageAvatarUser"],
div[data-testid="stChatMessageAvatarAssistant"],
div[data-testid="stChatMessageAvatarCustom"],
div[data-testid="stChatMessage"] > div:first-child:has(span, img, svg) {
    display: none !important;
}

/* Custom Initials Square Avatar */
.pwa-avatar-square {
    width: 28px;
    height: 28px;
    min-width: 28px;
    min-height: 28px;
    background-color: var(--pwa-surface);
    border: 1px solid var(--pwa-border);
    border-radius: var(--pwa-radius);
    font-family: 'Inter', sans-serif;
    font-size: 0.72rem;
    font-weight: 500;
    color: var(--pwa-text-secondary);
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

/* User Bubble: Right-aligned, surface bg, 1px border, 4px radius */
.pwa-user-bubble {
    background-color: var(--pwa-surface);
    color: var(--pwa-text-primary);
    padding: 0.55rem 0.85rem;
    border-radius: var(--pwa-radius);
    border: 1px solid var(--pwa-border);
    display: inline-block;
    max-width: 85%;
    font-family: 'Inter', sans-serif;
    font-size: 0.92rem;
    font-weight: 400;
    line-height: 1.5;
}

/* Assistant Answer Text: Weight 600 for final synthesized answer text */
.pwa-assistant-text {
    font-family: 'Inter', sans-serif;
    font-size: 0.95rem;
    font-weight: 600;
    line-height: 1.6;
    color: var(--pwa-text-primary);
    padding: 0.2rem 0;
}

/* Collapsible Section (st.expander): Flat 1px border, 4px radius, no shadow */
div.stExpander, div[data-testid="stExpander"] {
    border: 1px solid var(--pwa-border) !important;
    border-radius: var(--pwa-radius) !important;
    background-color: var(--pwa-surface) !important;
    margin-top: 0.4rem !important;
    margin-bottom: 0.4rem !important;
    box-shadow: none !important;
    overflow: hidden !important;
}

div.stExpander summary, div[data-testid="stExpander"] summary {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.84rem !important;
    color: var(--pwa-text-primary) !important;
    font-weight: 500 !important;
    background-color: var(--pwa-surface) !important;
    padding: 0.45rem 0.75rem !important;
    border-radius: var(--pwa-radius) !important;
}

div.stExpander summary:hover, div[data-testid="stExpander"] summary:hover {
    color: var(--pwa-interactive) !important;
    background-color: #EFEFEF !important;
}

/* Code Blocks: JetBrains Mono, surface bg, 1px border, 4px radius */
pre, code, .stCodeBlock, div[data-testid="stCodeBlock"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.82rem !important;
    background-color: var(--pwa-surface) !important;
    border: 1px solid var(--pwa-border) !important;
    border-radius: var(--pwa-radius) !important;
    color: var(--pwa-text-primary) !important;
    box-shadow: none !important;
}

/* Native st.dataframe Styling Overrides: No colored header row, thin grey dividers */
div[data-testid="stDataFrame"], div[data-testid="stTable"] {
    border: 1px solid var(--pwa-border) !important;
    border-radius: var(--pwa-radius) !important;
    background-color: var(--pwa-bg) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.82rem !important;
    overflow: hidden !important;
}

div[data-testid="stDataFrame"] iframe {
    border-radius: var(--pwa-radius) !important;
}

/* Pipeline Stage Pill Badges (Grey Outline vs Subtle Fill) */
.pwa-pill {
    display: inline-flex;
    align-items: center;
    padding: 0.12rem 0.45rem;
    border-radius: var(--pwa-radius);
    font-family: 'Inter', sans-serif;
    font-size: 0.75rem;
    font-weight: 500;
    line-height: 1.2;
    margin-left: 0.35rem;
}

.pwa-pill-cached {
    background-color: var(--pwa-border);
    color: var(--pwa-text-primary);
    border: 1px solid var(--pwa-border);
}

.pwa-pill-template {
    background-color: var(--pwa-surface);
    color: var(--pwa-text-primary);
    border: 1px solid var(--pwa-border);
}

.pwa-pill-llm {
    background-color: transparent;
    color: var(--pwa-text-secondary);
    border: 1px solid var(--pwa-border);
}

/* Quiet Metadata Text */
.pwa-quiet-meta {
    font-family: 'Inter', sans-serif;
    font-size: 0.8rem;
    font-weight: 400;
    color: var(--pwa-text-secondary);
}

/* Chat Input Box: Flat 1px border, 4px radius, no shadow, #2B2B2B focus ring */
div[data-testid="stChatInput"] {
    max-width: 700px !important;
    margin: 0 auto !important;
    background-color: var(--pwa-bg) !important;
    border: 1px solid var(--pwa-border) !important;
    border-radius: var(--pwa-radius) !important;
    box-shadow: none !important;
    padding: 0.25rem 0.5rem !important;
}

div[data-testid="stChatInput"]:focus-within {
    border-color: var(--pwa-interactive) !important;
    outline: 1.5px solid var(--pwa-interactive) !important;
}

div[data-testid="stChatInput"] textarea {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.92rem !important;
    font-weight: 400 !important;
    color: var(--pwa-text-primary) !important;
}

div[data-testid="stChatInput"] textarea::placeholder {
    color: var(--pwa-text-secondary) !important;
}

div[data-testid="stChatInput"] button {
    color: var(--pwa-interactive) !important;
    background: transparent !important;
    border: none !important;
}

div[data-testid="stChatInput"] button:hover {
    color: var(--pwa-text-primary) !important;
}

/* Rejection/Error Box: Monochrome 1px border, no colored alert styles */
.pwa-error-box {
    border: 1px solid var(--pwa-text-primary);
    background-color: var(--pwa-surface);
    border-radius: var(--pwa-radius);
    padding: 0.8rem 1rem;
    margin: 0.4rem 0;
}

.pwa-error-title {
    font-family: 'Inter', sans-serif;
    font-weight: 500;
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
    font-size: 0.84rem;
    font-weight: 400;
    color: var(--pwa-text-secondary);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0;
}

.pwa-thinking-dot {
    width: 5px;
    height: 5px;
    background-color: var(--pwa-interactive);
    border-radius: 50%;
    animation: pwa-pulse 1.2s infinite ease-in-out;
}

@keyframes pwa-pulse {
    0% { opacity: 0.2; }
    50% { opacity: 1; }
    100% { opacity: 0.2; }
}
</style>
"""


def apply_custom_styles() -> None:
    """Inject custom Inter / JetBrains Mono Google Fonts and monochrome CSS into Streamlit page."""
    st.markdown(FONTS_AND_CSS, unsafe_allow_html=True)

"""Minimal username/password auth gate for the Streamlit app.

The app previously had zero authentication: anyone who reached the URL was
anyone, every query ran under the same BigQuery identity with no per-user
attribution, and there was no audit trail tied to a real user.

This is deliberately NOT a replacement for a real identity provider — for a
production deployment, put this app behind Cloud IAP or an OAuth-terminating
proxy and read the verified identity from the resulting request header
instead of this module. This exists so the app is not wide open in the
meantime, and so query auditing has a real (if self-managed) identity to
attach to.

Configuration
-------------
PWA_AUTH_USERS   JSON object mapping username -> "<hex_salt>$<hex_pbkdf2_hash>"
                 (produced by `pwa auth add-user <username>`). If unset, the
                 app runs with NO auth gate (same as before) but renders a
                 visible "no authentication configured" banner instead of
                 silently being open with no indication of it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from typing import Optional

_PBKDF2_ITERATIONS = 260_000


def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Return "<hex_salt>$<hex_hash>" for storage in PWA_AUTH_USERS."""
    salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, _PBKDF2_ITERATIONS)
    return f"{salt_bytes.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification of `password` against a hash_password() value."""
    try:
        salt_hex, _ = stored.split("$", 1)
    except ValueError:
        return False
    candidate = hash_password(password, salt=salt_hex)
    return hmac.compare_digest(candidate, stored)


def _configured_users() -> dict[str, str]:
    raw = os.getenv("PWA_AUTH_USERS", "").strip()
    if not raw:
        return {}
    try:
        users = json.loads(raw)
        return users if isinstance(users, dict) else {}
    except (TypeError, ValueError):
        return {}


def is_auth_configured() -> bool:
    return bool(_configured_users())


def authenticate(username: str, password: str) -> bool:
    """Verify credentials against PWA_AUTH_USERS. Empty username never matches."""
    if not username:
        return False
    users = _configured_users()
    stored = users.get(username)
    return stored is not None and verify_password(password, stored)


def require_login() -> str:
    """Render a login form and block until authenticated; returns the username.

    No-op (returns "anonymous") if PWA_AUTH_USERS is not configured — see
    module docstring for why that is the deliberate default.
    """
    import streamlit as st

    if not is_auth_configured():
        return "anonymous"

    if st.session_state.get("pwa_authenticated_user"):
        return str(st.session_state["pwa_authenticated_user"])

    st.markdown("### Sign in")
    with st.form("pwa_login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        if authenticate(username, password):
            st.session_state["pwa_authenticated_user"] = username
            st.rerun()
        else:
            st.error("Invalid username or password.")

    st.stop()
    return ""  # unreachable — st.stop() raises

"""Unit tests for the Streamlit app's username/password auth gate."""

import json

from pwa.ui.auth import authenticate, hash_password, is_auth_configured, verify_password


def test_hash_and_verify_round_trip():
    stored = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", stored) is True
    assert verify_password("wrong password", stored) is False


def test_hash_password_uses_random_salt_by_default():
    a = hash_password("same password")
    b = hash_password("same password")
    assert a != b  # different random salts -> different stored strings
    assert verify_password("same password", a)
    assert verify_password("same password", b)


def test_verify_password_rejects_malformed_stored_value():
    assert verify_password("anything", "not-a-valid-stored-hash") is False


def test_is_auth_configured_false_when_env_unset(monkeypatch):
    monkeypatch.delenv("PWA_AUTH_USERS", raising=False)
    assert is_auth_configured() is False


def test_is_auth_configured_true_when_users_present(monkeypatch):
    stored = hash_password("secret123")
    monkeypatch.setenv("PWA_AUTH_USERS", json.dumps({"alice": stored}))
    assert is_auth_configured() is True


def test_authenticate_accepts_correct_credentials(monkeypatch):
    stored = hash_password("secret123")
    monkeypatch.setenv("PWA_AUTH_USERS", json.dumps({"alice": stored}))
    assert authenticate("alice", "secret123") is True


def test_authenticate_rejects_wrong_password(monkeypatch):
    stored = hash_password("secret123")
    monkeypatch.setenv("PWA_AUTH_USERS", json.dumps({"alice": stored}))
    assert authenticate("alice", "wrong") is False


def test_authenticate_rejects_unknown_user(monkeypatch):
    stored = hash_password("secret123")
    monkeypatch.setenv("PWA_AUTH_USERS", json.dumps({"alice": stored}))
    assert authenticate("bob", "secret123") is False


def test_authenticate_rejects_empty_username(monkeypatch):
    monkeypatch.delenv("PWA_AUTH_USERS", raising=False)
    assert authenticate("", "anything") is False


def test_authenticate_handles_malformed_env_json(monkeypatch):
    monkeypatch.setenv("PWA_AUTH_USERS", "{not valid json")
    assert authenticate("alice", "secret123") is False
    assert is_auth_configured() is False

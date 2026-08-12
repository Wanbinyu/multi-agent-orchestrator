"""Unit tests for feedback sanitizer (no network)."""
from __future__ import annotations

from scripts.sanitize_feedback_text import sanitize


def test_sanitize_redacts_common_api_keys_and_bearer():
    # Intentionally fake samples shaped like real tokens (sanitizer + gitleaks allowlist).
    # gitleaks:allow  # path allowlisted in .gitleaks.toml for historical fixtures too
    raw = (
        "key=sk-TESTONLY_not_a_real_key_48e8eb175496 "
        "ark=ark-TESTONLY-not-real-f1626370-b4f0 "
        "hdr=Bearer TESTONLY_token_abcdefghijklmnop"
    )
    out = sanitize(raw)
    assert "sk-TESTONLY" not in out
    assert "ark-TESTONLY" not in out
    assert "TESTONLY_token_abcdefghijklmnop" not in out
    assert "sk-***" in out
    assert "ark-***" in out
    assert "Bearer ***" in out


def test_sanitize_redacts_user_home_segments():
    raw = r"path=C:\Users\alice\project\src\main.py and /home/bob/app"
    out = sanitize(raw)
    assert "alice" not in out
    assert "bob" not in out
    assert r"C:\Users\<user>\project" in out or "Users\\<user>" in out
    assert "/home/<user>/app" in out


def test_sanitize_redacts_env_style_assignments():
    raw = "API_KEY=super-secret-value password: hunter2"
    out = sanitize(raw)
    assert "super-secret-value" not in out
    assert "hunter2" not in out

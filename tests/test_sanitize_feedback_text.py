"""Unit tests for feedback sanitizer (no network)."""
from __future__ import annotations

from scripts.sanitize_feedback_text import sanitize


def test_sanitize_redacts_common_api_keys_and_bearer():
    raw = (
        "key=sk-48e8eb175496d847ce479a5a45719c89 "
        "ark=ark-f1626370-b4f0-40a4-a993-eca26bf451c0 "
        "hdr=Bearer abcdefghijklmnop"
    )
    out = sanitize(raw)
    assert "sk-48e8" not in out
    assert "ark-f162" not in out
    assert "abcdefghijklmnop" not in out
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

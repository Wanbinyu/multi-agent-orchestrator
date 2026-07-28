"""Agent turn wall-clock timeout."""
from __future__ import annotations

import time

import pytest

from src.core.turn_timeout import (
    TurnDeadline,
    TurnTimeoutError,
    resolve_turn_timeout_seconds,
)


def test_resolve_turn_timeout_from_env(monkeypatch):
    monkeypatch.setenv("MAO_TURN_TIMEOUT_SECONDS", "120")
    assert resolve_turn_timeout_seconds() == 120.0
    monkeypatch.setenv("MAO_TURN_TIMEOUT_SECONDS", "0")
    assert resolve_turn_timeout_seconds() == 0.0
    monkeypatch.delenv("MAO_TURN_TIMEOUT_SECONDS", raising=False)
    assert resolve_turn_timeout_seconds(default=900) == 900.0


def test_deadline_disabled_when_zero(monkeypatch):
    monkeypatch.setenv("MAO_TURN_TIMEOUT_SECONDS", "0")
    deadline = TurnDeadline.start()
    assert deadline.enabled is False
    deadline.check()  # no raise


def test_deadline_raises_when_exceeded(monkeypatch):
    monkeypatch.setenv("MAO_TURN_TIMEOUT_SECONDS", "0.05")
    deadline = TurnDeadline.start()
    time.sleep(0.06)
    with pytest.raises(TurnTimeoutError) as exc:
        deadline.check()
    assert exc.value.limit_seconds == 0.05

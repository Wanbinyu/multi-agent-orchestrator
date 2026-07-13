"""CLI 权限模式切换相关单元测试"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.cli.chat_command import _set_mode
from src.core.session import Session


def _make_session(mode: str = "approve") -> Session:
    return Session(
        id="test-session",
        title="test",
        created_at="2026-07-12T00:00:00+00:00",
        updated_at="2026-07-12T00:00:00+00:00",
        output_dir="output",
        approval_mode=mode,  # type: ignore[arg-type]
    )


def test_set_mode_valid():
    session = _make_session("approve")
    agent = MagicMock()
    agent.approval_mode = "approve"
    mode_ref = ["approve"]

    assert _set_mode(session, agent, mode_ref, "auto") is True
    assert session.approval_mode == "auto"
    assert agent.approval_mode == "auto"
    assert mode_ref[0] == "auto"


def test_set_mode_invalid():
    session = _make_session("approve")
    agent = MagicMock()
    agent.approval_mode = "approve"
    mode_ref = ["approve"]

    assert _set_mode(session, agent, mode_ref, "invalid") is False
    assert session.approval_mode == "approve"
    assert mode_ref[0] == "approve"


def test_set_mode_cycle_logic():
    """验证 /mode 无参数时的循环顺序 approve -> readonly -> auto -> approve"""
    from src.cli.chat_command import MODES

    session = _make_session("approve")
    agent = MagicMock()
    agent.approval_mode = "approve"
    mode_ref = ["approve"]

    for expected in ["readonly", "auto", "approve"]:
        idx = MODES.index(mode_ref[0])
        next_mode = MODES[(idx + 1) % len(MODES)]
        _set_mode(session, agent, mode_ref, next_mode)
        assert mode_ref[0] == expected

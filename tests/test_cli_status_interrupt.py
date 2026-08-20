"""P0-10 /status and interrupt journal handling."""
from __future__ import annotations

from unittest.mock import MagicMock

from src.cli.chat_command import COMMANDS, _cmd_status
from src.core.agent import Agent
from src.core.engineering import RunJournalStore
from src.core.session import Session
from src.models.schemas import ChatResponse


def _session(tmp_path) -> Session:
    return Session(
        id="status-session",
        title="t",
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
        approval_mode="approve",
        execution_depth="auto",
        collaboration_mode="auto",
    )


def test_help_documents_status_and_resume():
    assert "/status" in COMMANDS
    assert "/resume" in COMMANDS
    assert "Ctrl+C" in COMMANDS


def test_status_is_local_and_includes_session_facts(tmp_path, capsys):
    session = _session(tmp_path)
    gateway = MagicMock()
    gateway.main_model = None
    gateway.chat_with_main_model.return_value = ChatResponse(
        content="unused", model="m", provider="p", input_tokens=0, output_tokens=0
    )
    agent = Agent(gateway, session)
    status = _cmd_status(agent)
    output = capsys.readouterr().out
    assert status["approval_mode"] == "approve"
    assert status["collaboration_mode"] == "auto"
    assert status["auto_checkpoint"] is True
    assert "权限模式" in output
    assert "写前自动检查点" in output
    assert "不调用模型" in output
    gateway.chat_with_main_model.assert_not_called()


def test_interrupt_turn_does_not_leave_journal_running(tmp_path):
    session = _session(tmp_path)
    gateway = MagicMock()
    gateway.main_model = None
    agent = Agent(gateway, session, journal_store=RunJournalStore(tmp_path / "runs"))
    journal = agent._start_engineering_run("修复 CLI")
    assert journal.status == "running"

    payload = agent.interrupt_turn("用户中断本轮")

    loaded = agent.journal_store.load(journal.run_id)
    assert payload is not None
    assert loaded.status == "blocked"
    assert loaded.status != "running"
    assert loaded.metrics.get("interrupted") is True
    assert any("用户中断" in item for item in loaded.residual_risks)
    assert agent._active_run_journal is None
    gateway.chat_with_main_model.assert_not_called()

"""B4.3 deterministic interrupted-session recovery."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.agent import Agent
from src.core.engineering import (
    RecoveryConfirmationRequired,
    RunJournalStore,
    SessionRecoveryManager,
    WorkPlan,
    WorkPlanStep,
)
from src.core.session import SessionStore
from src.cli.chat_command import _cmd_load, _cmd_resume


def _interrupted_session(tmp_path):
    sessions = SessionStore(tmp_path / "sessions")
    session = sessions.create("interrupted")
    runs = RunJournalStore.from_output_dir(session.output_dir)
    journal = runs.create(session.id, "build dashboard", "auto")
    journal.plan = WorkPlan(
        objective="build dashboard",
        status="in_progress",
        steps=[
            WorkPlanStep(id="done", title="create shell", status="completed"),
            WorkPlanStep(id="todo", title="wire routes", status="in_progress"),
        ],
    )
    journal.files_changed = ["src/shell.js"]
    runs.save(journal)
    return sessions, session, runs, journal


def test_detects_latest_running_run_and_unfinished_plan(tmp_path):
    _, session, _, journal = _interrupted_session(tmp_path)

    state = SessionRecoveryManager(session).inspect()

    assert state.required is True
    assert state.run_id == journal.run_id
    assert state.run_status == "running"
    assert state.unfinished_step_count == 1
    assert state.unfinished_steps[0]["id"] == "todo"
    assert state.completed_steps[0]["id"] == "done"


def test_continue_seals_old_run_and_claims_only_checkpoint_metadata(tmp_path):
    sessions, session, runs, old = _interrupted_session(tmp_path)
    manager = SessionRecoveryManager(session, runs)

    state = manager.decide("continue")

    assert state.required is False
    sealed = runs.load(old.run_id)
    assert sealed.status == "blocked"
    assert any("用户确认继续" in item for item in sealed.decisions)
    assert sealed.plan.steps[0].status == "completed"
    assert sealed.plan.steps[1].status == "in_progress"
    new = runs.create(session.id, "continue unfinished work", "auto")
    checkpoint = manager.claim_checkpoint(new.run_id)
    assert checkpoint is not None
    assert checkpoint.completed_step_ids == ["done"]
    assert checkpoint.unfinished_step_ids == ["todo"]
    assert checkpoint.files_changed == ["src/shell.js"]
    assert manager.claim_checkpoint("another-run") is None
    sessions.save(session)
    assert sessions.load(session.id).recovery_decisions[0].consumed_by_run_id == new.run_id


def test_abandon_preserves_completed_steps_and_blocks_only_unfinished(tmp_path):
    _, session, runs, old = _interrupted_session(tmp_path)

    SessionRecoveryManager(session, runs).decide("abandon")

    abandoned = runs.load(old.run_id)
    assert abandoned.plan.steps[0].status == "completed"
    assert abandoned.plan.steps[1].status == "blocked"
    assert abandoned.files_changed == ["src/shell.js"]
    assert any("不自动回滚" in item for item in abandoned.decisions)


def test_completed_run_with_unfinished_plan_is_sealed_as_blocked(tmp_path):
    _, session, runs, journal = _interrupted_session(tmp_path)
    journal.finish("completed")
    runs.save(journal)

    state = SessionRecoveryManager(session, runs).decide("continue")

    assert state.required is False
    sealed = runs.load(journal.run_id)
    assert sealed.status == "blocked"
    assert any("计划仍有未完成步骤" in item for item in sealed.residual_risks)


def test_agent_refuses_provider_or_new_run_before_recovery_confirmation(tmp_path):
    _, session, runs, old = _interrupted_session(tmp_path)
    gateway = MagicMock()
    agent = Agent(gateway, session, journal_store=runs)

    with pytest.raises(RecoveryConfirmationRequired):
        agent.run_turn("continue")

    gateway.chat_with_main_model.assert_not_called()
    assert [item.run_id for item in runs.list()] == [old.run_id]


def test_cli_load_prints_notice_and_resume_requires_explicit_action(tmp_path, capsys):
    sessions, session, _, _ = _interrupted_session(tmp_path)
    sessions.save(session)

    loaded = _cmd_load(sessions, session.id)
    assert loaded is not None
    assert _cmd_resume(sessions, loaded, "continue") is True

    output = capsys.readouterr().out
    assert "检测到中断任务" in output
    assert "/resume continue" in output
    assert "已确认继续" in output

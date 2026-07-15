"""Phase 7.0 工程运行状态与持久化测试。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.engineering import (
    Evidence,
    RunJournalStore,
    VerificationGate,
    WorkPlan,
    WorkPlanStep,
)


def test_work_plan_enforces_single_active_step_and_transitions():
    first = WorkPlanStep(id="inspect", title="检查项目")
    second = WorkPlanStep(id="test", title="运行测试")
    plan = WorkPlan(objective="稳定项目", steps=[first, second])

    plan.transition_step("inspect", "in_progress")
    assert plan.status == "in_progress"
    with pytest.raises(ValueError, match="同时最多一个"):
        plan.transition_step("test", "in_progress")

    plan.transition_step("inspect", "completed", evidence_ids=["ev-1"])
    plan.transition_step("test", "in_progress")
    plan.transition_step("test", "completed")
    assert plan.status == "completed"
    assert first.evidence_ids == ["ev-1"]


def test_work_plan_rejects_invalid_state_and_invalid_initial_shape():
    with pytest.raises(ValidationError, match="同时最多一个"):
        WorkPlan(
            objective="bad",
            steps=[
                WorkPlanStep(title="a", status="in_progress"),
                WorkPlanStep(title="b", status="in_progress"),
            ],
        )

    plan = WorkPlan(objective="test", steps=[WorkPlanStep(id="a", title="a")])
    with pytest.raises(ValueError, match="非法计划状态迁移"):
        plan.transition_step("a", "completed")
    with pytest.raises(KeyError, match="不存在"):
        plan.transition_step("missing", "in_progress")


def test_evidence_and_verification_validate_fields():
    evidence = Evidence(source="pytest", claim="测试通过", confidence=0.9)
    gate = VerificationGate(requirement="行为稳定", passed=True, actual="399 passed")
    assert evidence.id.startswith("ev-")
    assert gate.id.startswith("gate-")
    with pytest.raises(ValidationError):
        Evidence(source="pytest", claim="x", confidence=1.1)


def test_run_journal_store_round_trip_and_atomic_write(tmp_path):
    store = RunJournalStore(tmp_path / "runs")
    journal = store.create("session-1", "修复 CLI", "approve")
    assert store.load(journal.run_id).status == "running"
    journal.evidence.append(Evidence(source="file", claim="找到入口", excerpt="main.py"))
    journal.verification.append(
        VerificationGate(requirement="测试通过", command_or_check="pytest", passed=True)
    )
    journal.finish(
        "completed",
        files_changed=["src/main.py"],
        metrics={"input_tokens": 10},
    )
    path = store.save(journal)

    loaded = store.load(journal.run_id)
    assert loaded.status == "completed"
    assert loaded.intent.write_authorized is False
    assert loaded.files_changed == ["src/main.py"]
    assert loaded.objective == "修复 CLI"
    assert loaded.metrics["input_tokens"] == 10
    assert path.exists()
    assert not list((tmp_path / "runs").glob("*.tmp"))
    assert store.latest().run_id == journal.run_id


def test_run_journal_store_rejects_unsafe_id_and_missing_run(tmp_path):
    store = RunJournalStore(tmp_path / "runs")
    with pytest.raises(ValueError, match="非法 run_id"):
        store.load("../outside")
    with pytest.raises(FileNotFoundError):
        store.load("missing")

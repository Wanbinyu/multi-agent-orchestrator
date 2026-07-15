"""Phase 7.0 工程运行状态与持久化测试。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.engineering import (
    Evidence,
    RunJournalStore,
    TaskIntentClassifier,
    ToolEvidenceRecorder,
    VerificationGate,
    WorkPlan,
    WorkPlanStep,
)
from src.tools.tool_result import ToolResult


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
    intent = TaskIntentClassifier().classify("修复 CLI", "approve")
    journal = store.create("session-1", "修复 CLI", "approve", intent=intent)
    assert store.load(journal.run_id).status == "running"
    assert journal.intent.kind == "change"
    assert "任务分类为 change" in journal.decisions[0]
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


def test_unclassified_store_default_stays_readonly_even_in_auto_mode(tmp_path):
    store = RunJournalStore(tmp_path / "runs")

    journal = store.create("session-1", "继续处理", "auto")

    assert journal.intent.kind == "unclassified"
    assert journal.intent.write_authorized is False
    assert journal.intent.policy.allow_project_writes is False


def test_tool_evidence_drives_reconnaissance_without_double_counting(tmp_path):
    store = RunJournalStore(tmp_path / "runs")
    journal = store.create("session-1", "检查项目", "auto")
    recorder = ToolEvidenceRecorder()

    observations = [
        ("project_tree", {"path": "."}, "project tree"),
        ("git_status", {"path": "."}, "## main"),
        ("read_file", {"path": "README.md"}, "docs"),
        ("read_file", {"path": "pyproject.toml"}, "deps"),
        ("read_file", {"path": "src/main.py"}, "entry"),
        ("read_file", {"path": "tests/test_main.py"}, "tests"),
    ]
    for tool_name, params, output in observations:
        assert recorder.record(
            journal, tool_name, params, ToolResult(success=True, output=output)
        )

    assert journal.reconnaissance.tool_calls == len(observations)
    assert journal.reconnaissance.status == "completed"
    assert journal.reconnaissance.missing_categories() == []
    assert len(journal.reconnaissance.observed_categories) == 6
    assert len(journal.evidence) == len(observations)

    assert recorder.record(
        journal,
        "read_file",
        {"path": "README.md"},
        ToolResult(success=True, output="docs"),
        cached=True,
    ) is False
    assert journal.reconnaissance.tool_calls == len(observations)
    assert len(journal.evidence) == len(observations)


def test_skipped_read_is_evidence_but_not_reconnaissance_coverage(tmp_path):
    store = RunJournalStore(tmp_path / "runs")
    journal = store.create("session-1", "检查项目", "auto")
    recorder = ToolEvidenceRecorder()

    changed = recorder.record(
        journal,
        "read_file",
        {"path": "README.md"},
        ToolResult(success=True, output="达到抽样上限"),
        skipped=True,
    )

    assert changed is True
    assert journal.evidence[0].metadata["skipped"] is True
    assert journal.reconnaissance.tool_calls == 0
    assert journal.reconnaissance.files_sampled == []
    assert journal.reconnaissance.skipped_areas == ["README.md"]


def test_reconnaissance_stays_partial_until_all_six_categories_are_observed(tmp_path):
    journal = RunJournalStore(tmp_path / "runs").create(
        "session-1", "检查项目", "auto"
    )
    recorder = ToolEvidenceRecorder()
    for tool_name, params in (
        ("project_tree", {"path": "."}),
        ("git_status", {"path": "."}),
        ("read_file", {"path": "README.md"}),
        ("read_file", {"path": "src/main.py"}),
    ):
        recorder.record(
            journal, tool_name, params, ToolResult(success=True, output="ok")
        )

    journal.finish("completed")

    assert journal.reconnaissance.status == "partial"
    assert journal.reconnaissance.missing_categories() == ["dependencies", "tests"]


def test_hypothesis_requires_known_direct_evidence(tmp_path):
    journal = RunJournalStore(tmp_path / "runs").create(
        "session-1", "诊断故障", "auto"
    )
    hypothesis = journal.add_hypothesis("配置文件缺失")

    with pytest.raises(ValueError, match="必须引用直接证据"):
        journal.evaluate_hypothesis(hypothesis.id, "supported")
    with pytest.raises(ValueError, match="未知证据"):
        journal.evaluate_hypothesis(
            hypothesis.id, "refuted", evidence_ids=["ev-missing"]
        )

    evidence, _ = journal.add_evidence(
        Evidence(source="tool:read_file", claim="配置文件存在")
    )
    evaluated = journal.evaluate_hypothesis(
        hypothesis.id, "refuted", evidence_ids=[evidence.id]
    )
    assert evaluated.status == "refuted"
    assert evaluated.contradicting_evidence_ids == [evidence.id]


def test_failed_test_evidence_keeps_output_and_error(tmp_path):
    journal = RunJournalStore(tmp_path / "runs").create(
        "session-1", "运行测试", "auto"
    )
    recorder = ToolEvidenceRecorder()

    recorder.record(
        journal,
        "run_command",
        {"command": "python -m pytest -q"},
        ToolResult(success=False, output="1 failed", error="退出码：1"),
    )

    evidence = journal.evidence[0]
    assert evidence.kind == "test"
    assert evidence.success is False
    assert evidence.claim == "测试命令执行失败：python -m pytest -q"
    assert "1 failed" in evidence.excerpt
    assert "退出码：1" in evidence.excerpt

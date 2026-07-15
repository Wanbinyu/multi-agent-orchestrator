"""Phase 7.3 风险分级验证与完成审计测试。"""
from __future__ import annotations

import pytest

from src.core.engineering import (
    CompletionAuditor,
    Evidence,
    RunJournalStore,
    TaskIntentClassifier,
    ToolEvidenceRecorder,
    VerificationTracker,
)
from src.core.engineering.verifier import (
    classify_test_command,
    required_checks_for_depth,
)
from src.tools.tool_result import ToolResult


@pytest.mark.parametrize(
    ("depth", "expected"),
    [
        ("none", []),
        ("targeted", ["targeted"]),
        ("standard", ["targeted", "adjacent"]),
        ("deep", ["targeted", "integration", "full", "smoke"]),
        ("continuous", ["external_mock", "external_live"]),
    ],
)
def test_verification_depth_maps_to_required_checks(depth, expected):
    assert required_checks_for_depth(depth) == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("python -m pytest -q tests/test_agent.py", "targeted"),
        ("python -m pytest -q tests/integration/test_chat.py", "integration"),
        ("python -m pytest -q tests/e2e/test_web.py", "integration"),
        ("python -m pytest -q tests/smoke/test_ui.py", "smoke"),
        ("python -m pytest -q", "full"),
        ("npm test", "full"),
        ("python --version", None),
    ],
)
def test_test_command_classification(command, expected):
    assert classify_test_command(command) == expected


def _change_journal(tmp_path):
    intent = TaskIntentClassifier().classify("修复 CLI 输出", "auto")
    return RunJournalStore(tmp_path / "runs").create(
        "session-1", "修复 CLI 输出", "auto", intent=intent
    )


def _record_command(journal, command: str, *, success: bool = True):
    result = ToolResult(
        success=success,
        output="tests passed" if success else "1 failed",
        error="" if success else "退出码：1",
    )
    params = {"command": command}
    ToolEvidenceRecorder().record(journal, "run_command", params, result)
    VerificationTracker().record(journal, "run_command", params, result)


def test_standard_change_audit_requires_implementation_targeted_and_adjacent(tmp_path):
    journal = _change_journal(tmp_path)
    auditor = CompletionAuditor()

    blocked = auditor.audit(journal, "completed")

    assert blocked.can_complete is False
    assert blocked.missing_checks == ["实现证据", "针对性验证", "相邻模块回归"]
    assert [item.status for item in journal.requirements] == [
        "unverified",
        "unverified",
        "unverified",
    ]

    journal.add_evidence(
        Evidence(
            source="tool:edit_file",
            claim="已修改文件：src/cli.py",
            kind="change",
            tool_name="edit_file",
            path="src/cli.py",
        )
    )
    _record_command(
        journal,
        "python -m pytest -q tests/test_agent.py tests/test_chat_command_output.py",
    )

    passed = auditor.audit(journal, "completed")

    assert passed.can_complete is True
    assert passed.status == "passed"
    assert passed.satisfied_checks == ["targeted", "adjacent"]
    assert all(item.status == "satisfied" for item in journal.requirements)


def test_failed_required_verification_blocks_completion(tmp_path):
    journal = _change_journal(tmp_path)
    journal.add_evidence(
        Evidence(source="tool:write_file", claim="写入", kind="change")
    )
    _record_command(journal, "pytest tests/test_agent.py", success=False)

    audit = CompletionAuditor().audit(journal, "completed")

    assert audit.can_complete is False
    assert audit.failed_checks == ["针对性验证"]
    assert "相邻模块回归" in audit.missing_checks


def test_readonly_task_does_not_require_engineering_verification(tmp_path):
    intent = TaskIntentClassifier().classify("解释 Python", "auto")
    journal = RunJournalStore(tmp_path / "runs").create(
        "session-1", "解释 Python", "auto", intent=intent
    )

    audit = CompletionAuditor().audit(journal, "completed")

    assert audit.status == "not_required"
    assert audit.can_complete is True
    assert journal.requirements == []


def test_verification_tracker_deduplicates_cached_result(tmp_path):
    journal = _change_journal(tmp_path)
    params = {"command": "pytest tests/test_agent.py"}
    result = ToolResult(success=True, output="1 passed")
    recorder = ToolEvidenceRecorder()
    tracker = VerificationTracker()
    recorder.record(journal, "run_command", params, result)

    assert tracker.record(journal, "run_command", params, result) is True
    assert tracker.record(
        journal, "run_command", params, result, cached=True
    ) is False
    assert len(journal.verification) == 1
    assert journal.verification[0].evidence_ids


def test_deep_build_requires_usage_documentation_evidence(tmp_path):
    intent = TaskIntentClassifier().classify("实现一个登录功能", "auto")
    journal = RunJournalStore(tmp_path / "runs").create(
        "session-1", "实现一个登录功能", "auto", intent=intent
    )
    journal.add_evidence(
        Evidence(
            source="tool:write_file",
            claim="写入登录功能",
            kind="change",
            path="src/login.py",
        )
    )
    for command in (
        "pytest tests/test_login.py",
        "pytest tests/integration/test_login.py",
        "python -m pytest -q",
        "pytest tests/smoke/test_login.py",
    ):
        _record_command(journal, command)

    blocked = CompletionAuditor().audit(journal, "completed")

    assert blocked.missing_checks == ["使用说明"]
    assert journal.requirements[-1].requirement == "使用说明"
    assert journal.requirements[-1].status == "unverified"

    journal.add_evidence(
        Evidence(
            source="tool:write_file",
            claim="写入使用说明",
            kind="change",
            path="docs/login.md",
        )
    )
    passed = CompletionAuditor().audit(journal, "completed")

    assert passed.can_complete is True
    assert journal.requirements[-1].status == "satisfied"


def test_verification_matrix_and_audit_survive_journal_round_trip(tmp_path):
    store = RunJournalStore(tmp_path / "runs")
    intent = TaskIntentClassifier().classify("修复 CLI 输出", "auto")
    journal = store.create(
        "session-1", "修复 CLI 输出", "auto", intent=intent
    )
    journal.add_evidence(
        Evidence(
            source="tool:edit_file",
            claim="修改 CLI",
            kind="change",
            path="src/cli.py",
        )
    )
    _record_command(
        journal,
        "pytest tests/test_agent.py tests/test_chat_command_output.py",
    )
    CompletionAuditor().audit(journal, "completed")
    store.save(journal)

    loaded = store.load(journal.run_id)

    assert loaded.version == 2
    assert loaded.audit is not None
    assert loaded.audit.status == "passed"
    assert len(loaded.verification) == 2
    assert len(loaded.requirements) == 3
    assert all(item.status == "satisfied" for item in loaded.requirements)

"""P0-1/P0-2 bounded verify-then-fix protocol."""
from __future__ import annotations

from src.core.engineering import (
    BoundedFixState,
    CompletionAuditor,
    Evidence,
    ExecutionDepthResolver,
    RunJournalStore,
    TaskIntentClassifier,
    observe_bounded_fix,
)
from src.core.engineering.models import VerificationGate
from src.tools.tool_result import ToolResult


def _result(success: bool, output: str = "", error: str = "", **metadata) -> ToolResult:
    return ToolResult(success=success, output=output, error=error, metadata=metadata)


def test_write_then_failed_verify_starts_fix_round():
    state = BoundedFixState(max_rounds=3)
    state = observe_bounded_fix(
        state, "edit_file", {"path": "app.py"}, _result(True, "已更新")
    )
    assert state.status == "needs_verification"
    state = observe_bounded_fix(
        state,
        "run_command",
        {"command": "pytest tests/test_app.py"},
        _result(False, "AssertionError: expected 3"),
    )
    assert state.status == "fixing"
    assert state.fix_round == 1
    assert "AssertionError" in state.last_failure_summary
    assert "第 1/3 轮" in state.prompt_constraint()


def test_successful_reverify_marks_passed():
    state = BoundedFixState(max_rounds=3)
    state = observe_bounded_fix(
        state, "write_file", {"path": "app.py"}, _result(True)
    )
    state = observe_bounded_fix(
        state,
        "run_command",
        {"command": "pytest tests/test_app.py"},
        _result(False, "failed"),
    )
    state = observe_bounded_fix(
        state, "edit_file", {"path": "app.py"}, _result(True)
    )
    state = observe_bounded_fix(
        state,
        "run_command",
        {"command": "pytest tests/test_app.py"},
        _result(True, "1 passed"),
    )
    assert state.status == "passed"
    assert state.fix_round == 1
    assert state.prompt_constraint() == ""


def test_hits_round_limit_blocks():
    state = BoundedFixState(max_rounds=3)
    state = observe_bounded_fix(
        state, "edit_file", {"path": "app.py"}, _result(True)
    )
    for _ in range(3):
        state = observe_bounded_fix(
            state,
            "run_command",
            {"command": "python -m pytest -q tests/test_app.py"},
            _result(False, "still failing"),
        )
        if state.status != "blocked":
            state = observe_bounded_fix(
                state, "edit_file", {"path": "app.py"}, _result(True)
            )
    assert state.status == "blocked"
    assert state.fix_round == 3
    assert "上限" in state.reason
    assert "停止继续修改" in state.prompt_constraint()


def test_cancel_stops_protocol():
    state = BoundedFixState()
    state = observe_bounded_fix(
        state, "edit_file", {"path": "a.py"}, _result(True), cancelled=True
    )
    assert state.status == "cancelled"
    later = observe_bounded_fix(
        state, "edit_file", {"path": "a.py"}, _result(True)
    )
    assert later.status == "cancelled"


def test_preflight_command_failure_does_not_consume_fix_round():
    state = BoundedFixState()
    state = observe_bounded_fix(
        state, "write_file", {"path": "app.py"}, _result(True)
    )
    state = observe_bounded_fix(
        state,
        "run_command",
        {"command": "cd missing && npm test"},
        _result(False, error="inline_cwd", error_code="inline_cwd"),
    )
    assert state.status == "needs_verification"
    assert state.fix_round == 0


def test_failed_verification_cannot_pass_completion_audit(tmp_path):
    intent = TaskIntentClassifier().classify("修复 CLI", "auto")
    journal = RunJournalStore(tmp_path / "runs").create(
        "session", "修复 CLI", "auto", intent=intent
    )
    journal.execution_depth = ExecutionDepthResolver().resolve(intent)
    journal.add_evidence(
        Evidence(source="tool:edit_file", claim="写入", kind="change", success=True)
    )
    journal.add_verification(
        VerificationGate(
            requirement="针对性验证",
            command_or_check="pytest tests/test_app.py",
            expected="命令退出码为 0",
            actual="AssertionError",
            passed=False,
            check_type="targeted",
            evidence_ids=["e1"],
        )
    )

    audit = CompletionAuditor().audit(journal, "completed")

    assert audit.can_complete is False
    assert audit.status == "blocked"
    assert "针对性验证" in " ".join(audit.failed_checks + audit.missing_checks)

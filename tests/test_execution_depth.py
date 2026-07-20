"""B5.2 deterministic execution-depth contract tests."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.agent import Agent
from src.core.engineering import (
    CompletionAuditor,
    Evidence,
    ExecutionDepthResolver,
    RunJournalStore,
    TaskIntentClassifier,
)
from src.core.session import Session


@pytest.mark.parametrize(
    ("user_input", "expected"),
    [
        ("现在上下文是多少？", "fast"),
        ("诊断 CLI 为什么失败，只分析", "standard"),
        ("修复 CLI 输出", "standard"),
        ("实现一个前后端登录项目", "deep"),
    ],
)
def test_auto_depth_matches_task_risk(user_input, expected):
    intent = TaskIntentClassifier().classify(user_input, "auto")

    decision = ExecutionDepthResolver().resolve(intent)

    assert decision.actual == expected


def test_explicit_depth_wins_when_it_does_not_weaken_safety():
    intent = TaskIntentClassifier().classify("解释这个模块", "auto")

    decision = ExecutionDepthResolver().resolve(intent, "deep")

    assert decision.requested == "deep"
    assert decision.recommended == "fast"
    assert decision.actual == "deep"
    assert decision.source == "user"
    assert decision.budget.max_workers == 4


@pytest.mark.parametrize("requested", ["fast", "standard"])
def test_high_risk_task_cannot_use_shallow_depth(requested):
    intent = TaskIntentClassifier().classify("实现一个完整网站", "auto")

    decision = ExecutionDepthResolver().resolve(intent, requested)

    assert decision.actual == "deep"
    assert decision.source == "safety_override"
    assert decision.budget.mutation_verification_floor == "deep"


def test_fast_profile_disables_workers_and_bounds_context():
    budget = ExecutionDepthResolver.profile("fast")

    assert budget.max_tool_iterations == 3
    assert budget.context_budget_ratio == 0.5
    assert budget.worker_policy == "disabled"
    assert budget.max_workers == 0
    assert budget.reviewer_policy == "disabled"


def test_explicit_fast_change_keeps_standard_verification_boundary(tmp_path):
    intent = TaskIntentClassifier().classify("修复 CLI", "auto")
    decision = ExecutionDepthResolver().resolve(intent, "fast")
    journal = RunJournalStore(tmp_path / "runs").create(
        "session", "修复 CLI", "auto", intent=intent
    )
    journal.execution_depth = decision
    journal.add_evidence(
        Evidence(source="tool:write_file", claim="写入", kind="change")
    )

    audit = CompletionAuditor().audit(journal, "completed")

    assert decision.actual == "fast"
    assert decision.source == "user"
    assert decision.budget.max_workers == 0
    assert audit.required_checks == ["targeted", "adjacent"]


def test_execution_depth_round_trips_in_run_journal(tmp_path):
    store = RunJournalStore(tmp_path / "runs")
    intent = TaskIntentClassifier().classify("修复 CLI", "auto")
    journal = store.create("session", "修复 CLI", "auto", intent=intent)
    journal.execution_depth = ExecutionDepthResolver().resolve(intent, "standard")
    store.save(journal)

    loaded = store.load(journal.run_id)

    assert loaded.version == 5
    assert loaded.execution_depth is not None
    assert loaded.execution_depth.actual == "standard"
    assert loaded.event_payload()["execution_depth"]["budget"]["max_workers"] == 2


def test_observed_multi_file_write_raises_fast_run_to_deep(tmp_path):
    session = Session(
        id="depth-session",
        created_at="2026-07-19T00:00:00+00:00",
        updated_at="2026-07-19T00:00:00+00:00",
        output_dir=str(tmp_path / "session" / "output"),
        execution_depth="fast",
    )
    agent = Agent(MagicMock(), session)
    journal = agent._start_engineering_run("现在上下文是多少？")
    assert journal.execution_depth is not None
    assert journal.execution_depth.actual == "fast"

    for path in ("src/app.py", "src/router.py"):
        journal.add_evidence(
            Evidence(
                source="tool:write_file",
                claim=f"已写入 {path}",
                kind="change",
                tool_name="write_file",
                path=path,
            )
        )
    assert agent.mutation_escalator.observe(journal) is True
    assert agent._refresh_execution_depth(journal) is True

    assert journal.effective_intent is not None
    assert journal.effective_intent.kind == "build"
    assert journal.execution_depth.actual == "deep"
    assert journal.execution_depth.source == "safety_override"
    assert agent._tool_iteration_limit(journal) == 8


def test_user_deep_strengthens_change_verification_floor(tmp_path):
    intent = TaskIntentClassifier().classify("修复 CLI", "auto")
    journal = RunJournalStore(tmp_path / "runs").create(
        "session", "修复 CLI", "auto", intent=intent
    )
    journal.execution_depth = ExecutionDepthResolver().resolve(intent, "deep")
    journal.add_evidence(
        Evidence(source="tool:write_file", claim="写入", kind="change")
    )

    audit = CompletionAuditor().audit(journal, "completed")

    assert audit.required_checks == ["targeted", "integration", "full", "smoke"]
    assert "集成测试" in audit.missing_checks
    assert "全量回归" in audit.missing_checks

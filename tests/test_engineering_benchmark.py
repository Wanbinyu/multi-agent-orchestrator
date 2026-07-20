"""B5.1 reproducible engineering benchmark contracts and harness."""
from __future__ import annotations

import json
from pathlib import Path
import re

import pytest
from pydantic import ValidationError

from src.core.engineering import (
    BenchmarkExecution,
    BenchmarkTask,
    BenchmarkVerificationContract,
    EngineeringBenchmarkHarness,
    FixtureBenchmarkStrategy,
    load_benchmark_suite,
    write_benchmark_report,
)


SUITE = Path(__file__).parents[1] / "benchmarks" / "engineering_v1" / "suite.yaml"
CATEGORIES = {
    "question",
    "diagnosis",
    "small_change",
    "build",
    "review",
    "migration",
}


class _UnexpectedMutationStrategy:
    strategy_id = "fixture-outside"
    data_kind = "synthetic_contract"

    def __init__(self):
        self.base = FixtureBenchmarkStrategy(self.strategy_id)

    def execute(self, task, workspace):
        result = self.base.execute(task, workspace)
        (workspace / "unexpected.txt").write_text("outside contract", encoding="utf-8")
        result.tool_calls += 1
        return result


class _EmptyStrategy:
    strategy_id = "fixture-empty"
    data_kind = "synthetic_contract"

    def execute(self, _task, _workspace):
        return BenchmarkExecution(status="completed", response="")


class _TimeoutStrategy:
    strategy_id = "fixture-timeout"
    data_kind = "synthetic_contract"

    def execute(self, _task, _workspace):
        return BenchmarkExecution(
            status="timeout", response="timed out", error="bounded timeout"
        )


class _ProviderLeakStrategy:
    strategy_id = "fixture-provider-leak"
    data_kind = "synthetic_contract"

    def __init__(self):
        self.base = FixtureBenchmarkStrategy(self.strategy_id)

    def execute(self, task, workspace):
        result = self.base.execute(task, workspace)
        result.provider_calls = 1
        return result


class _UnstableUsageStrategy:
    strategy_id = "fixture-unstable"
    data_kind = "synthetic_contract"

    def __init__(self):
        self.base = FixtureBenchmarkStrategy(self.strategy_id)
        self.calls = 0

    def execute(self, task, workspace):
        self.calls += 1
        result = self.base.execute(task, workspace)
        result.input_tokens += self.calls
        return result


def test_public_suite_covers_six_generated_categories_without_private_data():
    suite = load_benchmark_suite(SUITE)

    assert {task.category for task in suite.tasks} == CATEGORIES
    assert len(suite.tasks) == 6
    assert len({task.id for task in suite.tasks}) == 6
    assert all((SUITE.parent / task.project_dir).is_dir() for task in suite.tasks)

    public_files = [
        path for path in SUITE.parent.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".py", ".txt", ".ini", ".yaml", ".yml"}
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in public_files)
    assert not re.search(r"(?i)(?:api[_-]?key|secret|token)\s*[:=]\s*[^\s]+", text)
    assert not re.search(r"(?i)[a-z]:[\\/]users[\\/]", text)
    assert "G:\\" not in text


def test_fixture_strategies_share_runner_and_are_stable_across_three_trials(tmp_path):
    harness = EngineeringBenchmarkHarness(
        SUITE,
        tmp_path / "workspaces",
        [FixtureBenchmarkStrategy("fixture-single"), FixtureBenchmarkStrategy("fixture-mao")],
    )

    report = harness.run(repeats=3)

    assert report.passed is True
    assert report.provider_calls == 0
    assert len(report.results) == 36
    assert all(result.passed for result in report.results)
    assert all(result.data_kind == "synthetic_contract" for result in report.results)
    assert all(item.stable and item.trials == 3 for item in report.stability)
    assert {item.strategy_id for item in report.aggregates} == {
        "fixture-single", "fixture-mao"
    }
    assert all(item.completion_rate == 1.0 for item in report.aggregates)
    assert all(item.verification_pass_rate == 1.0 for item in report.aggregates)
    assert all(item.mis_modification_rate == 0.0 for item in report.aggregates)

    first_run = tmp_path / "workspaces" / report.run_id
    marker = first_run / "fixture-single" / "trial-1" / "question-project-entry" / "local-only.txt"
    marker.write_text("must not leak", encoding="utf-8")
    second = harness.run(repeats=1)
    second_task = (
        tmp_path / "workspaces" / second.run_id / "fixture-single" /
        "trial-1" / "question-project-entry"
    )
    assert second.passed is True
    assert not (second_task / "local-only.txt").exists()


def test_harness_can_select_one_declared_task_without_changing_acceptance(tmp_path):
    harness = EngineeringBenchmarkHarness(
        SUITE, tmp_path / "runs", [FixtureBenchmarkStrategy("fixture-one")]
    )

    report = harness.run(repeats=1, task_ids=["build-health-module"])

    assert report.passed is True
    assert report.selected_task_ids == ["build-health-module"]
    assert len(report.results) == 1
    with pytest.raises(ValueError, match="task_ids"):
        harness.run(repeats=1, task_ids=["missing-task"])


def test_harness_fail_fast_does_not_start_later_strategy(tmp_path):
    harness = EngineeringBenchmarkHarness(
        SUITE,
        tmp_path / "runs",
        [_EmptyStrategy(), FixtureBenchmarkStrategy("fixture-never-started")],
    )

    report = harness.run(
        repeats=1,
        task_ids=["build-health-module"],
        fail_fast=True,
    )

    assert report.passed is False
    assert [item.strategy_id for item in report.results] == ["fixture-empty"]


def test_reports_are_machine_readable_and_do_not_expose_workspace_paths(tmp_path):
    harness = EngineeringBenchmarkHarness(
        SUITE, tmp_path / "runs", [FixtureBenchmarkStrategy("fixture-single")]
    )
    report = harness.run(repeats=1)
    json_path = tmp_path / "reports" / "result.json"
    markdown_path = tmp_path / "reports" / "result.md"

    write_benchmark_report(
        report, json_path=json_path, markdown_path=markdown_path
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert payload["suite_id"] == "engineering-v1"
    assert payload["provider_calls"] == 0
    assert "synthetic_contract" in markdown
    assert str(tmp_path) not in json_path.read_text(encoding="utf-8")
    assert str(tmp_path) not in markdown


def test_harness_rejects_mutations_outside_task_contract(tmp_path):
    harness = EngineeringBenchmarkHarness(
        SUITE, tmp_path / "runs", [_UnexpectedMutationStrategy()]
    )

    report = harness.run(repeats=1)

    assert report.passed is False
    assert all("unexpected.txt" in result.unauthorized_mutations for result in report.results)
    assert all(any("越界修改" in issue for issue in result.issues) for result in report.results)
    assert report.aggregates[0].mis_modification_rate > 0


def test_offline_gate_rejects_provider_calls_and_unstable_metrics(tmp_path):
    leak = EngineeringBenchmarkHarness(
        SUITE, tmp_path / "leak", [_ProviderLeakStrategy()]
    ).run(repeats=1)
    unstable = EngineeringBenchmarkHarness(
        SUITE, tmp_path / "unstable", [_UnstableUsageStrategy()]
    ).run(repeats=2)

    assert leak.passed is False
    assert leak.provider_calls == 6
    assert any("Provider 调用" in issue for issue in leak.issues)
    assert unstable.passed is False
    assert any(not item.stable for item in unstable.stability)
    assert any("结果不稳定" in issue for issue in unstable.issues)


@pytest.mark.parametrize("strategy", [_EmptyStrategy(), _TimeoutStrategy()])
def test_empty_and_timeout_results_cannot_count_as_completed(tmp_path, strategy):
    harness = EngineeringBenchmarkHarness(SUITE, tmp_path / strategy.strategy_id, [strategy])

    report = harness.run(repeats=1)

    assert report.passed is False
    assert report.aggregates[0].completion_rate == 0.0
    assert all(not result.passed for result in report.results)
    if strategy.strategy_id == "fixture-empty":
        assert all("strategy 返回空响应" in result.issues for result in report.results)
    else:
        assert all(result.status == "timeout" for result in report.results)


def test_schema_rejects_absolute_traversal_and_undeclared_fixture_writes():
    base = {
        "id": "invalid-task",
        "category": "build",
        "request": "build",
        "source": "programmatic",
        "risk_level": "high",
        "project_dir": "tasks/build/project",
        "allowed_mutations": ["src/**"],
        "verification": {"commands": ["python verify.py"]},
        "offline_fixture": {
            "response": "done",
            "writes": [{"path": "outside.txt", "content": "bad"}],
        },
    }
    with pytest.raises(ValidationError, match="allowed_mutations"):
        BenchmarkTask(**base)

    base["offline_fixture"]["writes"][0]["path"] = "../outside.txt"
    with pytest.raises(ValidationError, match="不能越出"):
        BenchmarkTask(**base)

    base["offline_fixture"]["writes"][0]["path"] = "C:/private.txt"
    with pytest.raises(ValidationError, match="相对路径"):
        BenchmarkTask(**base)


def test_verification_contract_rejects_empty_commands_and_duplicate_files():
    with pytest.raises(ValidationError, match="commands 不能为空"):
        BenchmarkVerificationContract(commands=["  "])
    with pytest.raises(ValidationError, match="重复检查"):
        BenchmarkVerificationContract(
            commands=["python verify.py"],
            files=[{"path": "same.txt"}, {"path": "same.txt"}],
        )


@pytest.mark.parametrize(
    "command, message",
    [
        ("python -c 'print(1)'", "内联代码"),
        ("python ../verify.py", "父目录"),
        ("python C:/private/verify.py", "绝对路径"),
        ("powershell verify.ps1", "executable 不允许"),
    ],
)
def test_verification_contract_rejects_unsafe_commands(command, message):
    with pytest.raises(ValidationError, match=message):
        BenchmarkVerificationContract(commands=[command])

"""P0-9 daily UX synthetic contracts. Not a model ranking."""
from __future__ import annotations

from pathlib import Path

from src.core.engineering import (
    EngineeringBenchmarkHarness,
    FixtureBenchmarkStrategy,
    load_benchmark_suite,
)

SUITE = Path(__file__).parents[1] / "benchmarks" / "daily_ux_v1" / "suite.yaml"
EXPECTED_IDS = {
    "d01-explain-module",
    "d02-locate-stack",
    "d03-fix-assertion",
    "d04-rename-symbol",
    "d05-add-function-test",
    "d06-run-lint",
    "d07-readonly-review",
    "d08-git-diff-summary",
    "d09-reject-outbound-write",
    "d10-keep-constraint",
}


def test_daily_ux_suite_has_ten_tagged_contracts():
    suite = load_benchmark_suite(SUITE)
    ids = {task.id for task in suite.tasks}
    assert ids == EXPECTED_IDS
    assert all("daily_ux" in task.tags for task in suite.tasks)
    assert all((SUITE.parent / task.project_dir).is_dir() for task in suite.tasks)
    readonly = [
        task for task in suite.tasks if task.id.startswith(("d01", "d02", "d06", "d07", "d08", "d09", "d10"))
    ]
    assert all(task.allowed_mutations == [] for task in readonly)


def test_daily_ux_fixture_strategy_passes_without_provider(tmp_path):
    harness = EngineeringBenchmarkHarness(
        SUITE,
        tmp_path / "workspaces",
        [FixtureBenchmarkStrategy("fixture-fixed-single")],
    )
    report = harness.run(repeats=1, require_stable_results=False)

    assert report.passed is True, report.issues + [
        f"{item.task_id}:{item.issues}" for item in report.results if not item.passed
    ]
    assert report.provider_calls == 0
    assert len(report.results) == 10
    assert all(result.passed for result in report.results)
    assert all(result.data_kind == "synthetic_contract" for result in report.results)
    assert all(not result.unauthorized_mutations for result in report.results)
    assert {result.task_id for result in report.results} == EXPECTED_IDS

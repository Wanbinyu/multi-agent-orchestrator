"""Phase 7.4 协作契约、文件所有权与计划校验测试。"""
from __future__ import annotations

import pytest

from src.core.collaboration import (
    MAX_COLLABORATION_TASKS,
    CollaborationPlanError,
    is_write_path_allowed,
    normalize_task_contract,
    validate_collaboration_plan,
)
from src.core.config_paths import (
    resolve_providers_config_path,
    resolve_workers_config_path,
)
from src.models.schemas import Task, TaskPlan
from src.core.worker import load_workers_config


def _task(task_id: str, **kwargs) -> Task:
    return Task(
        id=task_id,
        type=kwargs.pop("type", "backend_dev"),
        title=task_id,
        input="work",
        assigned_model="glm-ark",
        **kwargs,
    )


def test_normalize_contract_fills_acceptance_and_test_mode():
    task = normalize_task_contract(_task("test", type="tester"))

    assert task.execution_mode == "verify"
    assert task.output_format
    assert task.acceptance


def test_plan_rejects_duplicate_missing_self_and_cyclic_dependencies():
    with pytest.raises(CollaborationPlanError, match="ID 重复"):
        validate_collaboration_plan(TaskPlan(tasks=[_task("a"), _task("a")]))
    with pytest.raises(CollaborationPlanError, match="不存在的依赖"):
        validate_collaboration_plan(
            TaskPlan(tasks=[_task("a", depends_on=["missing"])])
        )


def test_plan_rejects_unbounded_task_fanout():
    plan = TaskPlan(
        tasks=[_task(f"task-{index}") for index in range(MAX_COLLABORATION_TASKS + 1)]
    )

    with pytest.raises(CollaborationPlanError, match="超过上限"):
        validate_collaboration_plan(plan)
    with pytest.raises(CollaborationPlanError, match="依赖自身"):
        validate_collaboration_plan(TaskPlan(tasks=[_task("a", depends_on=["a"])]))
    with pytest.raises(CollaborationPlanError, match="依赖环"):
        validate_collaboration_plan(
            TaskPlan(tasks=[
                _task("a", depends_on=["b"]),
                _task("b", depends_on=["a"]),
            ])
        )


def test_parallel_shared_path_conflict_is_rejected_but_sequential_owner_is_allowed():
    root = "C:/project/src"
    parallel = TaskPlan(tasks=[
        _task("a", owned_paths=[root]),
        _task("b", owned_paths=["C:/project/src/api"]),
    ])
    with pytest.raises(CollaborationPlanError, match="文件所有权冲突"):
        validate_collaboration_plan(parallel)

    sequential = TaskPlan(tasks=[
        _task("a", owned_paths=[root]),
        _task("b", owned_paths=[root], depends_on=["a"]),
    ])
    validate_collaboration_plan(sequential)


def test_read_task_does_not_conflict_with_writer():
    validate_collaboration_plan(TaskPlan(tasks=[
        _task("reader", execution_mode="read", owned_paths=["C:/project"]),
        _task("writer", execution_mode="write", owned_paths=["C:/project"]),
    ]))


def test_write_path_requires_ownership_only_for_absolute_shared_path(tmp_path):
    task = _task("a", owned_paths=[str(tmp_path / "owned")])
    base = tmp_path / "isolated"

    assert is_write_path_allowed(task, "src/main.py", str(base)) is True
    assert is_write_path_allowed(task, "../escape.py", str(base)) is False
    assert is_write_path_allowed(
        task, str(tmp_path / "owned" / "main.py"), str(base)
    ) is True
    assert is_write_path_allowed(
        task, str(tmp_path / "other" / "main.py"), str(base)
    ) is False


def test_workers_config_falls_back_to_example(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    example = config_dir / "workers.yaml.example"
    example.write_text("available_workers: {}\n", encoding="utf-8")

    resolved = resolve_workers_config_path(config_dir / "workers.yaml")

    assert resolved == example


def test_workers_config_falls_back_to_packaged_template(tmp_path):
    resolved = resolve_workers_config_path(tmp_path / "missing" / "workers.yaml")

    assert resolved.name == "workers.yaml.example"
    assert resolved.is_file()
    assert "available_workers" in resolved.read_text(encoding="utf-8")


def test_providers_config_falls_back_to_example(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    example = config_dir / "providers.yaml.example"
    example.write_text("providers: {}\nmodels: {}\nmain_model: null\n", encoding="utf-8")

    resolved = resolve_providers_config_path(config_dir / "providers.yaml")

    assert resolved == example


def test_worker_loader_reads_example_when_private_config_is_missing(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "workers.yaml.example").write_text(
        "available_workers:\n  analyst:\n    tools: [read_file]\n",
        encoding="utf-8",
    )

    workers = load_workers_config(str(config_dir / "workers.yaml"))

    assert workers["analyst"]["tools"] == ["read_file"]

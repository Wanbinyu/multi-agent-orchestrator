"""Dispatcher 边界情况单元测试"""
from unittest.mock import MagicMock

import pytest

from src.core.dispatcher import Dispatcher
from src.core.worker import Worker
from src.models.schemas import ChatResponse, Task, TaskPlan, TaskResult


def _mock_worker(results_map: dict[str, TaskResult]) -> Worker:
    worker = MagicMock(spec=Worker)

    def side_effect(task: Task, output_dir: str = "output", context: dict | None = None):
        return results_map[task.id]

    worker.execute = MagicMock(side_effect=side_effect)
    return worker


def _success_result(task: Task) -> TaskResult:
    return TaskResult(
        task=task,
        success=True,
        content=f"result of {task.id}",
        response=ChatResponse(
            content=f"result of {task.id}",
            model="glm-ark",
            provider="ark",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
        ),
        files_written=[],
    )


def test_dispatch_empty_task_list():
    plan = TaskPlan(tasks=[])
    worker = MagicMock(spec=Worker)
    dispatcher = Dispatcher(worker, max_workers=4)

    results = dispatcher.dispatch(plan)

    assert results == []
    worker.execute.assert_not_called()


def test_dispatch_self_dependency_is_marked_failed():
    t1 = Task(id="t1", type="a", title="A", input="", assigned_model="glm-ark", depends_on=["t1"])
    plan = TaskPlan(tasks=[t1])

    worker = _mock_worker({"t1": _success_result(t1)})
    dispatcher = Dispatcher(worker, max_workers=4)
    results = dispatcher.dispatch(plan)

    assert len(results) == 1
    assert results[0].success is False
    assert "依赖关系无法被执行" in results[0].error
    worker.execute.assert_not_called()


def test_dispatch_cyclic_dependency_between_two_tasks():
    t1 = Task(id="t1", type="a", title="A", input="", assigned_model="glm-ark", depends_on=["t2"])
    t2 = Task(id="t2", type="b", title="B", input="", assigned_model="glm-ark", depends_on=["t1"])
    plan = TaskPlan(tasks=[t1, t2])

    worker = _mock_worker({"t1": _success_result(t1), "t2": _success_result(t2)})
    dispatcher = Dispatcher(worker, max_workers=4)
    results = dispatcher.dispatch(plan)

    assert len(results) == 2
    assert all(not r.success for r in results)
    assert all("依赖关系无法被执行" in r.error for r in results)
    worker.execute.assert_not_called()


def test_dispatch_missing_dependency_is_marked_failed():
    t1 = Task(id="t1", type="a", title="A", input="", assigned_model="glm-ark", depends_on=["missing"])
    plan = TaskPlan(tasks=[t1])

    worker = _mock_worker({"t1": _success_result(t1)})
    dispatcher = Dispatcher(worker, max_workers=4)
    results = dispatcher.dispatch(plan)

    assert len(results) == 1
    assert results[0].success is False
    assert "依赖关系无法被执行" in results[0].error
    worker.execute.assert_not_called()


def test_dispatch_cycle_with_independent_task_still_runs_independent():
    t1 = Task(id="t1", type="a", title="A", input="", assigned_model="glm-ark")
    t2 = Task(id="t2", type="b", title="B", input="", assigned_model="glm-ark", depends_on=["t3"])
    t3 = Task(id="t3", type="c", title="C", input="", assigned_model="glm-ark", depends_on=["t2"])
    plan = TaskPlan(tasks=[t1, t2, t3])

    worker = _mock_worker({
        "t1": _success_result(t1),
        "t2": _success_result(t2),
        "t3": _success_result(t3),
    })
    dispatcher = Dispatcher(worker, max_workers=4)
    results = dispatcher.dispatch(plan)

    results_by_id = {r.task.id: r for r in results}
    assert results_by_id["t1"].success is True
    assert results_by_id["t2"].success is False
    assert results_by_id["t3"].success is False
    worker.execute.assert_called_once()
    assert worker.execute.call_args[0][0].id == "t1"

"""Dispatcher 依赖调度单元测试"""
from unittest.mock import MagicMock
from contextlib import redirect_stdout
import io
import threading
import time

import pytest

from src.core.dispatcher import Dispatcher
from src.core.worker import Worker
from src.models.schemas import ChatResponse, Task, TaskPlan, TaskResult


def _mock_worker(results_map: dict[str, TaskResult]) -> Worker:
    worker = MagicMock(spec=Worker)

    def side_effect(
        task: Task,
        output_dir: str = "output",
        context: dict | None = None,
        progress_callback=None,
        memory_context: str | None = None,
    ):
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


def _failed_result(task: Task) -> TaskResult:
    return TaskResult(
        task=task,
        success=False,
        content="",
        error=f"error in {task.id}",
    )


def test_dispatch_parallel_when_no_dependencies():
    t1 = Task(id="t1", type="a", title="A", input="", assigned_model="glm-ark")
    t2 = Task(id="t2", type="b", title="B", input="", assigned_model="glm-ark")
    plan = TaskPlan(tasks=[t1, t2])

    worker = _mock_worker({"t1": _success_result(t1), "t2": _success_result(t2)})
    dispatcher = Dispatcher(worker, max_workers=4)
    results = dispatcher.dispatch(plan)

    assert len(results) == 2
    assert all(r.success for r in results)
    worker.execute.assert_any_call(t1, "output", {}, None, None)
    worker.execute.assert_any_call(t2, "output", {}, None, None)


def test_default_progress_output_is_safe_on_windows_gbk_console():
    task = Task(id="t1", type="test", title="编码验收", input="", assigned_model="glm-ark")
    worker = _mock_worker({"t1": _success_result(task)})
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="gbk", errors="strict")

    with redirect_stdout(stream):
        results = Dispatcher(worker, max_workers=1).dispatch(TaskPlan(tasks=[task]))
    stream.flush()

    assert results[0].success is True
    assert "成功" in raw.getvalue().decode("gbk")


def test_dispatch_respects_dependencies():
    t1 = Task(id="t1", type="a", title="A", input="", assigned_model="glm-ark")
    t2 = Task(id="t2", type="b", title="B", input="", assigned_model="glm-ark", depends_on=["t1"])
    plan = TaskPlan(tasks=[t1, t2])

    worker = _mock_worker({"t1": _success_result(t1), "t2": _success_result(t2)})
    dispatcher = Dispatcher(worker, max_workers=4)
    results = dispatcher.dispatch(plan)

    assert len(results) == 2
    assert all(r.success for r in results)

    # 验证 t1 的 execute 在 t2 之前被调用
    calls = worker.execute.call_args_list
    assert calls[0][0][0].id == "t1"
    assert calls[1][0][0].id == "t2"


def test_dispatch_cascades_failure():
    t1 = Task(id="t1", type="a", title="A", input="", assigned_model="glm-ark")
    t2 = Task(id="t2", type="b", title="B", input="", assigned_model="glm-ark", depends_on=["t1"])
    t3 = Task(id="t3", type="c", title="C", input="", assigned_model="glm-ark", depends_on=["t2"])
    plan = TaskPlan(tasks=[t1, t2, t3])

    worker = _mock_worker({
        "t1": _failed_result(t1),
        "t2": _success_result(t2),
        "t3": _success_result(t3),
    })
    dispatcher = Dispatcher(worker, max_workers=4)
    results = dispatcher.dispatch(plan)

    results_by_id = {r.task.id: r for r in results}
    assert results_by_id["t1"].success is False
    assert results_by_id["t2"].success is False
    assert results_by_id["t2"].error == "依赖任务 t1 失败"
    assert results_by_id["t3"].success is False
    assert results_by_id["t3"].error == "依赖任务 t2 失败"

    # t2 和 t3 不应真正执行
    assert worker.execute.call_count == 1
    assert worker.execute.call_args[0][0].id == "t1"


def test_dispatch_passes_dependency_context_to_worker():
    t1 = Task(id="t1", type="a", title="A", input="", assigned_model="glm-ark")
    t2 = Task(id="t2", type="b", title="B", input="基于 {{t1.output}} 继续", assigned_model="glm-ark", depends_on=["t1"])
    plan = TaskPlan(tasks=[t1, t2])

    worker = _mock_worker({"t1": _success_result(t1), "t2": _success_result(t2)})
    dispatcher = Dispatcher(worker, max_workers=4)
    dispatcher.dispatch(plan)

    calls = worker.execute.call_args_list
    # t1 无依赖，context 为空
    assert calls[0].args[2] == {}
    # t2 依赖 t1，context 应包含 t1 的输出
    assert calls[1].args[2] == {"t1": "result of t1"}


def test_dispatch_mixed_dependency_chains():
    # t1 -> t2, t3 独立
    t1 = Task(id="t1", type="a", title="A", input="", assigned_model="glm-ark")
    t2 = Task(id="t2", type="b", title="B", input="", assigned_model="glm-ark", depends_on=["t1"])
    t3 = Task(id="t3", type="c", title="C", input="", assigned_model="glm-ark")
    plan = TaskPlan(tasks=[t1, t2, t3])

    worker = _mock_worker({
        "t1": _success_result(t1),
        "t2": _success_result(t2),
        "t3": _success_result(t3),
    })
    dispatcher = Dispatcher(worker, max_workers=4)
    results = dispatcher.dispatch(plan)

    assert len(results) == 3
    assert all(r.success for r in results)

    # t3 可以和 t1 并行，t2 必须在 t1 后
    calls = worker.execute.call_args_list
    id_order = [call[0][0].id for call in calls]
    assert id_order.index("t2") > id_order.index("t1")


def test_dispatch_retries_only_transiently_failed_task():
    t1 = Task(
        id="t1", type="a", title="A", input="", assigned_model="glm-ark",
        max_retries=1,
    )
    t2 = Task(id="t2", type="b", title="B", input="", assigned_model="glm-ark")
    worker = MagicMock(spec=Worker)
    attempts = {"t1": 0, "t2": 0}

    def execute(task, *_args, **_kwargs):
        attempts[task.id] += 1
        if task.id == "t1" and attempts[task.id] == 1:
            return TaskResult(
                task=task,
                success=False,
                content="",
                error="connection timeout",
                tool_calls=[{
                    "tool": "run_command",
                    "params": {"command": "pytest tests/test_a.py"},
                    "success": False,
                    "output": "1 failed",
                    "error": "退出码：1",
                }],
            )
        return _success_result(task)

    worker.execute.side_effect = execute
    events = []
    results = Dispatcher(worker).dispatch(
        TaskPlan(tasks=[t1, t2]),
        progress_callback=lambda event, payload: events.append((event, payload)),
    )

    by_id = {result.task.id: result for result in results}
    assert attempts == {"t1": 2, "t2": 1}
    assert by_id["t1"].success is True
    assert by_id["t1"].attempts == 2
    assert by_id["t1"].retry_errors == ["connection timeout"]
    assert by_id["t1"].tool_calls[0]["success"] is False
    retry = next(payload for event, payload in events if event == "task_retry")
    assert retry["id"] == "t1"
    assert retry["attempt"] == 2


def test_dispatch_does_not_retry_deterministic_failure():
    task = Task(
        id="t1", type="a", title="A", input="", assigned_model="glm-ark",
        max_retries=3,
    )
    worker = _mock_worker({"t1": _failed_result(task)})

    result = Dispatcher(worker).dispatch(TaskPlan(tasks=[task]))[0]

    assert result.success is False
    assert result.attempts == 1
    worker.execute.assert_called_once()


def test_non_parallel_safe_tasks_execute_exclusively():
    tasks = [
        Task(
            id=f"t{index}", type="a", title=str(index), input="",
            assigned_model="glm-ark", parallel_safe=False,
        )
        for index in range(3)
    ]
    worker = MagicMock(spec=Worker)
    lock = threading.Lock()
    active = 0
    max_active = 0

    def execute(task, *_args, **_kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return _success_result(task)

    worker.execute.side_effect = execute
    results = Dispatcher(worker, max_workers=3).dispatch(TaskPlan(tasks=tasks))

    assert all(result.success for result in results)
    assert max_active == 1


def test_dispatch_rejects_parallel_owned_path_conflict_without_running_worker():
    tasks = [
        Task(
            id="a", type="a", title="A", input="", assigned_model="glm-ark",
            owned_paths=["C:/project/src"],
        ),
        Task(
            id="b", type="b", title="B", input="", assigned_model="glm-ark",
            owned_paths=["C:/project/src/api"],
        ),
    ]
    worker = MagicMock(spec=Worker)
    events = []

    results = Dispatcher(worker).dispatch(
        TaskPlan(tasks=tasks),
        progress_callback=lambda event, payload: events.append((event, payload)),
    )

    assert all(not result.success for result in results)
    assert all("计划边界冲突" in result.error for result in results)
    assert [event for event, _payload in events] == ["task_complete", "task_complete"]
    worker.execute.assert_not_called()


def test_dispatch_rejects_duplicate_task_ids_without_running_worker():
    tasks = [
        Task(id="same", type="a", title="A", input="", assigned_model="glm-ark"),
        Task(id="same", type="b", title="B", input="", assigned_model="glm-ark"),
    ]
    worker = MagicMock(spec=Worker)

    results = Dispatcher(worker).dispatch(TaskPlan(tasks=tasks))

    assert len(results) == 2
    assert all("ID 重复" in result.error for result in results)
    worker.execute.assert_not_called()

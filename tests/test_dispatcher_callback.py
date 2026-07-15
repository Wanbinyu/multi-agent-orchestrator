"""Dispatcher progress_callback 单元测试"""
from __future__ import annotations

from unittest.mock import MagicMock

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
        files_written=[f"output/{task.id}.txt"],
        tool_calls=[{
            "tool": "write_file",
            "params": {"path": f"{task.id}.txt"},
            "success": True,
            "output": "ok",
            "error": "",
        }],
        acceptance_evidence=[f"写入文件：output/{task.id}.txt"],
    )


def test_dispatch_emits_progress_events():
    t1 = Task(id="t1", type="a", title="A", input="", assigned_model="glm-ark")
    t2 = Task(id="t2", type="b", title="B", input="", assigned_model="glm-ark")
    plan = TaskPlan(tasks=[t1, t2])

    worker = _mock_worker({"t1": _success_result(t1), "t2": _success_result(t2)})
    dispatcher = Dispatcher(worker, max_workers=4)

    events = []

    def callback(event_type: str, payload: dict):
        events.append((event_type, payload))

    dispatcher.dispatch(plan, output_dir="output", progress_callback=callback)

    start_events = [e for e in events if e[0] == "task_start"]
    complete_events = [e for e in events if e[0] == "task_complete"]

    assert len(start_events) == 2
    assert len(complete_events) == 2

    start_ids = {e[1]["id"] for e in start_events}
    complete_ids = {e[1]["id"] for e in complete_events}
    assert start_ids == {"t1", "t2"}
    assert complete_ids == {"t1", "t2"}

    t1_complete = next(e[1] for e in complete_events if e[1]["id"] == "t1")
    assert t1_complete["success"] is True
    assert t1_complete["files_written"] == ["output/t1.txt"]
    assert t1_complete["content"] == "result of t1"
    assert t1_complete["tool_calls"][0]["tool"] == "write_file"
    assert t1_complete["acceptance_evidence"]


def test_dispatch_emits_failure_progress():
    t1 = Task(id="t1", type="a", title="A", input="", assigned_model="glm-ark")
    t2 = Task(id="t2", type="b", title="B", input="", assigned_model="glm-ark", depends_on=["t1"])
    plan = TaskPlan(tasks=[t1, t2])

    failed = TaskResult(
        task=t1,
        success=False,
        content="",
        error="boom",
    )
    worker = _mock_worker({"t1": failed})
    dispatcher = Dispatcher(worker, max_workers=4)

    events = []

    def callback(event_type: str, payload: dict):
        events.append((event_type, payload))

    dispatcher.dispatch(plan, output_dir="output", progress_callback=callback)

    complete_events = [e for e in events if e[0] == "task_complete"]
    t2_complete = next(e[1] for e in complete_events if e[1]["id"] == "t2")
    assert t2_complete["success"] is False
    assert "依赖任务 t1 失败" in t2_complete["error"]

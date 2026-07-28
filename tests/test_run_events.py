"""U4.1 RunEventWriter 单元测试。"""
from __future__ import annotations

import io
import json
import threading

import pytest

from src.core.run_events import RunEventWriter, build_usage


def test_invalid_format_rejected():
    with pytest.raises(ValueError):
        RunEventWriter("yaml")


def test_streaming_json_emits_jsonl_lines():
    buf = io.StringIO()
    w = RunEventWriter("streaming-json", out=buf, run_id="run-1")
    w.emit("run", {"request": "hi"})
    w.emit("plan", {"tasks": 2})
    w.emit("end", {"exit_code": 0})
    w.finish({"status": "ok"})

    lines = [ln for ln in buf.getvalue().splitlines() if ln]
    assert len(lines) == 3  # finish 在 streaming 模式不额外输出
    objs = [json.loads(ln) for ln in lines]
    assert [o["type"] for o in objs] == ["run", "plan", "end"]
    for o in objs:
        assert set(o) == {"type", "ts", "run_id", "data"}
        assert isinstance(o["ts"], str) and o["ts"]
        assert o["run_id"] == "run-1"
    assert objs[0]["data"] == {"request": "hi"}
    assert objs[2]["data"] == {"exit_code": 0}


def test_json_collects_and_finish_single_object():
    buf = io.StringIO()
    w = RunEventWriter("json", out=buf)
    w.emit("run", {"request": "hi"})
    w.emit("task_complete", {"task_id": "t1", "success": True})
    w.emit("end", {"exit_code": 0})
    w.finish({"status": "ok", "exit_code": 0})

    payload = json.loads(buf.getvalue().strip())
    assert payload["run"] == {"status": "ok", "exit_code": 0}
    assert [e["type"] for e in payload["events"]] == ["run", "task_complete", "end"]
    assert payload["events"][-1]["type"] == "end"


def test_plain_noop():
    buf = io.StringIO()
    w = RunEventWriter("plain", out=buf)
    w.emit("run", {"x": 1})
    w.emit("end", {"exit_code": 0})
    w.finish({"status": "ok"})
    assert buf.getvalue() == ""


def test_end_is_last_emits_after_end_dropped():
    buf = io.StringIO()
    w = RunEventWriter("streaming-json", out=buf)
    w.emit("run", {})
    w.emit("end", {"exit_code": 0})
    w.emit("tool", {"tool": "late"})  # 应被丢弃
    w.finish()
    objs = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln]
    assert [o["type"] for o in objs] == ["run", "end"]
    assert w.ended is True


def test_finish_blocks_emit():
    buf = io.StringIO()
    w = RunEventWriter("json", out=buf)
    w.emit("run", {})
    w.finish({"status": "ok"})
    w.emit("end", {"exit_code": 0})  # finish 后丢弃
    payload = json.loads(buf.getvalue().strip())
    assert [e["type"] for e in payload["events"]] == ["run"]
    assert w.finished is True


def test_finish_idempotent():
    buf = io.StringIO()
    w = RunEventWriter("json", out=buf)
    w.emit("run", {})
    w.finish({"status": "ok"})
    w.finish({"status": "again"})
    # 只输出一次
    lines = [ln for ln in buf.getvalue().splitlines() if ln]
    assert len(lines) == 1
    assert json.loads(lines[0])["run"] == {"status": "ok"}


def test_envelope_shape():
    buf = io.StringIO()
    w = RunEventWriter("streaming-json", out=buf)
    w.emit("model", {"task_id": "t1", "model": "glm-ark", "input_tokens": 10})
    obj = json.loads(buf.getvalue().strip())
    assert set(obj) == {"type", "ts", "run_id", "data"}
    assert obj["type"] == "model"
    assert obj["data"]["model"] == "glm-ark"


def test_elapsed_ms_nonnegative():
    w = RunEventWriter("plain")
    assert w.elapsed_ms() >= 0


def test_jsonl_writer_keeps_threaded_events_atomic_and_in_one_run():
    buf = io.StringIO()
    writer = RunEventWriter("streaming-json", out=buf, run_id="threaded-run")

    def emit(index: int) -> None:
        writer.emit("tool", {"index": index})

    threads = [threading.Thread(target=emit, args=(index,)) for index in range(24)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    writer.emit("end", {"status": "completed", "exit_code": 0})
    writer.finish({"status": "completed", "exit_code": 0})

    events = [json.loads(line) for line in buf.getvalue().splitlines() if line]
    assert len(events) == 25
    assert {event["run_id"] for event in events} == {"threaded-run"}
    assert {event["data"]["index"] for event in events[:-1]} == set(range(24))
    assert events[-1]["type"] == "end"


def test_cancellation_event_has_a_stable_envelope():
    buf = io.StringIO()
    writer = RunEventWriter("json", out=buf, run_id="cancelled-run")
    writer.emit("cancel", {"reason": "approval_denied"})
    writer.emit("end", {"status": "cancelled", "exit_code": 0})
    writer.finish({"status": "cancelled", "exit_code": 0})

    payload = json.loads(buf.getvalue())
    assert [event["type"] for event in payload["events"]] == ["cancel", "end"]
    assert payload["events"][0]["run_id"] == "cancelled-run"


def test_build_usage_marks_unknown_cost_and_aggregates_models_and_roles():
    usage = build_usage({
        "total_input_tokens": 30,
        "total_output_tokens": 12,
        "total_cost_usd": 0.0,
        "calls": [
            {
                "model": "model-a",
                "task_id": "task-a",
                "input_tokens": 20,
                "output_tokens": 8,
                "cost_usd": 0.0,
            },
            {
                "model": "model-b",
                "task_id": "task-b",
                "input_tokens": 10,
                "output_tokens": 4,
                "cost_usd": 0.0,
            },
        ],
    })

    assert usage["total_cost_usd"] is None
    assert usage["cost_is_partial"] is True
    assert usage["usage_is_incomplete"] is False
    assert [item["key"] for item in usage["by_model"]] == ["model-a", "model-b"]
    assert [item["key"] for item in usage["by_role"]] == ["task-a", "task-b"]


def test_build_usage_keeps_known_partial_total_cost():
    usage = build_usage({
        "total_input_tokens": 15,
        "total_output_tokens": 6,
        "total_cost_usd": 0.25,
        "calls": [
            {
                "model": "model-a",
                "task_id": "task-a",
                "input_tokens": 10,
                "output_tokens": 4,
                "cost_usd": 0.25,
            },
            {
                "model": "model-b",
                "task_id": "task-b",
                "input_tokens": 5,
                "output_tokens": 2,
                "cost_usd": 0.0,
            },
        ],
    })

    assert usage["total_cost_usd"] == 0.25
    assert usage["cost_is_partial"] is True
    assert usage["by_model"][1]["cost_known"] is False

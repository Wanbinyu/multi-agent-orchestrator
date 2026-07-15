"""Agent 流式对话单元测试"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from src.core.agent import Agent
from src.core.engineering import RunJournalStore
from src.core.session import Session
from src.models.schemas import ChatStreamEvent, StreamChunk


def _make_session(tmp_path) -> Session:
    return Session(
        id="test-session",
        title="test",
        created_at="2026-07-12T00:00:00+00:00",
        updated_at="2026-07-12T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
    )


def _async_chunks(*chunks: StreamChunk):
    async def _gen():
        for c in chunks:
            yield c

    return _gen()


def _collect_events(agent: Agent, text: str) -> list[ChatStreamEvent]:
    async def _run():
        return [e async for e in agent.run_turn_stream(text)]

    return asyncio.run(_run())


def test_run_turn_stream_no_tools(tmp_path):
    session = _make_session(tmp_path)
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content="你好"),
        StreamChunk(type="delta", content="！"),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5, cost_usd=0.0001),
    )

    agent = Agent(gateway, session)
    events = _collect_events(agent, "Hi")

    deltas = [e.delta for e in events if e.type == "delta"]
    done = [e for e in events if e.type == "done"][0]

    assert "".join(deltas) == "你好！"
    assert done.input_tokens == 10
    assert done.output_tokens == 5
    assert done.cost_usd == pytest.approx(0.0001)
    assert session.messages[-1].role == "assistant"
    assert session.messages[-1].content == "你好！"
    assert [event.type for event in events if event.type.startswith("engineering_")] == [
        "engineering_start",
        "engineering_complete",
    ]
    run_id = next(event.engineering["run_id"] for event in events if event.type == "engineering_start")
    journal = RunJournalStore.from_output_dir(session.output_dir).load(run_id)
    assert journal.status == "completed"
    assert journal.metrics["output_tokens"] == 5


def test_run_turn_stream_failure_emits_failed_engineering_event(tmp_path):
    session = _make_session(tmp_path)
    gateway = MagicMock()

    async def _broken_stream(*_args, **_kwargs):
        raise RuntimeError("stream down")
        yield  # pragma: no cover

    gateway.chat_with_main_model_stream.side_effect = _broken_stream
    agent = Agent(gateway, session)
    events = []

    async def _run():
        async for event in agent.run_turn_stream("只分析，不修改文件"):
            events.append(event)

    with pytest.raises(RuntimeError, match="stream down"):
        asyncio.run(_run())

    engineering = [event.engineering for event in events if event.type.startswith("engineering_")]
    assert [item["status"] for item in engineering] == ["running", "failed"]
    journal = RunJournalStore.from_output_dir(session.output_dir).latest()
    assert journal is not None
    assert journal.status == "failed"


def test_run_turn_stream_with_tool(tmp_path):
    session = _make_session(tmp_path)
    target = tmp_path / "output" / "hello.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("Python 是一门优雅的编程语言。", encoding="utf-8")

    gateway = MagicMock()
    gateway.chat_with_main_model_stream.side_effect = [
        _async_chunks(
            StreamChunk(type="delta", content='```tool:read_file\n{"path": "hello.txt"}\n```'),
            StreamChunk(type="usage", input_tokens=10, output_tokens=5, cost_usd=0.0001),
        ),
        _async_chunks(
            StreamChunk(type="delta", content="Python 是一门优雅的编程语言。"),
            StreamChunk(type="usage", input_tokens=8, output_tokens=4, cost_usd=0.00008),
        ),
    ]

    agent = Agent(gateway, session)
    events = _collect_events(agent, "总结 hello.txt")

    done = [e for e in events if e.type == "done"][0]
    tool_start = [e for e in events if e.type == "tool_start"]
    tool_complete = [e for e in events if e.type == "tool_complete"]
    assert len(tool_start) == 1
    assert tool_start[0].tool_call["tool"] == "read_file"
    assert len(tool_complete) == 1
    assert tool_complete[0].tool_call["success"] is True
    assert done.tool_calls
    assert done.tool_calls[0]["tool"] == "read_file"
    assert done.tool_calls[0]["success"] is True
    assert "Python 是一门优雅的编程语言" in done.assistant_message
    assert done.input_tokens == 18
    assert done.output_tokens == 9
    assert done.cost_usd == pytest.approx(0.00018)


def test_run_turn_stream_respects_max_iterations(tmp_path):
    session = _make_session(tmp_path)
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.side_effect = lambda *args, **kwargs: _async_chunks(
        StreamChunk(type="delta", content='```tool:read_file\n{"path": "a.txt"}\n```'),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5, cost_usd=0.0001),
    )

    agent = Agent(gateway, session, max_tool_iterations=2)
    _collect_events(agent, "测试")

    # 初始调用 + 2 次工具循环 + 1 次最终总结 = 4 次模型调用
    assert gateway.chat_with_main_model_stream.call_count == 4


def test_run_turn_stream_writes_response_md(tmp_path):
    session = _make_session(tmp_path)
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content="这是最终回答。"),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5, cost_usd=0.0001),
    )

    agent = Agent(gateway, session)
    events = _collect_events(agent, "问题")

    done = [e for e in events if e.type == "done"][0]
    assert done.files_written
    assert any("response.md" in f for f in done.files_written)


def test_run_turn_stream_reuses_duplicate_read_in_same_turn(tmp_path):
    session = _make_session(tmp_path)
    target = tmp_path / "output" / "same.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("cached content", encoding="utf-8")
    duplicate_calls = (
        '```tool:read_file\n{"path":"same.txt"}\n```\n'
        '```tool:read_file\n{"path":"same.txt"}\n```'
    )
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.side_effect = [
        _async_chunks(StreamChunk(type="delta", content=duplicate_calls)),
        _async_chunks(StreamChunk(type="delta", content="完成")),
    ]

    events = _collect_events(Agent(gateway, session), "读取两次")
    done = next(event for event in events if event.type == "done")

    assert [call["cached"] for call in done.tool_calls] == [False, True]
    starts = [event.tool_call for event in events if event.type == "tool_start"]
    assert [call["cached"] for call in starts] == [False, True]


def test_analysis_only_turn_enforces_unique_read_file_limit(tmp_path):
    session = _make_session(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    calls = []
    for index in range(14):
        (output_dir / f"file-{index}.txt").write_text(str(index), encoding="utf-8")
        calls.append(
            f'```tool:read_file\n{{"path":"file-{index}.txt"}}\n```'
        )

    gateway = MagicMock()
    gateway.chat_with_main_model_stream.side_effect = [
        _async_chunks(StreamChunk(type="delta", content="\n".join(calls))),
        _async_chunks(StreamChunk(type="delta", content="完整方案")),
    ]

    events = _collect_events(Agent(gateway, session), "分析项目，只做方案")
    done = next(event for event in events if event.type == "done")

    assert len([event for event in events if event.type == "tool_start"]) == 12
    assert sum(call.get("skipped", False) for call in done.tool_calls) == 2
    assert all("12 个不同文件上限" in call["output"] for call in done.tool_calls[-2:])


def test_analysis_only_turn_rewrites_overlong_final_answer(tmp_path):
    session = _make_session(tmp_path)
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.side_effect = [
        _async_chunks(
            StreamChunk(type="delta", content="长" * 6001),
            StreamChunk(type="usage", input_tokens=100, output_tokens=100),
        ),
        _async_chunks(
            StreamChunk(type="delta", content="完整精简方案"),
            StreamChunk(type="usage", input_tokens=50, output_tokens=10),
        ),
    ]

    events = _collect_events(Agent(gateway, session), "分析项目，只做方案")
    done = next(event for event in events if event.type == "done")

    assert gateway.chat_with_main_model_stream.call_count == 2
    assert gateway.chat_with_main_model_stream.call_args.kwargs.get("tools") is None
    assert done.assistant_message == "完整精简方案"
    assert done.input_tokens == 150
    assert done.output_tokens == 110

"""Agent 流式对话单元测试"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from src.core.agent import Agent
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

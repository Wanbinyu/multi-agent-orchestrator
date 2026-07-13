"""Agent 权限模式单元测试"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from src.core.agent import Agent
from src.core.session import Session
from src.models.schemas import ChatStreamEvent, StreamChunk


def _make_session(tmp_path, approval_mode: str = "auto") -> Session:
    return Session(
        id="test-session",
        title="test",
        created_at="2026-07-12T00:00:00+00:00",
        updated_at="2026-07-12T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
        approval_mode=approval_mode,
    )


def _async_chunks(*chunks: StreamChunk):
    async def _gen():
        for c in chunks:
            yield c

    return _gen()


def test_readonly_denies_tool_call(tmp_path):
    """readonly 模式下工具调用应被拒绝，且不产生权限请求"""
    session = _make_session(tmp_path, approval_mode="readonly")
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content='```tool:write_file\n{"path": "foo.txt", "content": "hello"}\n```'),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5, cost_usd=0.0001),
    )

    agent = Agent(gateway, session)

    async def _run():
        events = [e async for e in agent.run_turn_stream("写文件")]
        return events

    events = asyncio.run(_run())

    permission_events = [e for e in events if e.type == "permission_request"]
    done = [e for e in events if e.type == "done"][0]

    assert not permission_events
    assert done.tool_calls
    assert done.tool_calls[0]["tool"] == "write_file"
    assert done.tool_calls[0]["success"] is False
    assert "只读模式" in done.tool_calls[0]["error"]
    assert not done.files_written


def test_approve_yields_permission_request_and_executes_when_approved(tmp_path):
    """approve 模式下应产出权限请求；用户批准后真正执行工具"""
    session = _make_session(tmp_path, approval_mode="approve")
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content='```tool:write_file\n{"path": "approved.txt", "content": "ok"}\n```'),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5, cost_usd=0.0001),
    )

    agent = Agent(gateway, session)

    async def _run():
        events: list[ChatStreamEvent] = []
        async for event in agent.run_turn_stream("写文件"):
            events.append(event)
            if event.type == "permission_request":
                req_id = event.permission_request["request_id"]
                # 在下一事件循环迭代中批准
                asyncio.get_event_loop().call_soon(
                    agent.respond_to_permission, req_id, True
                )
        return events

    events = asyncio.run(_run())

    permission_events = [e for e in events if e.type == "permission_request"]
    done = [e for e in events if e.type == "done"][0]

    assert len(permission_events) == 1
    req = permission_events[0].permission_request
    assert req["tool"] == "write_file"
    assert req["params"]["path"] == "approved.txt"

    assert done.tool_calls[0]["success"] is True
    assert any("approved.txt" in f for f in done.files_written)

    # 文件确实落盘
    written = tmp_path / "output" / "approved.txt"
    assert written.exists()
    assert written.read_text(encoding="utf-8") == "ok"


def test_approve_denies_tool_when_rejected(tmp_path):
    """approve 模式下用户拒绝后工具不应执行"""
    session = _make_session(tmp_path, approval_mode="approve")
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content='```tool:write_file\n{"path": "rejected.txt", "content": "no"}\n```'),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5, cost_usd=0.0001),
    )

    agent = Agent(gateway, session)

    async def _run():
        events: list[ChatStreamEvent] = []
        async for event in agent.run_turn_stream("写文件"):
            events.append(event)
            if event.type == "permission_request":
                req_id = event.permission_request["request_id"]
                asyncio.get_event_loop().call_soon(
                    agent.respond_to_permission, req_id, False
                )
        return events

    events = asyncio.run(_run())

    done = [e for e in events if e.type == "done"][0]
    assert done.tool_calls[0]["success"] is False
    assert "拒绝" in done.tool_calls[0]["error"]
    assert not done.files_written

    written = tmp_path / "output" / "rejected.txt"
    assert not written.exists()


def test_auto_executes_without_permission_event(tmp_path):
    """auto 模式下应直接执行工具，不产生权限请求，并自动落盘 response.md"""
    session = _make_session(tmp_path, approval_mode="auto")
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content="这是最终回答。"),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5, cost_usd=0.0001),
    )

    agent = Agent(gateway, session)

    events = asyncio.run(_collect_events(agent, "问题"))
    done = [e for e in events if e.type == "done"][0]

    assert not any(e.type == "permission_request" for e in events)
    assert done.files_written
    assert any("response.md" in f for f in done.files_written)


def test_approve_does_not_auto_write_response_md(tmp_path):
    """approve 模式下没有明确批准的 write_file 时，不应自动写 response.md"""
    session = _make_session(tmp_path, approval_mode="approve")
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content="这是最终回答。"),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5, cost_usd=0.0001),
    )

    agent = Agent(gateway, session)
    events = asyncio.run(_collect_events(agent, "问题"))
    done = [e for e in events if e.type == "done"][0]

    assert not done.files_written


async def _collect_events(agent: Agent, text: str) -> list[ChatStreamEvent]:
    return [e async for e in agent.run_turn_stream(text)]

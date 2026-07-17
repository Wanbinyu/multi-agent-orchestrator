"""空响应守卫回归测试：空文本 + 无工具调用不得静默 completed。"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from src.core.agent import Agent
from src.core.engineering import RunJournalStore
from src.core.session import Session
from src.models.schemas import ChatStreamEvent, StreamChunk


def _make_session(tmp_path) -> Session:
    return Session(
        id="test-session",
        title="test",
        created_at="2026-07-17T00:00:00+00:00",
        updated_at="2026-07-17T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
    )


def _make_gateway() -> MagicMock:
    gateway = MagicMock()
    gateway.main_model = "test-model"
    gateway.get_model_config.side_effect = Exception("unknown model")
    return gateway


def _async_chunks(*chunks: StreamChunk):
    async def _gen():
        for c in chunks:
            yield c

    return _gen()


def _collect_events(agent: Agent, text: str) -> list[ChatStreamEvent]:
    async def _run():
        return [e async for e in agent.run_turn_stream(text)]

    return asyncio.run(_run())


def _latest_journal(session: Session):
    store = RunJournalStore.from_output_dir(session.output_dir)
    return store.latest()


def test_sync_empty_response_fails_instead_of_completing(tmp_path):
    session = _make_session(tmp_path)
    gateway = _make_gateway()
    gateway.chat_with_main_model.return_value = MagicMock(
        content="",
        content_blocks=[],
        provider_payload=[],
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
    )

    agent = Agent(gateway, session)
    result = agent.run_turn("你好")

    assert "模型无响应或返回空内容" in result.assistant_message
    journal = _latest_journal(session)
    assert journal.status == "failed"
    assert journal.residual_risks == ["模型无响应或返回空内容"]
    # 空 assistant 消息不得写入会话历史，避免污染后续请求
    assert session.messages[-1].role == "user"


def test_stream_zero_token_empty_response_fails(tmp_path):
    session = _make_session(tmp_path)
    gateway = _make_gateway()
    gateway.chat_with_main_model_stream.return_value = _async_chunks()

    agent = Agent(gateway, session)
    events = _collect_events(agent, "你好")

    errors = [e for e in events if e.type == "error"]
    assert errors, "应产生错误事件"
    assert "0 token" in errors[0].error
    assert "模型 ID" in errors[0].error
    journal = _latest_journal(session)
    assert journal.status == "failed"
    assert journal.residual_risks == ["模型无响应或返回空内容（0 token）"]
    assert session.messages[-1].role == "user"


def test_stream_tokens_without_text_still_fails_with_parse_reason(tmp_path):
    session = _make_session(tmp_path)
    gateway = _make_gateway()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="usage", input_tokens=10, output_tokens=5),
    )

    agent = Agent(gateway, session)
    events = _collect_events(agent, "你好")

    errors = [e for e in events if e.type == "error"]
    assert errors
    assert "未返回可解析文本" in errors[0].error
    journal = _latest_journal(session)
    assert journal.status == "failed"
    assert journal.residual_risks == ["模型未返回可解析文本"]


def test_stream_normal_text_still_completes(tmp_path):
    session = _make_session(tmp_path)
    gateway = _make_gateway()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content="你好！"),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5),
    )

    agent = Agent(gateway, session)
    events = _collect_events(agent, "Hi")

    assert not [e for e in events if e.type == "error"]
    assert session.messages[-1].role == "assistant"
    assert session.messages[-1].content == "你好！"
    journal = _latest_journal(session)
    assert journal.status == "completed"

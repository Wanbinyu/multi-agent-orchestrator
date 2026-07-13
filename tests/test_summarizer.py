"""会话自动总结单元测试"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.core.memory import MemoryStore
from src.core.session import Session
from src.core.summarizer import SessionSummarizer
from src.models.schemas import ChatMessage, ChatResponse


def _make_session(tmp_path: Path) -> Session:
    return Session(
        id="test-session",
        title="test",
        created_at="2026-07-12T00:00:00+00:00",
        updated_at="2026-07-12T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
    )


def _mock_gateway(content: str) -> MagicMock:
    gateway = MagicMock()
    gateway.chat_with_main_model.return_value = ChatResponse(
        content=content,
        model="main",
        provider="test",
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.0001,
    )
    return gateway


@pytest.fixture
def memory_store(tmp_path: Path) -> MemoryStore:
    config_path = tmp_path / "memory_config.yaml"
    config_path.write_text(
        f"enabled: true\nstorage_path: {tmp_path / 'memory'}\n", encoding="utf-8"
    )
    return MemoryStore(config_path=str(config_path))


def test_summarizer_extracts_and_saves_entries(tmp_path, memory_store: MemoryStore):
    session = _make_session(tmp_path)
    session.add_message("user", "请用中文回复")
    session.add_message("assistant", "好的，我会用中文回复。")

    gateway = _mock_gateway(
        "[preference] 用户要求用中文回复\n[decision] 回复语言使用中文"
    )
    summarizer = SessionSummarizer(gateway, memory_store)
    ids = summarizer.summarize(session)

    assert len(ids) == 2
    assert gateway.chat_with_main_model.called
    entries = memory_store.list()
    assert len(entries) == 2
    assert any(e.category == "preference" for e in entries)
    assert any(e.category == "decision" for e in entries)
    assert all("auto_summary" in e.tags for e in entries)


def test_summarizer_skips_empty_output(tmp_path, memory_store: MemoryStore):
    session = _make_session(tmp_path)
    session.add_message("user", "你好")

    gateway = _mock_gateway("无")
    summarizer = SessionSummarizer(gateway, memory_store)
    ids = summarizer.summarize(session)

    assert ids == []
    assert memory_store.list() == []


def test_summarizer_disabled_store(tmp_path, memory_store: MemoryStore):
    session = _make_session(tmp_path)
    session.add_message("user", "你好")
    memory_store.config.enabled = False

    gateway = _mock_gateway("[preference] 中文")
    summarizer = SessionSummarizer(gateway, memory_store)
    ids = summarizer.summarize(session)

    assert ids == []
    gateway.chat_with_main_model.assert_not_called()


def test_summarizer_ignores_system_and_tool_messages(tmp_path, memory_store: MemoryStore):
    session = _make_session(tmp_path)
    session.messages.append(ChatMessage(role="system", content="系统提示"))
    session.add_message("user", "你好")

    gateway = _mock_gateway("[preference] 中文")
    summarizer = SessionSummarizer(gateway, memory_store)
    summarizer.summarize(session)

    transcript = gateway.chat_with_main_model.call_args.kwargs["messages"][1].content
    assert "系统提示" not in transcript


def test_summarizer_parse_filters_invalid_lines(tmp_path, memory_store: MemoryStore):
    session = _make_session(tmp_path)
    session.add_message("user", "你好")

    gateway = _mock_gateway(
        "[preference] 中文\n[invalid] 不应保存\n无标签行\n[decision] 使用 FastAPI"
    )
    summarizer = SessionSummarizer(gateway, memory_store)
    ids = summarizer.summarize(session)

    assert len(ids) == 2
    assert {e.category for e in memory_store.list()} == {"preference", "decision"}

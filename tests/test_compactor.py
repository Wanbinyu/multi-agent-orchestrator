"""ContextCompactor 单元测试"""
from __future__ import annotations

from unittest.mock import MagicMock

from src.core.compactor import ContextCompactor
from src.models.schemas import ChatMessage


def _make_messages(n: int, content_size: int = 200) -> list[ChatMessage]:
    msgs = [ChatMessage(role="system", content="system")]
    for i in range(n):
        msgs.append(ChatMessage(role="user" if i % 2 == 0 else "assistant", content="x" * content_size + str(i)))
    return msgs


def _mock_gateway(summary_text: str = "这是摘要") -> MagicMock:
    gw = MagicMock()
    gw.main_model = "test-model"
    resp = MagicMock()
    resp.content = summary_text
    gw.chat_with_main_model.return_value = resp
    return gw


def test_no_compaction_under_threshold():
    gw = _mock_gateway()
    compactor = ContextCompactor(gw, max_context_tokens=1_000_000, keep_recent=4)
    msgs = _make_messages(12)
    result = compactor.maybe_compact(msgs)
    assert result is msgs  # 未压缩，原样返回
    gw.chat_with_main_model.assert_not_called()


def test_no_compaction_when_disabled():
    gw = _mock_gateway()
    compactor = ContextCompactor(gw, max_context_tokens=0)
    msgs = _make_messages(50)
    result = compactor.maybe_compact(msgs)
    assert result is msgs


def test_no_compaction_too_few_messages():
    gw = _mock_gateway()
    compactor = ContextCompactor(gw, max_context_tokens=100, keep_recent=6, min_messages_to_compact=10)
    msgs = _make_messages(5)  # 少于 min_messages_to_compact
    result = compactor.maybe_compact(msgs)
    assert result is msgs


def test_compaction_replaces_old_messages_with_summary():
    gw = _mock_gateway(summary_text="压缩后的摘要内容")
    compactor = ContextCompactor(gw, max_context_tokens=500, threshold=0.5, keep_recent=4, min_messages_to_compact=6)
    msgs = _make_messages(20, content_size=100)
    before = len(msgs)

    result = compactor.maybe_compact(msgs)

    assert len(result) < before
    # 保留 system + 摘要 + 最近 4 条
    assert result[0].role == "system"
    assert "摘要" in result[1].content
    assert len(result) == 1 + 1 + 4  # system + summary + recent
    gw.chat_with_main_model.assert_called_once()


def test_compaction_preserves_recent_messages():
    gw = _mock_gateway(summary_text="摘要")
    compactor = ContextCompactor(gw, max_context_tokens=500, threshold=0.5, keep_recent=4, min_messages_to_compact=6)
    msgs = _make_messages(20, content_size=100)
    recent_contents = [m.content for m in msgs[-4:]]

    result = compactor.maybe_compact(msgs)

    result_recent_contents = [m.content for m in result[-4:]]
    assert result_recent_contents == recent_contents


def test_compaction_summary_failure_aborts():
    gw = MagicMock()
    gw.main_model = "test-model"
    gw.chat_with_main_model.side_effect = RuntimeError("model down")
    compactor = ContextCompactor(gw, max_context_tokens=500, threshold=0.5, keep_recent=4, min_messages_to_compact=6)
    msgs = _make_messages(20, content_size=100)

    result = compactor.maybe_compact(msgs)

    # 压缩失败时返回原始消息，不中断
    assert result is msgs


def test_needs_compaction_checks_token_count():
    gw = _mock_gateway()
    compactor = ContextCompactor(gw, max_context_tokens=1000, threshold=0.5, min_messages_to_compact=4)
    small = _make_messages(3)
    assert compactor.needs_compaction(small) is False

    large = _make_messages(40, content_size=100)
    assert compactor.needs_compaction(large) is True


def test_transcript_truncates_long_content():
    long_msg = ChatMessage(role="user", content="y" * 2000)
    transcript = ContextCompactor._build_transcript([long_msg])
    assert "已截断" in transcript
    assert len(transcript) < 2000

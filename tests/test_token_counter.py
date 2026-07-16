"""token_counter 单元测试"""
from __future__ import annotations

from src.core.token_counter import count_message_tokens, count_messages_tokens, count_tokens
from src.models.schemas import ChatMessage, ToolUseContentBlock


def test_count_tokens_nonempty():
    assert count_tokens("hello world") > 0


def test_count_tokens_empty():
    assert count_tokens("") == 0


def test_count_tokens_chinese():
    # 中文应产生非零 token 数
    assert count_tokens("你好世界") > 0


def test_count_message_tokens_includes_overhead():
    msg = ChatMessage(role="user", content="hi")
    base = count_tokens("hi")
    assert count_message_tokens(msg) == base + 4


def test_count_messages_tokens_sum():
    msgs = [
        ChatMessage(role="system", content="system prompt"),
        ChatMessage(role="user", content="hello"),
        ChatMessage(role="assistant", content="hi there"),
    ]
    total = count_messages_tokens(msgs)
    assert total > 0
    # 等于各条之和
    expected = sum(count_message_tokens(m) for m in msgs)
    assert total == expected


def test_count_message_tokens_uses_native_payload_instead_of_display_text():
    short = ChatMessage(role="assistant", content="调用工具")
    native = ChatMessage(
        role="assistant",
        content="调用工具",
        content_blocks=[ToolUseContentBlock(
            id="toolu_count_1",
            name="read_file",
            input={"path": "README.md"},
        )],
        provider_payload=[{
            "type": "thinking",
            "thinking": "x" * 200,
            "signature": "sig",
        }],
    )

    assert count_message_tokens(native) > count_message_tokens(short)

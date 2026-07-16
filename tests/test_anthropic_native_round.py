"""Anthropic 原生内容块和工具结果回传契约。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.core.native_content import tool_result_blocks
from src.gateway.provider import AnthropicProvider
from src.models.schemas import ChatMessage, ModelConfig, ProviderConfig


class _Block:
    def __init__(self, payload: dict):
        self.type = payload["type"]
        self.payload = payload

    def model_dump(self, **_kwargs):
        return dict(self.payload)


def _provider() -> AnthropicProvider:
    return AnthropicProvider(
        "anthropic",
        ProviderConfig(
            name="Anthropic",
            type="anthropic",
            base_url="https://api.anthropic.com",
            api_keys=["test-key"],
        ),
    )


def _response(blocks: list[dict], input_tokens: int = 10, output_tokens: int = 5):
    return SimpleNamespace(
        content=[_Block(block) for block in blocks],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )


def test_anthropic_sync_round_preserves_private_state_and_tool_result_order():
    provider = _provider()
    client = MagicMock()
    client.messages.create.side_effect = [
        _response([
            {
                "type": "thinking",
                "thinking": "private chain of thought",
                "signature": "sig-1",
            },
            {"type": "text", "text": "我先读取文件。"},
            {
                "type": "tool_use",
                "id": "toolu_read_1",
                "name": "read_file",
                "input": {"path": "README.md"},
            },
        ]),
        _response([{"type": "text", "text": "读取完成。"}]),
    ]
    provider._make_client = MagicMock(return_value=client)  # type: ignore[method-assign]
    model = ModelConfig(provider="anthropic", model_id="claude-sonnet-5")

    first = provider.chat(
        [ChatMessage(role="user", content="读取 README")],
        model,
    )

    assert "private chain of thought" not in first.content
    assert [block.type for block in first.content_blocks] == ["text", "tool_use"]
    assert first.provider_payload[0]["type"] == "thinking"

    calls = [{
        "tool": "read_file",
        "tool_use_id": "toolu_read_1",
        "success": True,
        "output": "README content",
    }]
    second = provider.chat(
        [
            ChatMessage(role="user", content="读取 README"),
            ChatMessage(
                role="assistant",
                content=first.content,
                content_blocks=first.content_blocks,
                provider_payload=first.provider_payload,
            ),
            ChatMessage(
                role="user",
                content="工具读取成功",
                content_blocks=tool_result_blocks(calls),
            ),
        ],
        model,
    )

    sent = client.messages.create.call_args_list[1].kwargs["messages"]
    assert sent[1]["content"][0]["type"] == "thinking"
    assert sent[1]["content"][2]["id"] == "toolu_read_1"
    assert sent[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "toolu_read_1",
        "content": "README content",
        "is_error": False,
    }
    assert sent[2]["content"][1]["type"] == "text"
    assert second.content == "读取完成。"


def test_anthropic_stream_emits_same_safe_and_private_message_state():
    provider = _provider()
    final_message = _response([
        {"type": "thinking", "thinking": "hidden", "signature": "sig"},
        {
            "type": "tool_use",
            "id": "toolu_stream_1",
            "name": "read_file",
            "input": {"path": "README.md"},
        },
    ])
    events = [
        SimpleNamespace(
            type="content_block_start",
            content_block=SimpleNamespace(
                type="tool_use", name="read_file", id="toolu_stream_1"
            ),
        ),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(
                type="input_json_delta", partial_json='{"path":"README.md"}'
            ),
        ),
        SimpleNamespace(type="content_block_stop"),
        SimpleNamespace(
            type="message_delta",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        ),
    ]

    class _Stream:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def __iter__(self):
            return iter(events)

        def get_final_message(self):
            return final_message

    client = MagicMock()
    client.messages.stream.return_value = _Stream()
    provider._make_client = MagicMock(return_value=client)  # type: ignore[method-assign]

    chunks = list(provider.chat_stream(
        [ChatMessage(role="user", content="读取 README")],
        ModelConfig(provider="anthropic", model_id="claude-sonnet-5"),
    ))

    state = next(chunk for chunk in chunks if chunk.type == "message_state")
    assert [block.type for block in state.content_blocks] == ["tool_use"]
    assert state.content_blocks[0].id == "toolu_stream_1"
    assert state.provider_payload[0]["type"] == "thinking"
    assert all("hidden" not in (chunk.content or "") for chunk in chunks)

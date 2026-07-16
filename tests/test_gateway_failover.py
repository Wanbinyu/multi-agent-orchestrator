"""GatewayClient 故障切换与流式去重测试"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from src.gateway.client import GatewayClient
from src.gateway.errors import ProviderError
from src.models.schemas import ChatMessage, ChatResponse, ModelConfig, ProviderConfig, StreamChunk


def _make_client(tmp_path, monkeypatch, model_name="glm-ark"):
    """构造带多个模型的 GatewayClient，provider 全部 mock"""
    from src.gateway.client import Billing
    from src.gateway.router import ModelRouter

    client = GatewayClient.__new__(GatewayClient)
    client.models = {
        "glm-ark": ModelConfig(
            provider="ark",
            model_id="ark-code-latest",
            fallback_models=["glm-chat", "kimi-fake"],
            failover_enabled=True,
            failover_cooldown_seconds=1,
        ),
        "glm-chat": ModelConfig(
            provider="ark",
            model_id="ark-chat-latest",
            fallback_models=[],
            failover_enabled=True,
        ),
        "kimi-fake": ModelConfig(
            provider="ark",
            model_id="kimi-for-coding",
            fallback_models=[],
            failover_enabled=True,
        ),
    }
    client.main_model = model_name
    client.default_failover_chain = []
    client.billing = Billing()
    client.router = ModelRouter(client.models, {})
    client._unhealthy_models = {}
    client.last_failover = None

    provider = MagicMock()
    provider.name = "ark"
    provider.config = ProviderConfig(
        name="ark",
        type="anthropic",
        base_url="https://example.com",
        api_keys=["key"],
    )
    client.providers = {"ark": provider}
    return client, provider


# ---------- 流式去重 ----------


def test_chat_stream_no_duplicate_on_mid_stream_error(tmp_path, monkeypatch):
    """流式过程中发生异常时，不重试也不重复产出已输出的 chunk"""
    client, provider = _make_client(tmp_path, monkeypatch)

    def _stream(*args, **kwargs):
        yield StreamChunk(type="delta", content="hello")
        yield StreamChunk(type="delta", content=" world")
        raise RuntimeError("connection reset")

    provider.chat_stream.side_effect = _stream

    async def _run():
        async for _ in client.chat_stream([MagicMock()], "glm-ark", max_retries=2):
            pass

    with pytest.raises(ProviderError) as raised:
        asyncio.run(_run())

    assert raised.value.code == "stream_interrupted"
    assert raised.value.retryable is False
    # provider 只被调用一次，没有重试
    assert provider.chat_stream.call_count == 1


def test_chat_stream_retries_when_no_chunks_yielded(tmp_path, monkeypatch):
    """尚未产出任何 chunk 时发生异常，允许重试"""
    client, provider = _make_client(tmp_path, monkeypatch)

    call_count = 0

    def _stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("timeout")
        yield StreamChunk(type="delta", content="ok")

    provider.chat_stream.side_effect = _stream

    async def _run():
        chunks = []
        async for chunk in client.chat_stream([MagicMock()], "glm-ark", max_retries=2):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(_run())

    assert provider.chat_stream.call_count == 2
    assert len(chunks) == 1
    assert chunks[0].content == "ok"


# ---------- 故障切换 ----------


def test_chat_fails_over_on_quota_error(tmp_path, monkeypatch):
    """429 配额错误时自动切换到回退模型"""
    client, provider = _make_client(tmp_path, monkeypatch)

    def _chat(messages, model_config, **kwargs):
        if model_config.model_id == "ark-code-latest":
            raise RuntimeError("Error code: 429 - AccountQuotaExceeded")
        return ChatResponse(
            content="fallback answer",
            model=model_config.model_id,
            provider="ark",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
        )

    provider.chat.side_effect = _chat

    response = client.chat([MagicMock()], "glm-ark", max_retries=0)

    assert response.content == "fallback answer"
    assert response.model == "ark-chat-latest"
    assert client.last_failover is not None
    assert client.last_failover["from_model"] == "glm-ark"
    assert client.last_failover["to_model"] == "glm-chat"


def test_chat_retries_short_rate_limit_before_failover(tmp_path, monkeypatch):
    client, provider = _make_client(tmp_path, monkeypatch)

    def _chat(messages, model_config, **kwargs):
        if model_config.model_id == "ark-code-latest":
            raise RuntimeError("Error code: 429 rate limit")
        return ChatResponse(
            content="fallback answer",
            model=model_config.model_id,
            provider="ark",
        )

    provider.chat.side_effect = _chat

    response = client.chat([MagicMock()], "glm-ark", max_retries=1)

    assert response.content == "fallback answer"
    assert provider.chat.call_count == 3
    assert [item["error_code"] for item in client.last_attempt_trace] == [
        "rate_limit_error",
        "rate_limit_error",
        "",
    ]
    assert client.last_failover["error_code"] == "rate_limit_error"
    assert client.last_failover["attempts"] == 2


def test_chat_retries_server_error_then_succeeds(tmp_path, monkeypatch):
    client, provider = _make_client(tmp_path, monkeypatch)
    response = ChatResponse(content="ok", model="ark-code-latest", provider="ark")
    provider.chat.side_effect = [RuntimeError("status code: 503"), response]

    assert client.chat([MagicMock()], "glm-ark", max_retries=1).content == "ok"
    assert provider.chat.call_count == 2
    assert client.last_attempt_trace[0]["error_code"] == "server_error"
    assert client.last_attempt_trace[-1]["success"] is True


def test_failover_chain_expands_nested_fallbacks(tmp_path, monkeypatch):
    """链式配置按真实 providers.yaml 形状递归展开并避免环路。"""
    client, _ = _make_client(tmp_path, monkeypatch)
    client.models["glm-ark"].fallback_models = ["kimi-fake"]
    client.models["kimi-fake"].fallback_models = ["glm-chat"]
    client.models["glm-chat"].fallback_models = ["kimi-fake"]

    assert client._get_failover_chain("glm-ark") == [
        "glm-ark", "kimi-fake", "glm-chat",
    ]


def test_nested_failover_reaches_third_model(tmp_path, monkeypatch):
    client, provider = _make_client(tmp_path, monkeypatch)
    client.models["glm-ark"].fallback_models = ["kimi-fake"]
    client.models["kimi-fake"].fallback_models = ["glm-chat"]

    def _chat(messages, model_config, **kwargs):
        if model_config.model_id != "ark-chat-latest":
            raise RuntimeError("Error code: 429 - AccountQuotaExceeded")
        return ChatResponse(
            content="third model", model=model_config.model_id, provider="ark"
        )

    provider.chat.side_effect = _chat
    response = client.chat([MagicMock()], "glm-ark", max_retries=0)

    assert response.content == "third model"
    assert provider.chat.call_count == 3


def test_chat_stream_fails_over_on_quota_error(tmp_path, monkeypatch):
    """流式 429 时发出 failover 事件并切换到回退模型"""
    client, provider = _make_client(tmp_path, monkeypatch)

    def _stream(messages, model_config, **kwargs):
        if model_config.model_id == "ark-code-latest":
            raise RuntimeError("Error code: 429 - AccountQuotaExceeded")
        yield StreamChunk(type="delta", content="fallback ok")

    provider.chat_stream.side_effect = _stream

    async def _run():
        chunks = []
        async for chunk in client.chat_stream([MagicMock()], "glm-ark", max_retries=0):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(_run())

    assert len(chunks) == 2
    assert chunks[0].type == "failover"
    assert chunks[0].from_model == "glm-ark"
    assert chunks[0].to_model == "glm-chat"
    assert chunks[1].type == "delta"
    assert chunks[1].content == "fallback ok"


def test_chat_raises_on_fatal_error_without_failover(tmp_path, monkeypatch):
    """认证错误直接抛出，不切换"""
    client, provider = _make_client(tmp_path, monkeypatch)

    provider.chat.side_effect = RuntimeError("AuthenticationError: invalid api key")

    with pytest.raises(ProviderError) as raised:
        client.chat([MagicMock()], "glm-ark")

    assert raised.value.code == "authentication_error"
    assert client.last_failover is None
    assert provider.chat.call_count == 1


def test_bad_request_does_not_failover_or_mark_unhealthy(tmp_path, monkeypatch):
    client, provider = _make_client(tmp_path, monkeypatch)
    provider.chat.side_effect = RuntimeError("BadRequestError: invalid max_tokens")

    with pytest.raises(ProviderError) as raised:
        client.chat([MagicMock()], "glm-ark")

    assert raised.value.code == "invalid_request_error"
    assert provider.chat.call_count == 1
    assert client._unhealthy_models == {}


def test_quota_classification_wins_over_invalid_request_text(tmp_path, monkeypatch):
    client, provider = _make_client(tmp_path, monkeypatch)

    def _chat(messages, model_config, **kwargs):
        if model_config.model_id == "ark-code-latest":
            raise RuntimeError("Error code: 429 invalid request: quota exceeded")
        return ChatResponse(content="ok", model=model_config.model_id, provider="ark")

    provider.chat.side_effect = _chat
    assert client.chat([MagicMock()], "glm-ark", max_retries=0).content == "ok"


def test_quota_cooldown_parses_five_hour_window(tmp_path, monkeypatch):
    client, _ = _make_client(tmp_path, monkeypatch)
    before = __import__("time").time()
    client._mark_unhealthy(
        "glm-ark",
        RuntimeError("429 AccountQuotaExceeded: exceeded the 5-hour usage quota"),
    )

    assert client._unhealthy_models["glm-ark"] - before >= 5 * 3600 - 1


def test_chat_skips_unsupported_model_and_continues(tmp_path, monkeypatch):
    """模型不存在/不支持时跳过并继续尝试下一个"""
    client, provider = _make_client(tmp_path, monkeypatch)

    def _chat(messages, model_config, **kwargs):
        if model_config.model_id == "ark-code-latest":
            raise RuntimeError("Error code: 429 - AccountQuotaExceeded")
        if model_config.model_id == "ark-chat-latest":
            raise RuntimeError("UnsupportedModel: the model does not support coding plan")
        return ChatResponse(
            content="fallback answer",
            model=model_config.model_id,
            provider="ark",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
        )

    provider.chat.side_effect = _chat

    response = client.chat([MagicMock()], "glm-ark", max_retries=0)

    assert response.content == "fallback answer"
    assert response.model == "kimi-for-coding"
    assert client.last_failover is not None
    assert client.last_failover["from_model"] == "glm-chat"
    assert client.last_failover["to_model"] == "kimi-fake"


def test_unhealthy_models_are_skipped(tmp_path, monkeypatch):
    """已标记为不健康的模型会被跳过"""
    client, provider = _make_client(tmp_path, monkeypatch)
    import time

    client._unhealthy_models["glm-ark"] = time.time() + 60

    provider.chat.return_value = ChatResponse(
        content="ok",
        model="ark-chat-latest",
        provider="ark",
        input_tokens=1,
        output_tokens=1,
        cost_usd=0.0,
    )

    response = client.chat([MagicMock()], "glm-ark", max_retries=0)

    assert response.model == "ark-chat-latest"
    assert client.last_failover is not None
    assert client.last_failover["from_model"] == "glm-ark"
    assert "冷却" in client.last_failover["reason"]
    assert [item["error_code"] for item in client.last_attempt_trace] == [
        "cooldown_skip",
        "",
    ]


def test_stream_reports_model_skipped_during_cooldown(tmp_path, monkeypatch):
    client, provider = _make_client(tmp_path, monkeypatch)
    import time

    client._unhealthy_models["glm-ark"] = time.time() + 60

    def _stream(*args, **kwargs):
        yield StreamChunk(type="delta", content="ok")

    provider.chat_stream.side_effect = _stream

    async def _run():
        return [
            chunk
            async for chunk in client.chat_stream(
                [MagicMock()], "glm-ark", max_retries=0
            )
        ]

    chunks = asyncio.run(_run())
    assert [chunk.type for chunk in chunks] == ["failover", "delta"]
    assert chunks[0].to_model == "glm-chat"


def test_model_diagnostic_updates_health_state(tmp_path, monkeypatch):
    client, provider = _make_client(tmp_path, monkeypatch)
    provider.chat.side_effect = RuntimeError("429 AccountQuotaExceeded")

    failed = client.test_model("glm-ark")

    assert failed["success"] is False
    assert failed["consumes_quota"] is True
    assert "glm-ark" in client._unhealthy_models

    provider.chat.side_effect = None
    provider.chat.return_value = ChatResponse(
        content="ok", model="ark-code-latest", provider="ark"
    )
    passed = client.test_model("glm-ark")

    assert passed["success"] is True
    assert "glm-ark" not in client._unhealthy_models
    call = provider.chat.call_args
    assert call.kwargs["max_tokens"] == 1


def test_model_auth_failure_does_not_enter_cooldown(tmp_path, monkeypatch):
    client, provider = _make_client(tmp_path, monkeypatch)
    provider.chat.side_effect = RuntimeError(
        "AuthenticationError: invalid api key private-value"
    )

    failed = client.test_model("glm-ark")

    assert failed["error_code"] == "authentication_error"
    assert "private-value" not in failed["error"]
    assert "glm-ark" not in client._unhealthy_models


# ---------- Agent 事件转换 ----------


def test_agent_converts_failover_chunk_to_event():
    from src.core.agent import Agent
    from src.models.schemas import StreamChunk

    chunk = StreamChunk(
        type="failover",
        from_model="glm-ark",
        to_model="glm-chat",
        reason="429 quota",
    )
    event = Agent._handle_stream_chunk(chunk)

    assert event is not None
    assert event.type == "model_failover"
    assert event.failover["from_model"] == "glm-ark"
    assert event.failover["to_model"] == "glm-chat"
    assert "连接失效" in event.delta

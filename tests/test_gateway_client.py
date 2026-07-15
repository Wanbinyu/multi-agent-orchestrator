"""GatewayClient 单元测试"""
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.core.context_budget import ContextBudgetExceeded
from src.gateway.client import Billing, GatewayClient
from src.models.schemas import ChatMessage, ChatResponse, ModelConfig


def _sample_providers_yaml(main_model: str | None = "glm-ark"):
    data = {
        "providers": {
            "ark": {
                "name": "火山方舟",
                "type": "anthropic",
                "base_url": "https://ark.cn-beijing.volces.com/api/coding",
                "api_keys": ["${ARK_API_KEY}"],
                "timeout": 120,
                "rpm_limit": 60,
            }
        },
        "models": {
            "glm-ark": {
                "provider": "ark",
                "model_id": "ark-code-latest",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
            },
            "claude-sonnet-5": {
                "provider": "ark",
                "model_id": "claude-sonnet-5-20251001",
                "input_price_per_1m": 3.0,
                "output_price_per_1m": 15.0,
            },
        },
    }
    if main_model is not None:
        data["main_model"] = main_model
    return yaml.dump(data)


def _make_client(tmp_path, monkeypatch, main_model: str | None = "glm-ark"):
    config_path = tmp_path / "providers.yaml"
    config_path.write_text(_sample_providers_yaml(main_model), encoding="utf-8")

    provider = MagicMock()
    provider.chat.return_value = ChatResponse(
        content="hello",
        model="ark-code-latest",
        provider="ark",
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.001,
    )

    def fake_create_provider(name, config):
        provider.name = name
        provider.config = config
        return provider

    monkeypatch.setattr("src.gateway.client.create_provider", fake_create_provider)
    monkeypatch.setattr("src.gateway.client.time.sleep", MagicMock())

    return GatewayClient(config_path=str(config_path)), provider


def test_load_config_parses_providers_and_models(tmp_path, monkeypatch):
    client, _ = _make_client(tmp_path, monkeypatch)

    assert "ark" in client.providers
    assert "glm-ark" in client.models
    assert "claude-sonnet-5" in client.models
    assert client.main_model == "glm-ark"


def test_main_model_fallback_to_first_model(tmp_path, monkeypatch):
    config_path = tmp_path / "providers.yaml"
    config_path.write_text(yaml.dump({
        "providers": {
            "ark": {
                "name": "火山方舟",
                "type": "anthropic",
                "base_url": "https://example.com",
                "api_keys": ["key"],
            }
        },
        "models": {
            "only-model": {"provider": "ark", "model_id": "x"}
        },
    }), encoding="utf-8")

    monkeypatch.setattr("src.gateway.client.create_provider", lambda name, cfg: MagicMock())
    client = GatewayClient(config_path=str(config_path))

    assert client.main_model == "only-model"


def test_chat_returns_response_and_records_billing(tmp_path, monkeypatch):
    client, provider = _make_client(tmp_path, monkeypatch)
    messages = [MagicMock()]

    response = client.chat(messages, "glm-ark", task_id="task-1")

    assert response.content == "hello"
    assert response.input_tokens == 10
    provider.chat.assert_called_once()
    assert client.billing.total_input_tokens == 10
    assert client.billing.total_output_tokens == 5
    assert client.billing.total_cost_usd == 0.001
    assert len(client.billing.calls) == 1
    assert client.billing.calls[0]["task_id"] == "task-1"


def test_chat_rejects_oversized_context_before_provider_call(tmp_path, monkeypatch):
    client, provider = _make_client(tmp_path, monkeypatch)
    client.models["glm-ark"] = ModelConfig(
        provider="ark",
        model_id="ark-code-latest",
        context_window_tokens=8192,
        max_output_tokens=4096,
        context_safety_ratio=0.1,
    )
    messages = [ChatMessage(role="user", content="x" * 30_000)]

    with pytest.raises(ContextBudgetExceeded, match="发送前阻止请求"):
        client.chat(messages, "glm-ark", max_tokens=4096)

    provider.chat.assert_not_called()


def test_chat_retries_then_succeeds(tmp_path, monkeypatch):
    client, provider = _make_client(tmp_path, monkeypatch)
    provider.chat.side_effect = [RuntimeError("timeout"), ChatResponse(
        content="ok",
        model="ark-code-latest",
        provider="ark",
        input_tokens=2,
        output_tokens=1,
        cost_usd=0.0001,
    )]

    response = client.chat([MagicMock()], "glm-ark", max_retries=2)

    assert response.content == "ok"
    assert provider.chat.call_count == 2


def test_chat_exhausts_retries_and_raises(tmp_path, monkeypatch):
    client, provider = _make_client(tmp_path, monkeypatch)
    provider.chat.side_effect = RuntimeError("always fails")

    with pytest.raises(RuntimeError, match="模型 glm-ark 请求失败"):
        client.chat([MagicMock()], "glm-ark", max_retries=2)

    assert provider.chat.call_count == 3


def test_chat_unknown_model_raises():
    client = GatewayClient.__new__(GatewayClient)
    client.models = {}
    client.providers = {}

    with pytest.raises(ValueError, match="未知模型"):
        client.chat([MagicMock()], "not-a-model")


def test_chat_unknown_provider_raises(tmp_path, monkeypatch):
    config_path = tmp_path / "providers.yaml"
    config_path.write_text(yaml.dump({
        "providers": {},
        "models": {
            "glm-ark": {
                "provider": "missing-provider",
                "model_id": "x",
            }
        },
        "main_model": "glm-ark",
    }), encoding="utf-8")

    monkeypatch.setattr("src.gateway.client.create_provider", lambda name, cfg: MagicMock())
    client = GatewayClient(config_path=str(config_path))

    with pytest.raises(ValueError, match="未知 provider"):
        client.chat([MagicMock()], "glm-ark")


def test_chat_with_main_model_uses_main_model(tmp_path, monkeypatch):
    client, provider = _make_client(tmp_path, monkeypatch)

    response = client.chat_with_main_model([MagicMock()], task_id="main-task")

    assert response.content == "hello"
    call_args = provider.chat.call_args.args
    assert len(call_args) >= 2
    assert call_args[1] == ModelConfig(
        provider="ark",
        model_id="ark-code-latest",
        input_price_per_1m=1.0,
        output_price_per_1m=1.0,
    )


def test_chat_with_main_model_raises_when_not_configured():
    client = GatewayClient.__new__(GatewayClient)
    client.main_model = None

    with pytest.raises(ValueError, match="未配置主模型"):
        client.chat_with_main_model([MagicMock()])


def test_get_main_model():
    client = GatewayClient.__new__(GatewayClient)
    client.main_model = "glm-ark"
    assert client.get_main_model() == "glm-ark"


def test_get_model_config():
    client = GatewayClient.__new__(GatewayClient)
    client.models = {"glm-ark": ModelConfig(provider="ark", model_id="x")}
    assert client.get_model_config("glm-ark").provider == "ark"


def test_get_router():
    client = GatewayClient.__new__(GatewayClient)
    client.router = MagicMock()
    assert client.get_router() is client.router


def test_print_billing(capsys):
    client = GatewayClient.__new__(GatewayClient)
    client.billing = Billing()
    client.billing.record(ChatResponse(
        content="",
        model="glm-ark",
        provider="ark",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.0001,
    ))

    client.print_billing()
    captured = capsys.readouterr()
    assert "输入 token: 100" in captured.out
    assert "输出 token: 50" in captured.out
    assert "总成本: $0.0001" in captured.out


def test_billing_summary_rounds_cost():
    billing = Billing()
    billing.record(ChatResponse(
        content="",
        model="m",
        provider="p",
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.1234567,
    ))

    summary = billing.summary()
    assert summary["total_cost_usd"] == 0.123457
    assert summary["total_input_tokens"] == 0
    assert summary["calls"][0]["cost_usd"] == 0.1234567


def test_load_config_expands_env_vars(monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_API_KEY", "expanded-key")

    config_path = tmp_path / "providers.yaml"
    config_path.write_text(yaml.dump({
        "providers": {
            "test": {
                "name": "Test",
                "type": "anthropic",
                "base_url": "https://example.com",
                "api_keys": ["${TEST_API_KEY}"],
            }
        },
        "models": {
            "test-model": {"provider": "test", "model_id": "m"}
        },
    }), encoding="utf-8")

    def fake_create_provider(name, config):
        fake = MagicMock()
        fake.config = config
        return fake

    monkeypatch.setattr("src.gateway.client.create_provider", fake_create_provider)
    client = GatewayClient(config_path=str(config_path))

    assert client.providers["test"].config.api_keys == ["expanded-key"]

"""测试 Provider 连通性测试"""
from unittest.mock import MagicMock, patch

from src.gateway.connection_test import (
    ConnectionTestResult,
    check_anthropic_connection,
    check_openai_compatible_connection,
    check_provider_connection,
)
from src.gateway.provider import AnthropicProvider
from src.models.schemas import ProviderConfig


def test_anthropic_connection_success():
    mock_response = MagicMock()
    with patch("src.gateway.connection_test.anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = mock_response

        result = check_anthropic_connection("real-key", "https://api.anthropic.com")
        assert result.success is True
        assert result.provider_name == "anthropic"
        assert result.error_message == ""


def test_coding_plan_connection_uses_bearer_auth_token():
    with patch("src.gateway.connection_test.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = MagicMock()

        result = check_anthropic_connection(
            "coding-token",
            "https://ark.cn-beijing.volces.com/api/coding",
            "ark-code-latest",
        )

    assert result.success is True
    kwargs = MockClient.call_args.kwargs
    assert kwargs["auth_token"] == "coding-token"
    assert "api_key" not in kwargs


def test_coding_plan_provider_prefers_configured_token(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "environment-token")
    provider = AnthropicProvider(
        "ark",
        ProviderConfig(
            name="ark",
            type="anthropic",
            base_url="https://ark.cn-beijing.volces.com/api/coding",
            api_keys=["configured-token"],
        ),
    )
    with patch("src.gateway.provider.anthropic.Anthropic") as MockClient:
        provider._make_client("configured-token")

    kwargs = MockClient.call_args.kwargs
    assert kwargs["auth_token"] == "configured-token"
    assert "api_key" not in kwargs


def test_coding_plan_provider_uses_environment_token_when_key_missing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "environment-token")
    provider = AnthropicProvider(
        "ark",
        ProviderConfig(
            name="ark",
            type="anthropic",
            base_url="https://ark.cn-beijing.volces.com/api/coding",
            api_keys=[],
        ),
    )
    with patch("src.gateway.provider.anthropic.Anthropic") as MockClient:
        provider._make_client("")

    assert MockClient.call_args.kwargs["auth_token"] == "environment-token"


def test_anthropic_connection_auth_error():
    import anthropic

    with patch("src.gateway.connection_test.anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.side_effect = anthropic.AuthenticationError(
            "invalid", response=MagicMock(), body=MagicMock()
        )

        result = check_anthropic_connection("fake-key", "https://api.anthropic.com")
        assert result.success is False
        assert "API Key" in result.error_message


def test_openai_connection_success():
    mock_response = MagicMock()
    with patch("src.gateway.connection_test.openai.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = mock_response

        result = check_openai_compatible_connection("real-key", "https://api.openai.com/v1", "gpt-4o")
        assert result.success is True
        assert result.provider_type == "openai"


def test_openai_connection_auth_error():
    import openai

    with patch("src.gateway.connection_test.openai.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.side_effect = openai.AuthenticationError(
            "invalid", response=MagicMock(), body=MagicMock()
        )

        result = check_openai_compatible_connection("fake-key", "https://api.openai.com/v1", "gpt-4o")
        assert result.success is False
        assert "API Key" in result.error_message


def test_provider_connection_unsupported_type():
    result = check_provider_connection("unknown", "key", "http://localhost")
    assert result.success is False
    assert "不支持" in result.error_message


def test_provider_connection_openai_without_model_id():
    result = check_provider_connection("openai", "key", "http://localhost", model_id="")
    assert result.success is False
    assert "model_id" in result.error_message

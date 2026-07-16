"""测试 Provider 连通性测试"""
from unittest.mock import MagicMock, patch

import anthropic
import httpx
import pytest

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
        assert instance.messages.create.call_args.kwargs["model"] == "claude-sonnet-5"


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


def _anthropic_status_error(exception_type, status: int, body=None):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=request)
    return exception_type(
        "upstream detail includes private-value",
        response=response,
        body=body or {"type": "error"},
    )


@pytest.mark.parametrize(
    ("exception_type", "status", "expected_code", "expected_text"),
    [
        (anthropic.AuthenticationError, 401, "authentication_error", "API Key"),
        (anthropic.PermissionDeniedError, 403, "permission_error", "无权"),
        (anthropic.NotFoundError, 404, "model_not_found", "模型"),
        (anthropic.RateLimitError, 429, "rate_limit_error", "重试"),
    ],
)
def test_anthropic_connection_classifies_status_errors(
    exception_type, status, expected_code, expected_text
):
    with patch("src.gateway.connection_test.anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.side_effect = _anthropic_status_error(
            exception_type, status
        )

        result = check_anthropic_connection("fake-key", "https://api.anthropic.com")
        assert result.success is False
        assert result.error_code == expected_code
        assert expected_text in f"{result.error_message} {result.action}"
        assert result.provider_type == "anthropic"
        assert "private-value" not in result.error_message


def test_anthropic_connection_classifies_timeout():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    with patch("src.gateway.connection_test.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.side_effect = anthropic.APITimeoutError(
            request=request
        )

        result = check_anthropic_connection("fake-key", "https://api.anthropic.com")

    assert result.error_code == "timeout_error"
    assert "超时" in result.error_message


def test_anthropic_connection_classifies_context_limit():
    body = {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "prompt exceeds the model context window",
        },
    }
    with patch("src.gateway.connection_test.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.side_effect = _anthropic_status_error(
            anthropic.BadRequestError, 400, body
        )

        result = check_anthropic_connection("fake-key", "https://api.anthropic.com")

    assert result.error_code == "context_length_error"
    assert "上下文" in result.error_message


def test_anthropic_connection_keeps_other_bad_requests_distinct():
    body = {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "max_tokens must be greater than zero",
        },
    }
    with patch("src.gateway.connection_test.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.side_effect = _anthropic_status_error(
            anthropic.BadRequestError, 400, body
        )

        result = check_anthropic_connection("fake-key", "https://api.anthropic.com")

    assert result.error_code == "invalid_request_error"
    assert "消息格式" in result.error_message


def test_anthropic_connection_rejects_empty_key_without_request():
    with patch("src.gateway.connection_test.anthropic.Anthropic") as MockClient:
        result = check_anthropic_connection("", "https://api.anthropic.com")

    assert result.error_code == "authentication_error"
    MockClient.assert_not_called()


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
    assert "API Key" in result.action


def test_provider_connection_unsupported_type():
    result = check_provider_connection("unknown", "key", "http://localhost")
    assert result.success is False
    assert "不支持" in result.error_message


def test_provider_connection_openai_without_model_id():
    result = check_provider_connection("openai", "key", "http://localhost", model_id="")
    assert result.success is False
    assert "model_id" in result.error_message

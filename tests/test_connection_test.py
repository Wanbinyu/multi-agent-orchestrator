"""测试 Provider 连通性测试"""
from unittest.mock import MagicMock, patch

from src.gateway.connection_test import (
    ConnectionTestResult,
    check_anthropic_connection,
    check_openai_compatible_connection,
    check_provider_connection,
)


def test_anthropic_connection_success():
    mock_response = MagicMock()
    with patch("src.gateway.connection_test.anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = mock_response

        result = check_anthropic_connection("real-key", "https://api.anthropic.com")
        assert result.success is True
        assert result.provider_name == "anthropic"
        assert result.error_message == ""


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

"""统一 Provider 错误契约。"""
from __future__ import annotations

from src.core.context_budget import ContextBudgetExceeded
from src.gateway.errors import (
    ProviderError,
    classify_provider_error,
    provider_error_http_status,
)


def test_provider_error_redacts_upstream_details_and_secret_values():
    error = classify_provider_error(
        RuntimeError(
            "AuthenticationError: invalid api key private-key-value; headers={'x': 'secret'}"
        ),
        provider="anthropic",
        model="claude",
    )

    serialized = str(error.to_dict())
    assert error.code == "authentication_error"
    assert error.retryable is False
    assert error.failover_allowed is False
    assert "private-key-value" not in error.user_message
    assert "private-key-value" not in serialized
    assert provider_error_http_status(error) == 401


def test_provider_error_distinguishes_rate_limit_from_long_quota_window():
    limited = classify_provider_error(RuntimeError("Error code: 429 rate limit"))
    quota = classify_provider_error(
        RuntimeError("429 AccountQuotaExceeded: exceeded the 5-hour usage quota")
    )

    assert limited.code == "rate_limit_error"
    assert limited.retryable is True
    assert quota.code == "quota_exceeded"
    assert quota.retryable is False
    assert quota.failover_allowed is True


def test_local_context_budget_becomes_non_retryable_provider_error():
    error = classify_provider_error(
        ContextBudgetExceeded("输入估算 33000，安全输入预算 32000")
    )

    assert error.code == "context_length_error"
    assert error.retryable is False
    assert error.failover_allowed is False
    assert "输入估算 33000" in error.user_message


def test_stream_interruption_never_retries_or_fails_over():
    error = classify_provider_error(
        ConnectionError("connection reset with private upstream detail"),
        stream_started=True,
    )

    assert error.code == "stream_interrupted"
    assert error.retryable is False
    assert error.failover_allowed is False

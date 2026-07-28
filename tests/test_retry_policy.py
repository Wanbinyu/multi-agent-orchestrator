"""Retry policy unit tests."""
from __future__ import annotations

from src.core.retry_policy import (
    is_retryable_error_code,
    is_retryable_error_text,
    is_retryable_failure,
)
from src.gateway.errors import ProviderError
from src.models.schemas import Task, TaskResult


def test_retryable_codes():
    assert is_retryable_error_code("timeout_error")
    assert is_retryable_error_code("connection_error")
    assert is_retryable_error_code("rate_limit_error")
    assert not is_retryable_error_code("authentication_error")
    assert not is_retryable_error_code("invalid_request_error")


def test_provider_error_retryable_flag():
    err = ProviderError("timeout_error")
    assert is_retryable_failure(error=err) is True
    auth = ProviderError("authentication_error")
    assert is_retryable_failure(error=auth) is False


def test_text_fallback_still_works():
    assert is_retryable_error_text("connection timeout")
    assert is_retryable_error_text("HTTP 503 service unavailable")
    assert not is_retryable_error_text("unknown worker type")


def test_error_code_preferred_over_text():
    # deterministic message that would not match markers, but code is retryable
    assert is_retryable_failure(
        error="something went wrong",
        error_code="server_error",
    )
    # text looks transient but code says no
    assert not is_retryable_failure(
        error="connection timeout",
        error_code="authentication_error",
    )


def test_task_result_error_code_field():
    task = Task(id="t1", type="a", title="A", input="", assigned_model="m")
    result = TaskResult(
        task=task,
        success=False,
        content="",
        error="Provider 请求超时",
        error_code="timeout_error",
    )
    assert is_retryable_failure(error=result.error, error_code=result.error_code)

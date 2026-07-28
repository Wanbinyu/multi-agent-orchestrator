"""Shared retry / failover classification for tasks and provider errors."""
from __future__ import annotations

from typing import Any

from src.gateway.errors import ProviderError, ProviderErrorCode

# Codes that may be retried for the *same* model/task (transient).
RETRYABLE_ERROR_CODES: frozenset[str] = frozenset(
    {
        "timeout_error",
        "connection_error",
        "server_error",
        "rate_limit_error",
        "provider_error",
    }
)

# Substring markers kept as fallback when only free-text errors are available.
_TRANSIENT_MARKERS: tuple[str, ...] = (
    "timeout",
    "timed out",
    "超时",
    "connection",
    "连接",
    "temporarily",
    "临时",
    "rate limit",
    "429",
    "502",
    "503",
    "504",
    "stream idle",
    "无输出阈值",
)


def normalize_error_code(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, ProviderError):
        return str(value.code or "")
    text = str(value).strip()
    return text


def is_retryable_error_code(code: str | ProviderErrorCode | None) -> bool:
    if not code:
        return False
    return str(code) in RETRYABLE_ERROR_CODES


def is_retryable_error_text(error: str | None) -> bool:
    if not error:
        return False
    normalized = error.casefold()
    return any(marker in normalized for marker in _TRANSIENT_MARKERS)


def is_retryable_failure(
    *,
    error: str | Exception | None = None,
    error_code: str | None = None,
) -> bool:
    """Return True when a failed task/provider call may be retried safely.

    Preference order:
    1. ``ProviderError.retryable`` when *error* is a ProviderError
    2. explicit *error_code* against the retryable code set
    3. free-text markers (legacy Worker string errors)
    """
    if isinstance(error, ProviderError):
        return bool(error.retryable)
    code = normalize_error_code(error_code)
    if code:
        return is_retryable_error_code(code)
    if isinstance(error, Exception):
        return is_retryable_error_text(str(error))
    return is_retryable_error_text(str(error or ""))


def error_code_from_task_result(result: Any) -> str:
    """Best-effort extract of error_code from a TaskResult-like object."""
    code = getattr(result, "error_code", None)
    if code:
        return str(code)
    # Some call sites stash codes on the first tool call metadata.
    tool_calls = getattr(result, "tool_calls", None) or []
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        meta = call.get("metadata") or {}
        if isinstance(meta, dict) and meta.get("error_code"):
            return str(meta["error_code"])
    return ""

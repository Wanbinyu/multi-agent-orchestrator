"""Provider 错误分类、脱敏展示和恢复策略。"""
from __future__ import annotations

import re
from typing import Any, Literal

from src.core.context_budget import ContextBudgetExceeded


ProviderErrorCode = Literal[
    "configuration_error",
    "authentication_error",
    "permission_error",
    "model_not_found",
    "quota_exceeded",
    "rate_limit_error",
    "timeout_error",
    "connection_error",
    "server_error",
    "context_length_error",
    "invalid_request_error",
    "stream_interrupted",
    "provider_error",
]


_ERROR_DETAILS: dict[ProviderErrorCode, tuple[str, str, bool, bool]] = {
    "configuration_error": (
        "Provider 或模型配置不完整",
        "检查 providers.yaml 中的 Provider、模型映射和 API 地址",
        False,
        False,
    ),
    "authentication_error": (
        "Provider 认证失败",
        "检查 API Key 是否正确、有效并属于当前服务",
        False,
        False,
    ),
    "permission_error": (
        "当前凭据无权访问请求的模型或资源",
        "检查账号权限、区域、组织和模型授权",
        False,
        False,
    ),
    "model_not_found": (
        "请求的模型不存在或当前端点不支持该模型",
        "检查上游模型 ID，或配置可用的回退模型",
        False,
        True,
    ),
    "quota_exceeded": (
        "Provider 配额已用尽或仍在恢复窗口内",
        "等待配额恢复，或切换到有可用额度的模型",
        False,
        True,
    ),
    "rate_limit_error": (
        "Provider 请求受到短期限流",
        "稍后重试，或降低并发和请求频率",
        True,
        True,
    ),
    "timeout_error": (
        "Provider 请求超时",
        "检查网络、服务状态和超时配置后重试",
        True,
        True,
    ),
    "connection_error": (
        "无法连接到 Provider",
        "检查网络、代理和 base_url 后重试",
        True,
        True,
    ),
    "server_error": (
        "Provider 服务暂时不可用",
        "稍后重试，或使用已配置的回退模型",
        True,
        True,
    ),
    "context_length_error": (
        "请求超过模型的安全上下文或输出限制",
        "缩短输入、触发上下文压缩或降低输出上限",
        False,
        False,
    ),
    "invalid_request_error": (
        "Provider 不接受当前请求参数或消息格式",
        "检查模型能力、工具参数和输出上限配置",
        False,
        False,
    ),
    "stream_interrupted": (
        "Provider 流式响应在输出后中断",
        "保留已输出内容并重试本轮；系统不会自动重放以避免重复",
        False,
        False,
    ),
    "provider_error": (
        "Provider 请求失败",
        "检查 Provider 状态和本地配置后重试",
        True,
        True,
    ),
}


class ProviderError(RuntimeError):
    """可安全展示、可用于确定性恢复决策的 Provider 异常。"""

    def __init__(
        self,
        code: ProviderErrorCode,
        *,
        provider: str = "",
        model: str = "",
        status_code: int | None = None,
        attempts: int = 0,
        attempted_models: list[str] | None = None,
        final_model: str = "",
        cause_type: str = "",
        detail: str = "",
    ) -> None:
        message, action, retryable, failover_allowed = _ERROR_DETAILS[code]
        self.code = code
        self.message = message
        self.action = action
        self.retryable = retryable
        self.failover_allowed = failover_allowed
        self.provider = provider
        self.model = model
        self.status_code = status_code
        self.attempts = attempts
        self.attempted_models = list(dict.fromkeys(attempted_models or []))
        self.final_model = final_model or model
        self.cause_type = cause_type
        self.detail = detail
        super().__init__(self.user_message)

    @property
    def user_message(self) -> str:
        detail = f"详情：{self.detail}。" if self.detail else ""
        return f"[{self.code}] {self.message}。{detail}建议：{self.action}。"

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.code,
            "message": self.message,
            "action": self.action,
            "retryable": self.retryable,
            "failover_allowed": self.failover_allowed,
            "provider": self.provider,
            "model": self.model,
            "status_code": self.status_code,
            "attempts": self.attempts,
            "attempted_models": self.attempted_models,
            "final_model": self.final_model,
            "cause_type": self.cause_type,
            "detail": self.detail,
        }

    def with_attempts(
        self,
        *,
        attempts: int,
        attempted_models: list[str],
        final_model: str,
    ) -> "ProviderError":
        return ProviderError(
            self.code,
            provider=self.provider,
            model=self.model,
            status_code=self.status_code,
            attempts=attempts,
            attempted_models=attempted_models,
            final_model=final_model,
            cause_type=self.cause_type,
            detail=self.detail,
        )


def status_code_from_exception(exc: Exception) -> int | None:
    for candidate in (exc, getattr(exc, "response", None)):
        value = getattr(candidate, "status_code", None)
        if isinstance(value, int):
            return value
    match = re.search(
        r"(?:error\s+code|status(?:\s+code)?)\s*[:=]?\s*(\d{3})",
        str(exc),
        re.IGNORECASE,
    )
    if match is None:
        match = re.search(r"\b([45]\d{2})\b", str(exc))
    return int(match.group(1)) if match else None


def classify_provider_error(
    exc: Exception,
    *,
    provider: str = "",
    model: str = "",
    stream_started: bool = False,
) -> ProviderError:
    """把 SDK 和兼容端点异常归一为稳定、脱敏的错误语义。"""
    if isinstance(exc, ProviderError):
        return exc
    if stream_started:
        code: ProviderErrorCode = "stream_interrupted"
        return ProviderError(
            code,
            provider=provider,
            model=model,
            status_code=status_code_from_exception(exc),
            cause_type=type(exc).__name__,
        )
    if isinstance(exc, ContextBudgetExceeded):
        return ProviderError(
            "context_length_error",
            provider=provider,
            model=model,
            cause_type=type(exc).__name__,
            detail=str(exc),
        )

    status = status_code_from_exception(exc)
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    body = str(getattr(exc, "body", "") or "").lower()
    combined = f"{name} {text} {body}"

    context_markers = (
        "context window",
        "context length",
        "too many input tokens",
        "prompt is too long",
        "maximum context",
        "input length",
        "contextbudgetexceeded",
    )
    quota_markers = (
        "accountquotaexceeded",
        "quota exceeded",
        "usage quota",
        "insufficient_quota",
        "billing quota",
    )

    if any(marker in combined for marker in context_markers):
        code = "context_length_error"
    elif status == 401 or any(
        marker in combined
        for marker in ("authentication", "unauthorized", "invalid api key")
    ):
        code = "authentication_error"
    elif status == 403 or any(
        marker in combined for marker in ("permissiondenied", "forbidden")
    ):
        code = "permission_error"
    elif status == 404 or "notfound" in name or any(
        marker in combined
        for marker in (
            "model_not_found",
            "notfounderror",
            "model not found",
            "model does not exist",
            "unsupportedmodel",
            "unsupported model",
            "model is not supported",
            "invalidendpointormodel",
        )
    ):
        code = "model_not_found"
    elif status == 429 and any(marker in combined for marker in quota_markers):
        code = "quota_exceeded"
    elif status == 429 or any(
        marker in combined for marker in ("ratelimit", "rate limit", "too many requests")
    ):
        code = "rate_limit_error"
    elif "timeout" in name or "timeout" in combined:
        code = "timeout_error"
    elif "connection" in name or any(
        marker in combined for marker in ("connection reset", "unreachable", "network")
    ):
        code = "connection_error"
    elif (status is not None and status >= 500) or "service unavailable" in combined:
        code = "server_error"
    elif status in (400, 422) or any(
        marker in combined
        for marker in (
            "badrequest",
            "bad request",
            "invalid_request",
            "invalid request",
            "invalid max_tokens",
            "invalid parameter",
            "validation error",
        )
    ):
        code = "invalid_request_error"
    else:
        code = "provider_error"

    return ProviderError(
        code,
        provider=provider,
        model=model,
        status_code=status,
        cause_type=type(exc).__name__,
    )


def provider_error_http_status(error: ProviderError) -> int:
    return {
        "configuration_error": 400,
        "authentication_error": 401,
        "permission_error": 403,
        "model_not_found": 404,
        "rate_limit_error": 429,
        "quota_exceeded": 429,
        "context_length_error": 400,
        "invalid_request_error": 400,
    }.get(error.code, 502)

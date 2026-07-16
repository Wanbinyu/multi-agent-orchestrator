"""Provider 连通性测试

通过发送一个极短/低成本的请求，验证 Provider 配置是否正确、模型是否可用。
支持 Anthropic Messages API 和 OpenAI 兼容 API。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import anthropic
import openai

from src.gateway.errors import ProviderError, classify_provider_error


@dataclass
class ConnectionTestResult:
    """连通性测试结果"""

    success: bool
    provider_name: str
    provider_type: str
    base_url: str
    available_models: list[str]
    error_message: str = ""
    error_code: str = ""
    action: str = ""
    retryable: bool = False
    response_time_ms: float = 0.0


def check_anthropic_connection(
    api_key: str,
    base_url: str,
    model_id: str = "claude-sonnet-5",
    timeout: int = 30,
) -> ConnectionTestResult:
    """测试 Anthropic Messages API 连通性"""
    import time

    start = time.time()
    if not api_key.strip():
        return _provider_error_result(
            "anthropic",
            base_url,
            ProviderError("authentication_error", provider="anthropic", model=model_id),
            start,
        )
    if not model_id.strip():
        return _provider_error_result(
            "anthropic",
            base_url,
            ProviderError("configuration_error", provider="anthropic"),
            start,
        )
    try:
        client_kwargs: dict[str, Any] = {
            "base_url": base_url or None,
            "timeout": timeout,
        }
        if base_url and "volces.com/api/coding" in base_url:
            client_kwargs["auth_token"] = api_key
        else:
            client_kwargs["api_key"] = api_key
        client = anthropic.Anthropic(**client_kwargs)
        # 使用配置中的模型 ID 或一个常见模型名测试
        response = client.messages.create(
            model=model_id,
            max_tokens=10,
            messages=[{"role": "user", "content": "hi"}],
        )
        elapsed = (time.time() - start) * 1000
        return ConnectionTestResult(
            success=True,
            provider_name="anthropic",
            provider_type="anthropic",
            base_url=base_url,
            available_models=[],
            response_time_ms=elapsed,
        )
    except Exception as exception:
        return _provider_error_result(
            "anthropic",
            base_url,
            classify_provider_error(
                exception,
                provider="anthropic",
                model=model_id,
            ),
            start,
        )


def check_openai_compatible_connection(
    api_key: str,
    base_url: str,
    model_id: str,
    timeout: int = 30,
) -> ConnectionTestResult:
    """测试 OpenAI 兼容 API 连通性"""
    import time

    start = time.time()
    if not api_key.strip():
        return _provider_error_result(
            "openai_compatible",
            base_url,
            ProviderError(
                "authentication_error",
                provider="openai_compatible",
                model=model_id,
            ),
            start,
        )
    try:
        client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )
        response = client.chat.completions.create(
            model=model_id,
            max_tokens=10,
            messages=[{"role": "user", "content": "hi"}],
        )
        elapsed = (time.time() - start) * 1000
        return ConnectionTestResult(
            success=True,
            provider_name="openai_compatible",
            provider_type="openai",
            base_url=base_url,
            available_models=[],
            response_time_ms=elapsed,
        )
    except Exception as exception:
        return _provider_error_result(
            "openai_compatible",
            base_url,
            classify_provider_error(
                exception,
                provider="openai_compatible",
                model=model_id,
            ),
            start,
        )


def check_provider_connection(
    provider_type: str,
    api_key: str,
    base_url: str,
    model_id: str = "",
    timeout: int = 30,
) -> ConnectionTestResult:
    """根据 Provider 类型 dispatch 到对应的测试函数"""
    api_key = os.path.expandvars(api_key)

    if provider_type == "anthropic":
        return check_anthropic_connection(api_key, base_url, model_id, timeout)
    elif provider_type == "openai":
        if not model_id:
            # 对于 OpenAI 兼容服务，必须指定一个模型名测试
            error = ProviderError("configuration_error")
            return ConnectionTestResult(
                success=False,
                provider_name="openai_compatible",
                provider_type="openai",
                base_url=base_url,
                available_models=[],
                error_message="测试 OpenAI 兼容服务需要指定 model_id",
                error_code="configuration_error",
                action=error.action,
            )
        return check_openai_compatible_connection(api_key, base_url, model_id, timeout)
    else:
        error = ProviderError("configuration_error")
        return ConnectionTestResult(
            success=False,
            provider_name=provider_type,
            provider_type=provider_type,
            base_url=base_url,
            available_models=[],
            error_message=f"不支持的 provider 类型: {provider_type}",
            error_code="configuration_error",
            action=error.action,
        )


def _error_result(
    provider_name: str,
    base_url: str,
    message: str,
    start_time: float,
    error_code: str = "",
    action: str = "",
    retryable: bool = False,
) -> ConnectionTestResult:
    import time

    elapsed = (time.time() - start_time) * 1000
    return ConnectionTestResult(
        success=False,
        provider_name=provider_name,
        provider_type="anthropic" if provider_name == "anthropic" else "openai",
        base_url=base_url,
        available_models=[],
        error_message=message,
        error_code=error_code,
        action=action,
        retryable=retryable,
        response_time_ms=elapsed,
    )


def _provider_error_result(
    provider_name: str,
    base_url: str,
    error: ProviderError,
    start_time: float,
) -> ConnectionTestResult:
    return _error_result(
        provider_name,
        base_url,
        error.message,
        start_time,
        error.code,
        error.action,
        error.retryable,
    )

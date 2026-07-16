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
        return _error_result(
            "anthropic", base_url, "API Key 不能为空", start, "authentication_error"
        )
    if not model_id.strip():
        return _error_result(
            "anthropic",
            base_url,
            "测试 Anthropic 需要指定 model_id",
            start,
            "invalid_request_error",
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
    except anthropic.AuthenticationError:
        return _error_result(
            "anthropic",
            base_url,
            "API Key 无效、已过期或已撤销",
            start,
            "authentication_error",
        )
    except anthropic.PermissionDeniedError:
        return _error_result(
            "anthropic",
            base_url,
            "API Key 无权访问该模型或资源",
            start,
            "permission_error",
        )
    except anthropic.NotFoundError:
        return _error_result(
            "anthropic",
            base_url,
            "请求的模型不存在，请检查是否使用官方模型 ID",
            start,
            "not_found_error",
        )
    except anthropic.RateLimitError:
        return _error_result(
            "anthropic",
            base_url,
            "已达到 Anthropic 速率或加速限制，请稍后重试",
            start,
            "rate_limit_error",
        )
    except anthropic.APITimeoutError:
        return _error_result(
            "anthropic",
            base_url,
            "Anthropic 请求超时，请检查网络或增大超时时间",
            start,
            "timeout_error",
        )
    except anthropic.BadRequestError as exception:
        if _is_context_limit_error(exception):
            return _error_result(
                "anthropic",
                base_url,
                "请求超过模型上下文或输出限制，请缩短输入或降低输出上限",
                start,
                "context_length_error",
            )
        return _error_result(
            "anthropic",
            base_url,
            "请求参数或消息格式不受支持",
            start,
            "invalid_request_error",
        )
    except anthropic.APIConnectionError:
        return _error_result(
            "anthropic",
            base_url,
            "无法连接到服务器，请检查网络或 base_url",
            start,
            "connection_error",
        )
    except Exception:
        return _error_result(
            "anthropic",
            base_url,
            "Anthropic 连接测试失败",
            start,
            "provider_error",
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
    except openai.AuthenticationError:
        return _error_result("openai_compatible", base_url, "API Key 无效或已过期", start)
    except openai.NotFoundError:
        return _error_result("openai_compatible", base_url, "请求的模型不存在，请检查 model_id", start)
    except openai.APIConnectionError:
        return _error_result("openai_compatible", base_url, "无法连接到服务器，请检查网络或 base_url", start)
    except Exception:
        return _error_result("openai_compatible", base_url, "OpenAI 兼容连接测试失败", start)


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
            return ConnectionTestResult(
                success=False,
                provider_name="openai_compatible",
                provider_type="openai",
                base_url=base_url,
                available_models=[],
                error_message="测试 OpenAI 兼容服务需要指定 model_id",
            )
        return check_openai_compatible_connection(api_key, base_url, model_id, timeout)
    else:
        return ConnectionTestResult(
            success=False,
            provider_name=provider_type,
            provider_type=provider_type,
            base_url=base_url,
            available_models=[],
            error_message=f"不支持的 provider 类型: {provider_type}",
        )


def _error_result(
    provider_name: str,
    base_url: str,
    message: str,
    start_time: float,
    error_code: str = "",
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
        response_time_ms=elapsed,
    )


def _is_context_limit_error(exception: anthropic.BadRequestError) -> bool:
    """Anthropic 将上下文超限归为通用 invalid_request_error。"""
    body = getattr(exception, "body", None)
    normalized = f"{body or ''} {exception}".lower()
    markers = (
        "context window",
        "context length",
        "too many input tokens",
        "prompt is too long",
        "maximum context",
        "input length",
    )
    return any(marker in normalized for marker in markers)

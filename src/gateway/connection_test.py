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
    response_time_ms: float = 0.0


def check_anthropic_connection(
    api_key: str,
    base_url: str,
    model_id: str = "claude-sonnet-4-5-20241022",
    timeout: int = 30,
) -> ConnectionTestResult:
    """测试 Anthropic Messages API 连通性"""
    import time

    start = time.time()
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
    except anthropic.AuthenticationError as e:
        return _error_result("anthropic", base_url, "API Key 无效或已过期", e, start)
    except anthropic.NotFoundError as e:
        return _error_result("anthropic", base_url, "请求的模型不存在，请检查 base_url 或 model_id", e, start)
    except anthropic.APIConnectionError as e:
        return _error_result("anthropic", base_url, "无法连接到服务器，请检查网络或 base_url", e, start)
    except Exception as e:
        return _error_result("anthropic", base_url, f"测试失败: {e}", e, start)


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
    except openai.AuthenticationError as e:
        return _error_result("openai_compatible", base_url, "API Key 无效或已过期", e, start)
    except openai.NotFoundError as e:
        return _error_result("openai_compatible", base_url, "请求的模型不存在，请检查 model_id", e, start)
    except openai.APIConnectionError as e:
        return _error_result("openai_compatible", base_url, "无法连接到服务器，请检查网络或 base_url", e, start)
    except Exception as e:
        return _error_result("openai_compatible", base_url, f"测试失败: {e}", e, start)


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
    exception: Exception,
    start_time: float,
) -> ConnectionTestResult:
    import time

    elapsed = (time.time() - start_time) * 1000
    error = f"{message}"
    if str(exception) and str(exception) != message:
        error += f" ({exception})"
    return ConnectionTestResult(
        success=False,
        provider_name=provider_name,
        provider_type="unknown",
        base_url=base_url,
        available_models=[],
        error_message=error,
        response_time_ms=elapsed,
    )

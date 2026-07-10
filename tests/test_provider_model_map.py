"""Provider 模型映射单元测试"""
import pytest

from src.gateway.provider import AnthropicProvider, OpenAICompatibleProvider, create_provider
from src.models.schemas import ProviderConfig


def _kimi_config() -> ProviderConfig:
    return ProviderConfig(
        name="Kimi 转发服务",
        type="anthropic",
        base_url="https://api.va11.icu/",
        api_keys=["sk-test"],
        model_map={
            "claude-sonnet-5": "kimi-for-coding",
            "claude-sonnet-5-20251001": "kimi-for-coding",
            "claude-opus-4-8": "kimi-for-coding",
        },
    )


def test_anthropic_provider_model_mapping():
    provider = AnthropicProvider("kimi", _kimi_config())
    assert provider.map_model_id("claude-sonnet-5") == "kimi-for-coding"
    assert provider.map_model_id("claude-sonnet-5-20251001") == "kimi-for-coding"
    assert provider.map_model_id("claude-opus-4-8") == "kimi-for-coding"


def test_anthropic_provider_model_no_mapping():
    provider = AnthropicProvider(
        "anthropic",
        ProviderConfig(
            name="Anthropic",
            type="anthropic",
            base_url="https://api.anthropic.com",
            api_keys=["sk-test"],
        ),
    )
    assert provider.map_model_id("claude-sonnet-5") == "claude-sonnet-5"


def test_openai_provider_model_mapping():
    provider = OpenAICompatibleProvider(
        "glm",
        ProviderConfig(
            name="GLM",
            type="openai",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            api_keys=["sk-test"],
            model_map={"glm-4": "glm-4-0520"},
        ),
    )
    assert provider.map_model_id("glm-4") == "glm-4-0520"
    assert provider.map_model_id("glm-4-flash") == "glm-4-flash"


def test_factory_creates_provider_with_model_map():
    config = _kimi_config()
    provider = create_provider("kimi", config)
    assert isinstance(provider, AnthropicProvider)
    assert provider.map_model_id("claude-sonnet-5") == "kimi-for-coding"

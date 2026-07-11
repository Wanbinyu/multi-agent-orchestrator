"""Provider key 轮询与模型映射单元测试"""
from unittest.mock import MagicMock

import pytest

from src.gateway.provider import BaseProvider, create_provider
from src.models.schemas import ProviderConfig


class _FakeProvider(BaseProvider):
    """仅用于测试基类行为的简单实现"""

    def chat(self, messages, model_config, **kwargs):
        raise NotImplementedError


def test_key_rotation_cycles_through_keys():
    config = ProviderConfig(
        name="multi-key",
        type="anthropic",
        base_url="https://example.com",
        api_keys=["k1", "k2", "k3"],
    )
    provider = _FakeProvider("multi-key", config)

    assert provider.get_next_key() == "k1"
    assert provider.get_next_key() == "k2"
    assert provider.get_next_key() == "k3"
    assert provider.get_next_key() == "k1"


def test_key_rotation_raises_when_no_keys():
    config = ProviderConfig(
        name="no-key",
        type="anthropic",
        base_url="https://example.com",
        api_keys=[],
    )
    provider = _FakeProvider("no-key", config)

    with pytest.raises(ValueError, match="没有配置 API key"):
        provider.get_next_key()


def test_map_model_id_returns_mapped_value():
    config = ProviderConfig(
        name="kimi",
        type="anthropic",
        base_url="https://example.com",
        api_keys=["sk-test"],
        model_map={"claude-sonnet-5": "kimi-for-coding"},
    )
    provider = _FakeProvider("kimi", config)

    assert provider.map_model_id("claude-sonnet-5") == "kimi-for-coding"


def test_map_model_id_returns_original_when_key_missing():
    config = ProviderConfig(
        name="kimi",
        type="anthropic",
        base_url="https://example.com",
        api_keys=["sk-test"],
        model_map={"claude-sonnet-5": "kimi-for-coding"},
    )
    provider = _FakeProvider("kimi", config)

    assert provider.map_model_id("claude-opus-4-8") == "claude-opus-4-8"


def test_map_model_id_returns_original_when_model_map_empty():
    config = ProviderConfig(
        name="anthropic",
        type="anthropic",
        base_url="https://example.com",
        api_keys=["sk-test"],
    )
    provider = _FakeProvider("anthropic", config)

    assert provider.map_model_id("claude-sonnet-5") == "claude-sonnet-5"


def test_create_provider_raises_unsupported_type():
    config = MagicMock()
    config.type = "azure"

    with pytest.raises(ValueError, match="不支持的 provider 类型"):
        create_provider("azure", config)

"""本地 LLM Provider 测试"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.gateway.local_provider import LocalLlamaCppProvider, OllamaProvider
from src.models.schemas import ChatMessage, ModelConfig, ProviderConfig
from src.tools.tool_result import ToolResult


def _model_cfg() -> ModelConfig:
    return ModelConfig(provider="ollama", model_id="qwen2.5:7b")


# ---------- OllamaProvider ----------


def test_ollama_provider_defaults_key_when_empty():
    cfg = ProviderConfig(
        name="ollama",
        type="ollama",
        base_url="http://localhost:11434/v1",
        api_keys=[],
    )
    provider = OllamaProvider("ollama", cfg)
    assert provider.get_next_key() == "ollama"
    assert provider.get_next_key() == "ollama"  # 始终返回占位 key


def test_ollama_provider_uses_configured_key_when_present():
    cfg = ProviderConfig(
        name="ollama",
        type="ollama",
        base_url="http://localhost:11434/v1",
        api_keys=["key-a", "key-b"],
    )
    provider = OllamaProvider("ollama", cfg)
    assert provider.get_next_key() == "key-a"
    assert provider.get_next_key() == "key-b"
    assert provider.get_next_key() == "key-a"  # 轮换


def test_ollama_provider_is_openai_compatible():
    cfg = ProviderConfig(
        name="ollama",
        type="ollama",
        base_url="http://localhost:11434/v1",
        api_keys=[],
    )
    provider = OllamaProvider("ollama", cfg)
    # 继承自 OpenAICompatibleProvider
    from src.gateway.provider import OpenAICompatibleProvider

    assert isinstance(provider, OpenAICompatibleProvider)


# ---------- LocalLlamaCppProvider ----------


def _llamacpp_cfg(model_path: str = "/tmp/model.gguf", extra: dict | None = None) -> ProviderConfig:
    return ProviderConfig(
        name="local",
        type="llamacpp",
        base_url=model_path,
        api_keys=[],
        extra=extra or {},
    )


def test_llamacpp_missing_model_path():
    cfg = ProviderConfig(name="local", type="llamacpp", base_url="", api_keys=[])
    provider = LocalLlamaCppProvider("local", cfg)
    provider._ensure_loaded()
    assert provider._load_error is not None
    assert "模型路径" in provider._load_error


def test_llamacpp_missing_dependency():
    cfg = _llamacpp_cfg()
    provider = LocalLlamaCppProvider("local", cfg)
    with patch.dict("sys.modules", {"llama_cpp": None}):
        # 强制 ImportError
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "llama_cpp":
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            provider._ensure_loaded()
    assert provider._load_error is not None
    assert "llama-cpp-python" in provider._load_error


def test_llamacpp_chat_uses_loaded_model():
    cfg = _llamacpp_cfg()
    provider = LocalLlamaCppProvider("local", cfg)

    fake_llm = MagicMock()
    fake_llm.create_chat_completion.return_value = {
        "choices": [{"message": {"content": "你好"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
    }
    provider._llm = fake_llm  # 跳过懒加载

    messages = [ChatMessage(role="user", content="hi")]
    response = provider.chat(messages, _model_cfg())
    assert response.content == "你好"
    assert response.input_tokens == 5
    assert response.output_tokens == 2
    assert response.cost_usd == 0.0  # 本地模型不计费
    fake_llm.create_chat_completion.assert_called_once()


def test_llamacpp_chat_stream_yields_delta_and_usage():
    cfg = _llamacpp_cfg()
    provider = LocalLlamaCppProvider("local", cfg)

    fake_llm = MagicMock()
    fake_llm.create_chat_completion.return_value = iter([
        {"choices": [{"delta": {"content": "你"}}]},
        {"choices": [{"delta": {"content": "好"}}]},
        {"usage": {"prompt_tokens": 3, "completion_tokens": 2}},
    ])
    provider._llm = fake_llm

    messages = [ChatMessage(role="user", content="hi")]
    chunks = list(provider.chat_stream(messages, _model_cfg()))
    deltas = [c for c in chunks if c.type == "delta"]
    usages = [c for c in chunks if c.type == "usage"]
    assert len(deltas) == 2
    assert deltas[0].content == "你"
    assert deltas[1].content == "好"
    assert len(usages) == 1
    assert usages[0].input_tokens == 3


def test_llamacpp_chat_stream_fallback_usage_when_missing():
    cfg = _llamacpp_cfg()
    provider = LocalLlamaCppProvider("local", cfg)

    fake_llm = MagicMock()
    fake_llm.create_chat_completion.return_value = iter([
        {"choices": [{"delta": {"content": "hello world"}}]},
    ])
    provider._llm = fake_llm

    chunks = list(provider.chat_stream([ChatMessage(role="user", content="hi")], _model_cfg()))
    usages = [c for c in chunks if c.type == "usage"]
    assert len(usages) == 1
    assert usages[0].output_tokens > 0  # 兜底估算


# ---------- create_provider 工厂 ----------


def test_create_provider_ollama():
    from src.gateway.provider import create_provider

    cfg = ProviderConfig(
        name="ollama",
        type="ollama",
        base_url="http://localhost:11434/v1",
        api_keys=[],
    )
    provider = create_provider("ollama", cfg)
    assert isinstance(provider, OllamaProvider)


def test_create_provider_llamacpp():
    from src.gateway.provider import create_provider

    cfg = ProviderConfig(
        name="local",
        type="llamacpp",
        base_url="/tmp/m.gguf",
        api_keys=[],
    )
    provider = create_provider("local", cfg)
    assert isinstance(provider, LocalLlamaCppProvider)


def test_create_provider_unknown_type():
    from src.gateway.provider import create_provider

    cfg = ProviderConfig(name="x", type="anthropic", base_url="", api_keys=["k"])
    # type 是 Literal，构造非法类型需绕过校验
    cfg.type = "unknown"
    with pytest.raises(ValueError, match="不支持"):
        create_provider("x", cfg)

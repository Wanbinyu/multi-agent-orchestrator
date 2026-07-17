"""测试模型目录"""
import pytest
from pydantic import ValidationError

from src.models.catalog import (
    BUILTIN_MODELS,
    PROVIDER_TEMPLATES,
    find_models_for_template,
    get_default_model_for_template,
    get_model_catalog,
    get_provider_templates,
    list_models_by_provider,
    ModelCatalogEntry,
)
from src.models.schemas import ModelConfig


def test_catalog_contains_common_models():
    catalog = get_model_catalog()
    assert "glm-ark" in catalog
    assert "kimi-for-coding" in catalog
    assert "deepseek-chat" in catalog


def test_catalog_covers_mainstream_providers():
    """2026-07 扩充后，目录覆盖主流 Provider 的代表模型。"""
    catalog = get_model_catalog()
    for alias in (
        "gpt-5",
        "deepseek-v4-pro",
        "kimi-k2.7-code",
        "glm-5",
        "minimax-m2.7",
        "qwen3-coder-plus",
        "doubao-seed",
        "gemini-3.1-pro",
    ):
        assert alias in catalog, alias


def test_expanded_models_stay_unverified():
    """未逐项核实的扩充条目不声明已验证元数据。"""
    for alias in ("gpt-5", "gemini-3.1-pro", "glm-5"):
        entry = BUILTIN_MODELS[alias]
        assert entry.metadata_source == "unverified"
        assert set(entry.capability_status.values()) == {"unverified"}
        assert entry.context_window_tokens == 0


def test_all_template_models_exist_in_catalog():
    for key, template in PROVIDER_TEMPLATES.items():
        for alias in template["supported_models"]:
            assert alias in BUILTIN_MODELS, f"{key}: {alias}"


def test_model_entry_attributes():
    entry = BUILTIN_MODELS["glm-ark"]
    assert entry.alias == "glm-ark"
    assert entry.provider_type == "anthropic"
    assert entry.default_model_id == "ark-code-latest"
    assert "tool_use" in entry.capabilities
    assert entry.dynamic_model_alias is True
    assert entry.context_window_tokens == 0
    assert "unverified" in entry.context_window_source
    assert entry.capability_status["tool_use"] == "unverified"
    assert entry.metadata_source == "unverified"


def test_model_config_conversion():
    entry = BUILTIN_MODELS["glm-ark"]
    cfg = entry.to_model_config("ark")
    assert cfg["provider"] == "ark"
    assert cfg["model_id"] == "ark-code-latest"
    assert "capabilities" in cfg
    assert cfg["dynamic_model_alias"] is True
    assert cfg["capability_status"]["tool_use"] == "unverified"
    assert cfg["metadata_source"] == "unverified"


def test_official_anthropic_catalog_matches_verified_limits():
    sonnet = BUILTIN_MODELS["claude-sonnet-5"]
    assert sonnet.default_model_id == "claude-sonnet-5"
    assert sonnet.input_price_per_1m == 3.0
    assert sonnet.output_price_per_1m == 15.0
    assert sonnet.context_window_tokens == 1_000_000
    assert sonnet.max_output_tokens == 128_000
    assert sonnet.capability_status["vision"] == "unverified"
    assert sonnet.capability_status["tool_use"] == "unverified"
    assert sonnet.metadata_verified_at == "2026-07-16"

    haiku = BUILTIN_MODELS["claude-haiku-4-5"]
    assert haiku.default_model_id == "claude-haiku-4-5-20251001"
    assert haiku.context_window_tokens == 200_000
    assert haiku.max_output_tokens == 64_000


def test_legacy_capability_list_remains_compatible():
    cfg = ModelConfig(provider="p", model_id="m", capabilities=["tool_use"])
    assert cfg.supports_capability("tool_use") is True


@pytest.mark.parametrize("state", ["unverified", "unsupported"])
def test_unavailable_capability_is_not_enabled(state):
    cfg = ModelConfig(
        provider="p",
        model_id="m",
        capabilities=["tool_use"],
        capability_status={"tool_use": state},
    )
    assert cfg.supports_capability("tool_use") is False


def test_supported_capability_is_enabled():
    cfg = ModelConfig(
        provider="p",
        model_id="m",
        capability_status={"tool_use": "supported"},
    )
    assert cfg.supports_capability("tool_use") is True


def test_unknown_model_capability_is_unverified():
    cfg = ModelConfig(provider="p", model_id="unknown")
    assert cfg.get_capability_state("tool_use") == "unverified"
    assert cfg.supports_capability("tool_use") is False


def test_invalid_capability_state_is_rejected():
    with pytest.raises(ValidationError):
        ModelConfig(
            provider="p",
            model_id="m",
            capability_status={"tool_use": "maybe"},
        )


def test_invalid_metadata_date_is_rejected():
    with pytest.raises(ValidationError):
        ModelConfig(
            provider="p",
            model_id="m",
            metadata_source="provider_docs",
            metadata_verified_at="not-a-date",
        )


def test_invalid_catalog_capability_state_is_rejected():
    with pytest.raises(ValueError, match="无效能力状态"):
        ModelCatalogEntry(
            alias="bad",
            name="Bad",
            provider_type="openai",
            default_model_id="bad",
            capability_status={"tool_use": "maybe"},
        )


def test_provider_templates():
    templates = get_provider_templates()
    assert "volcengine_ark" in templates
    assert templates["volcengine_ark"]["type"] == "anthropic"


def test_find_models_for_template():
    models = find_models_for_template("volcengine_ark")
    aliases = [m.alias for m in models]
    assert "glm-ark" in aliases


def test_get_default_model_for_template():
    default = get_default_model_for_template("volcengine_ark")
    assert default == "glm-ark"


def test_list_models_by_provider():
    models = list_models_by_provider("openai")
    aliases = [m.alias for m in models]
    assert "deepseek-chat" in aliases

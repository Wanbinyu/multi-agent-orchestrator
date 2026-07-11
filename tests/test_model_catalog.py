"""测试模型目录"""
import pytest

from src.models.catalog import (
    BUILTIN_MODELS,
    PROVIDER_TEMPLATES,
    find_models_for_template,
    get_default_model_for_template,
    get_model_catalog,
    get_provider_templates,
    list_models_by_provider,
)


def test_catalog_contains_common_models():
    catalog = get_model_catalog()
    assert "glm-ark" in catalog
    assert "kimi-for-coding" in catalog
    assert "deepseek-chat" in catalog


def test_model_entry_attributes():
    entry = BUILTIN_MODELS["glm-ark"]
    assert entry.alias == "glm-ark"
    assert entry.provider_type == "anthropic"
    assert entry.default_model_id == "ark-code-latest"
    assert "tool_use" in entry.capabilities


def test_model_config_conversion():
    entry = BUILTIN_MODELS["glm-ark"]
    cfg = entry.to_model_config("ark")
    assert cfg["provider"] == "ark"
    assert cfg["model_id"] == "ark-code-latest"
    assert "capabilities" in cfg


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

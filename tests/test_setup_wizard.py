"""setup wizard / provider presets 单元测试"""
from src.cli.provider_presets import (
    PROVIDER_PRESETS,
    build_provider_config,
    build_providers_yaml,
    get_default_models_for_provider,
    validate_custom_provider,
)


def test_build_provider_config_anthropic():
    cfg, models, env_var = build_provider_config("anthropic", "sk-test")
    assert cfg["name"] == "Anthropic (Claude)"
    assert cfg["type"] == "anthropic"
    assert cfg["base_url"] == "https://api.anthropic.com"
    assert cfg["api_keys"] == ["${ANTHROPIC_API_KEY}"]
    assert "claude-sonnet-5" in models
    assert env_var == "ANTHROPIC_API_KEY"


def test_build_provider_config_kimi_has_model_map():
    cfg, models, env_var = build_provider_config("kimi", "sk-test")
    assert cfg["type"] == "anthropic"
    assert cfg["base_url"] == "https://api.va11.icu/"
    assert "model_map" in cfg
    assert cfg["model_map"]["claude-sonnet-5"] == "kimi-for-coding"
    assert "kimi-for-coding" in models
    assert env_var == "KIMI_API_KEY"


def test_build_provider_config_with_base_url_override():
    cfg, _, _ = build_provider_config("anthropic", "sk-test", base_url="https://proxy.example.com")
    assert cfg["base_url"] == "https://proxy.example.com"


def test_build_providers_yaml_multiple_providers():
    selected = [
        ("glm", "glm-key", None, None),
        ("deepseek", "ds-key", None, None),
    ]
    data, env_vars = build_providers_yaml(selected)

    assert "glm" in data["providers"]
    assert "deepseek" in data["providers"]
    assert "glm-4" in data["models"]
    assert "deepseek-v3" in data["models"]
    assert env_vars == {"GLM_API_KEY": "glm-key", "DEEPSEEK_API_KEY": "ds-key"}


def test_validate_custom_provider():
    assert validate_custom_provider("custom_anthropic", "https://api.example.com") is None
    assert validate_custom_provider("custom_anthropic", "") is not None
    assert validate_custom_provider("custom_anthropic", "ftp://example.com") is not None


def test_get_default_models_for_provider():
    models = get_default_models_for_provider("openai")
    assert "gpt-4o" in models
    assert "gpt-4o-mini" in models


def test_all_presets_have_required_fields():
    for key, preset in PROVIDER_PRESETS.items():
        assert preset["name"]
        assert preset["type"] in ("anthropic", "openai")
        assert preset["env_var"]
        # 自定义 provider 允许空 base_url 和空 models

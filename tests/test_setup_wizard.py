"""setup wizard / provider presets 单元测试"""
from src.cli.provider_presets import (
    PROVIDER_PRESETS,
    build_provider_config,
    build_providers_yaml,
    get_default_models_for_provider,
    validate_custom_provider,
)
from src.cli.setup_wizard import SCENARIOS


def test_build_provider_config_anthropic():
    cfg, models, env_var = build_provider_config("anthropic", "sk-test")
    assert cfg["name"] == "Anthropic (Claude)"
    assert cfg["type"] == "anthropic"
    assert cfg["base_url"] == "https://api.anthropic.com"
    assert cfg["api_keys"] == ["${ANTHROPIC_API_KEY}"]
    assert "claude-sonnet-5" in models
    assert models["claude-sonnet-5"]["model_id"] == "claude-sonnet-5"
    assert models["claude-sonnet-5"]["context_window_tokens"] == 1_000_000
    assert models["claude-sonnet-5"]["max_output_tokens"] == 128_000
    assert models["claude-sonnet-5"]["capability_status"]["tool_use"] == "unverified"
    assert models["claude-haiku-4-5"]["model_id"] == "claude-haiku-4-5-20251001"
    assert env_var == "ANTHROPIC_API_KEY"


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
    assert "glm-5" in data["models"]
    assert "deepseek-v4-pro" in data["models"]
    assert env_vars == {"GLM_API_KEY": "glm-key", "DEEPSEEK_API_KEY": "ds-key"}


def test_validate_custom_provider():
    assert validate_custom_provider("custom_anthropic", "https://api.example.com") is None
    assert validate_custom_provider("custom_anthropic", "") is not None
    assert validate_custom_provider("custom_anthropic", "ftp://example.com") is not None


def test_get_default_models_for_provider():
    models = get_default_models_for_provider("openai")
    assert models == ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]


def test_new_provider_presets_use_current_model_ids():
    assert get_default_models_for_provider("kimi_coding") == [
        "k3",
        "k3-256k",
        "kimi-for-coding",
        "kimi-for-coding-highspeed",
    ]
    assert get_default_models_for_provider("qwen") == [
        "qwen3.8-max-preview",
        "qwen3.7-max",
        "qwen3.7-plus",
        "qwen3.7-flash",
    ]


def test_scenario_defaults_do_not_use_retired_glm_model():
    defaults = [
        worker["default_model"]
        for scenario in SCENARIOS.values()
        for worker in scenario["workers"]
    ]
    assert "glm-4-flash" not in defaults
    assert "glm-5.2" in defaults


def test_all_presets_have_required_fields():
    for key, preset in PROVIDER_PRESETS.items():
        assert preset["name"]
        assert preset["type"] in ("anthropic", "openai")
        assert preset["env_var"]
        # 自定义 provider 允许空 base_url 和空 models


def test_preset_models_are_sourced_from_catalog():
    """CLI 预设的模型数据必须来自 catalog.py 单一真值源，不得硬编码漂移。"""
    from src.models.catalog import BUILTIN_MODELS

    for key, preset in PROVIDER_PRESETS.items():
        for alias, model_data in preset.get("models", {}).items():
            # 自定义 provider 可能在 catalog 之外追加模型，跳过未注册别名。
            if alias not in BUILTIN_MODELS:
                continue
            assert model_data == BUILTIN_MODELS[alias].to_model_data(), (
                f"preset '{key}' model '{alias}' 漂离 catalog 单一真值源"
            )

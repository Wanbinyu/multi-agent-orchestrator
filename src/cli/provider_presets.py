"""Provider 预设模板与生成逻辑"""
from __future__ import annotations

from copy import deepcopy

from src.models.catalog import BUILTIN_MODELS


ProviderPreset = dict


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "anthropic": {
        "name": "Anthropic (Claude)",
        "type": "anthropic",
        "base_url": "https://api.anthropic.com",
        "env_var": "ANTHROPIC_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in (
                "claude-fable-5",
                "claude-opus-4-8",
                "claude-sonnet-5",
                "claude-haiku-4-5",
            )
        },
    },
    "openai": {
        "name": "OpenAI",
        "type": "openai",
        "base_url": "https://api.openai.com/v1",
        "env_var": "OPENAI_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in (
                "gpt-5",
                "gpt-4o",
                "gpt-4o-mini",
            )
        },
    },
    "glm": {
        "name": "智谱 GLM",
        "type": "openai",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "env_var": "GLM_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in (
                "glm-5",
                "glm-4-flash",
            )
        },
    },
    "deepseek": {
        "name": "DeepSeek",
        "type": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "env_var": "DEEPSEEK_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in (
                "deepseek-v4-pro",
                "deepseek-v4-flash",
            )
        },
    },
    "ark": {
        "name": "火山方舟 Coding Plan",
        "type": "anthropic",
        "base_url": "https://ark.cn-beijing.volces.com/api/coding",
        "env_var": "ARK_API_KEY",
        "models": {
            alias: BUILTIN_MODELS[alias].to_model_data()
            for alias in (
                "glm-ark",
            )
        },
    },
    "custom_anthropic": {
        "name": "自定义 Anthropic 兼容服务",
        "type": "anthropic",
        "base_url": "",
        "env_var": "CUSTOM_ANTHROPIC_API_KEY",
        "models": {},
    },
    "custom_openai": {
        "name": "自定义 OpenAI 兼容服务",
        "type": "openai",
        "base_url": "",
        "env_var": "CUSTOM_OPENAI_API_KEY",
        "models": {},
    },
}


def list_provider_choices() -> list[tuple[str, str]]:
    """返回用于 questionary 的 (显示名, key) 列表"""
    return [(preset["name"], key) for key, preset in PROVIDER_PRESETS.items()]


def build_provider_config(
    key: str,
    api_key: str,
    base_url: str | None = None,
    custom_models: dict | None = None,
) -> tuple[dict, dict[str, dict], str]:
    """生成单个 provider 配置及其模型配置

    返回：
        provider_cfg: provider 段落配置
        models: {逻辑模型名: ModelConfig}
        env_var: 环境变量名
    """
    preset = deepcopy(PROVIDER_PRESETS[key])
    provider_cfg = {
        "name": preset["name"],
        "type": preset["type"],
        "base_url": base_url if base_url else preset["base_url"],
        "api_keys": [f"${{{preset['env_var']}}}"],
        "timeout": 120,
        "rpm_limit": 60,
    }

    # 模型映射
    if preset.get("model_map"):
        provider_cfg["model_map"] = preset["model_map"]

    # 模型配置
    models = custom_models if custom_models is not None else preset.get("models", {})
    model_configs = {}
    for model_name, model_data in models.items():
        model_configs[model_name] = {
            "provider": key,
            "model_id": model_data["model_id"],
            "input_price_per_1m": model_data.get("input_price_per_1m", 0.0),
            "output_price_per_1m": model_data.get("output_price_per_1m", 0.0),
            "capabilities": model_data.get("capabilities", []),
            "capability_status": model_data.get("capability_status", {}),
            "metadata_source": model_data.get("metadata_source", "unverified"),
            "metadata_verified_at": model_data.get("metadata_verified_at", ""),
            "context_window_tokens": model_data.get("context_window_tokens", 0),
            "max_output_tokens": model_data.get("max_output_tokens", 4096),
            "context_window_source": model_data.get("context_window_source", "unverified"),
            "context_window_verified_at": model_data.get("context_window_verified_at", ""),
        }

    return provider_cfg, model_configs, preset["env_var"]


def build_providers_yaml(
    selected: list[tuple[str, str, str | None, dict | None]],
) -> tuple[dict, dict[str, str]]:
    """根据用户选择的 provider 生成完整 providers.yaml 内容和所需环境变量

    selected 中每个元素为：(preset_key, api_key, base_url_override, custom_models)
    """
    providers: dict[str, dict] = {}
    models: dict[str, dict] = {}
    env_vars: dict[str, str] = {}

    for key, api_key, base_url_override, custom_models in selected:
        provider_cfg, model_configs, env_var = build_provider_config(
            key, api_key, base_url=base_url_override, custom_models=custom_models
        )
        providers[key] = provider_cfg
        models.update(model_configs)
        env_vars[env_var] = api_key

    return {"providers": providers, "models": models}, env_vars


def get_default_models_for_provider(provider_key: str) -> list[str]:
    """获取某个 provider 预设下的默认模型名列表"""
    preset = PROVIDER_PRESETS.get(provider_key, {})
    return list(preset.get("models", {}).keys())


def validate_custom_provider(key: str, base_url: str) -> str | None:
    """验证自定义 provider 输入是否合法"""
    preset = PROVIDER_PRESETS.get(key, {})
    if not base_url or not base_url.startswith(("http://", "https://")):
        return "base_url 必须以 http:// 或 https:// 开头"
    return None

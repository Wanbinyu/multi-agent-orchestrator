"""Provider 预设模板与生成逻辑"""
from __future__ import annotations

from copy import deepcopy


ProviderPreset = dict


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "anthropic": {
        "name": "Anthropic (Claude)",
        "type": "anthropic",
        "base_url": "https://api.anthropic.com",
        "env_var": "ANTHROPIC_API_KEY",
        "models": {
            "claude-fable-5": {
                "model_id": "claude-fable-5-20251001",
                "input_price_per_1m": 15.0,
                "output_price_per_1m": 75.0,
            },
            "claude-sonnet-5": {
                "model_id": "claude-sonnet-5-20251001",
                "input_price_per_1m": 3.0,
                "output_price_per_1m": 15.0,
            },
            "claude-haiku-4-5": {
                "model_id": "claude-haiku-4-5-20251001",
                "input_price_per_1m": 0.25,
                "output_price_per_1m": 1.25,
            },
        },
    },
    "openai": {
        "name": "OpenAI",
        "type": "openai",
        "base_url": "https://api.openai.com/v1",
        "env_var": "OPENAI_API_KEY",
        "models": {
            "gpt-4o": {
                "model_id": "gpt-4o",
                "input_price_per_1m": 5.0,
                "output_price_per_1m": 15.0,
            },
            "gpt-4o-mini": {
                "model_id": "gpt-4o-mini",
                "input_price_per_1m": 0.15,
                "output_price_per_1m": 0.6,
            },
        },
    },
    "glm": {
        "name": "智谱 GLM",
        "type": "openai",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "env_var": "GLM_API_KEY",
        "models": {
            "glm-4": {
                "model_id": "glm-4",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
            },
            "glm-4-flash": {
                "model_id": "glm-4-flash",
                "input_price_per_1m": 0.1,
                "output_price_per_1m": 0.1,
            },
        },
    },
    "deepseek": {
        "name": "DeepSeek",
        "type": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "env_var": "DEEPSEEK_API_KEY",
        "models": {
            "deepseek-v3": {
                "model_id": "deepseek-chat",
                "input_price_per_1m": 0.3,
                "output_price_per_1m": 1.2,
            },
            "deepseek-r1": {
                "model_id": "deepseek-reasoner",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 4.0,
            },
        },
    },
    "ark": {
        "name": "火山方舟 Coding Plan",
        "type": "anthropic",
        "base_url": "https://ark.cn-beijing.volces.com/api/coding",
        "env_var": "ARK_API_KEY",
        "models": {
            "glm-ark": {
                "model_id": "ark-code-latest",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
            },
        },
    },
    "kimi": {
        "name": "Kimi 转发服务（via CCswitch）",
        "type": "anthropic",
        "base_url": "https://api.va11.icu/",
        "env_var": "KIMI_API_KEY",
        "model_map": {
            "claude-sonnet-5": "kimi-for-coding",
            "claude-sonnet-5-20251001": "kimi-for-coding",
            "claude-opus-4-8": "kimi-for-coding",
            "claude-opus-4-8-20251001": "kimi-for-coding",
            "claude-haiku-4-5": "kimi-for-coding",
            "claude-haiku-4-5-20251001": "kimi-for-coding",
            "claude-fable-5": "kimi-for-coding",
            "claude-fable-5-20251001": "kimi-for-coding",
        },
        "models": {
            "kimi-for-coding": {
                "model_id": "kimi-for-coding",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
            },
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

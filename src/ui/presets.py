"""UI 层使用的 Provider 预设模板

数据参考：
- src/cli/provider_presets.py（项目已有 CLI 预设）
- CCswitch https://github.com/farion1231/cc-switch 的 src/config/*ProviderPresets.ts

这里只保留最常用的国内/国际 Provider，字段与 providers.yaml 直接兼容。
"""
from __future__ import annotations

from copy import deepcopy


UI_PROVIDER_PRESETS: dict[str, dict] = {
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
                "capabilities": ["coding", "reasoning", "vision", "tool_use"],
            },
            "claude-sonnet-5": {
                "model_id": "claude-sonnet-5-20251001",
                "input_price_per_1m": 3.0,
                "output_price_per_1m": 15.0,
                "capabilities": ["coding", "reasoning", "vision", "tool_use"],
            },
            "claude-haiku-4-5": {
                "model_id": "claude-haiku-4-5-20251001",
                "input_price_per_1m": 0.25,
                "output_price_per_1m": 1.25,
                "capabilities": ["chat", "vision"],
            },
        },
    },
    "openai": {
        "name": "OpenAI",
        "type": "openai",
        "base_url": "https://api.openai.com/v1",
        "env_var": "OPENAI_API_KEY",
        "models": {
            "gpt-5": {
                "model_id": "gpt-5",
                "input_price_per_1m": 5.0,
                "output_price_per_1m": 15.0,
                "capabilities": ["coding", "reasoning", "vision", "tool_use"],
            },
            "gpt-4o": {
                "model_id": "gpt-4o",
                "input_price_per_1m": 5.0,
                "output_price_per_1m": 15.0,
                "capabilities": ["coding", "reasoning", "vision", "tool_use"],
            },
            "gpt-4o-mini": {
                "model_id": "gpt-4o-mini",
                "input_price_per_1m": 0.15,
                "output_price_per_1m": 0.6,
                "capabilities": ["chat", "vision"],
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
                "capabilities": ["coding", "tool_use", "reasoning"],
            },
            "glm-chat": {
                "model_id": "ark-chat-latest",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["chat", "tool_use"],
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
                "capabilities": ["coding", "tool_use", "reasoning"],
            },
        },
    },
    "glm": {
        "name": "智谱 GLM",
        "type": "openai",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "env_var": "GLM_API_KEY",
        "models": {
            "glm-5": {
                "model_id": "glm-5",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 1.0,
                "capabilities": ["coding", "reasoning", "tool_use"],
            },
            "glm-4-flash": {
                "model_id": "glm-4-flash",
                "input_price_per_1m": 0.1,
                "output_price_per_1m": 0.1,
                "capabilities": ["chat"],
            },
        },
    },
    "deepseek": {
        "name": "DeepSeek",
        "type": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "env_var": "DEEPSEEK_API_KEY",
        "models": {
            "deepseek-v4-pro": {
                "model_id": "deepseek-v4-pro",
                "input_price_per_1m": 1.0,
                "output_price_per_1m": 4.0,
                "capabilities": ["coding", "reasoning"],
            },
            "deepseek-v4-flash": {
                "model_id": "deepseek-v4-flash",
                "input_price_per_1m": 0.3,
                "output_price_per_1m": 1.2,
                "capabilities": ["coding", "chat"],
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


def list_presets() -> list[dict]:
    """返回前端下拉框需要的预设列表"""
    return [
        {"key": key, "name": preset["name"], "type": preset["type"]}
        for key, preset in UI_PROVIDER_PRESETS.items()
    ]


def get_preset(key: str) -> dict:
    """获取某个预设的完整副本"""
    if key not in UI_PROVIDER_PRESETS:
        raise KeyError(f"未知预设: {key}")
    return deepcopy(UI_PROVIDER_PRESETS[key])


def get_env_var_name(provider_name: str) -> str:
    """根据 provider 名生成环境变量名"""
    return f"{provider_name.upper().replace('-', '_')}_API_KEY"


def build_default_provider_name(preset_key: str, existing_names: set[str]) -> str:
    """生成不重复的 provider 名"""
    base = preset_key.replace("_", "-")
    name = base
    counter = 1
    while name in existing_names:
        name = f"{base}-{counter}"
        counter += 1
    return name


def expand_preset_models(preset_key: str) -> list[dict]:
    """把预设里的模型展开为前端表格可用的对象列表"""
    preset = get_preset(preset_key)
    return [
        {
            "alias": alias,
            "model_id": data["model_id"],
            "input_price_per_1m": data.get("input_price_per_1m", 0.0),
            "output_price_per_1m": data.get("output_price_per_1m", 0.0),
            "capabilities": data.get("capabilities", []),
        }
        for alias, data in preset.get("models", {}).items()
    ]

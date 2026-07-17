"""Provider 预设注册中心

设计目标：内置常用 Provider + 运行时加载用户自定义预设，方便后续不断新增模型
或用户自己部署的模型。

添加一个新的内置预设，只需在 src/ui/presets/builtin/ 下新建一个 .py 文件，
定义 PRESET 字典并调用 register_preset(key, PRESET)。

用户自定义预设可放在 config/presets/*.json 或 *.yaml，格式与 PRESET 相同。
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


UI_PROVIDER_PRESETS: dict[str, dict[str, Any]] = {}


def register_preset(key: str, preset: dict[str, Any]) -> None:
    """注册一个 Provider 预设

    preset 结构示例：
    {
        "name": "显示名称",
        "type": "anthropic" | "openai",
        "base_url": "https://...",
        "env_var": "PROVIDER_API_KEY",
        "model_map": {"逻辑名": "上游真实模型名"},  # 可选
        "models": {
            "alias": {
                "model_id": "...",
                "input_price_per_1m": 0.0,
                "output_price_per_1m": 0.0,
                "capabilities": ["coding"],
                "capability_status": {"coding": "unverified"},
                "metadata_source": "unverified",
                "metadata_verified_at": "",
            }
        },
    }
    """
    if not key or not isinstance(preset, dict):
        raise ValueError("preset key 和 preset dict 不能为空")
    if key in UI_PROVIDER_PRESETS:
        raise ValueError(f"preset key 已存在: {key}")
    required = {"name", "type", "base_url", "env_var"}
    missing = required - set(preset.keys())
    if missing:
        raise ValueError(f"preset {key} 缺少字段: {missing}")
    UI_PROVIDER_PRESETS[key] = deepcopy(preset)


def unregister_preset(key: str) -> None:
    """注销预设（主要用于测试）"""
    UI_PROVIDER_PRESETS.pop(key, None)


def list_presets() -> list[dict[str, str]]:
    """返回前端下拉框需要的预设列表"""
    return [
        {"key": key, "name": preset["name"], "type": preset["type"]}
        for key, preset in UI_PROVIDER_PRESETS.items()
    ]


def get_preset(key: str) -> dict[str, Any]:
    """获取某个预设的完整副本"""
    if key not in UI_PROVIDER_PRESETS:
        raise KeyError(f"未知预设: {key}")
    return deepcopy(UI_PROVIDER_PRESETS[key])


def expand_preset_models(preset_key: str) -> list[dict[str, Any]]:
    """把预设里的模型展开为前端表格可用的对象列表"""
    preset = get_preset(preset_key)
    return [
        {
            "alias": alias,
            "model_id": data["model_id"],
            "input_price_per_1m": data.get("input_price_per_1m", 0.0),
            "output_price_per_1m": data.get("output_price_per_1m", 0.0),
            "capabilities": data.get("capabilities", []),
            "capability_status": data.get("capability_status") or {
                capability: "unverified"
                for capability in data.get("capabilities", [])
            },
            "metadata_source": data.get("metadata_source", "unverified"),
            "metadata_verified_at": data.get("metadata_verified_at", ""),
            "context_window_tokens": data.get("context_window_tokens", 0),
            "max_output_tokens": data.get("max_output_tokens", 4096),
            "context_safety_ratio": data.get("context_safety_ratio", 0.08),
            "compaction_threshold": data.get("compaction_threshold", 0.75),
            "context_window_source": data.get("context_window_source", "unverified"),
            "context_window_verified_at": data.get("context_window_verified_at", ""),
            "dynamic_model_alias": data.get("dynamic_model_alias", False),
        }
        for alias, data in preset.get("models", {}).items()
    ]


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


def load_user_presets(directory: str | None = None) -> None:
    """从 config/presets/ 加载用户自定义预设（JSON/YAML）"""
    if directory is None:
        directory = "config/presets"
    path = Path(directory)
    if not path.exists():
        return
    for file in sorted(path.iterdir()):
        if file.suffix not in (".json", ".yaml", ".yml"):
            continue
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) if file.suffix != ".json" else json.load(f)
        except Exception as e:
            print(f"[ui-presets] 加载自定义预设失败 {file}: {e}")
            continue
        if not isinstance(data, dict):
            continue
        # 支持两种写法：文件名为 key，或文件内包含 key 字段
        key = data.pop("key", None) or file.stem
        register_preset(key, data)


# 加载内置预设
from src.ui.presets.builtin import (  # noqa: E402
    anthropic,
    ark,
    ark_coding,
    azure_openai,
    baidu_qianfan,
    custom_anthropic,
    custom_openai,
    deepseek,
    gemini,
    kimi,
    minimax,
    openai,
    openrouter,
    qwen,
    siliconflow,
    stepfun,
    zhipu_glm,
)

# 加载用户自定义预设（如果存在）
load_user_presets()

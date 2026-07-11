"""providers.yaml / .env 的读写管理

为 UI 提供原子化配置操作，保证 CLI 与 UI 双向兼容。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = "config/providers.yaml"
DEFAULT_ENV_PATH = ".env"


def _resolve_config_path(config_path: str | None) -> str:
    return config_path if config_path is not None else DEFAULT_CONFIG_PATH


def _resolve_env_path(env_path: str | None) -> str:
    return env_path if env_path is not None else DEFAULT_ENV_PATH


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """加载 providers.yaml，不存在时返回空骨架"""
    path = Path(_resolve_config_path(config_path))
    if not path.exists():
        return {"providers": {}, "models": {}, "main_model": None}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {
        "providers": data.get("providers", {}),
        "models": data.get("models", {}),
        "main_model": data.get("main_model"),
    }


def save_yaml(config_path: str | None, data: dict[str, Any]) -> None:
    """保存 providers.yaml"""
    path = Path(_resolve_config_path(config_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def _env_var_name(provider_name: str) -> str:
    return f"{provider_name.upper().replace('-', '_')}_API_KEY"


def _read_env_lines(env_path: Path) -> list[str]:
    if not env_path.exists():
        return []
    with open(env_path, "r", encoding="utf-8") as f:
        return f.readlines()


def _write_env_lines(env_path: Path, lines: list[str]) -> None:
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def save_api_key(env_path: str | None, provider_name: str, api_key: str) -> None:
    """将 API Key 写入 .env"""
    path = Path(_resolve_env_path(env_path))
    var_name = _env_var_name(provider_name)
    line = f"{var_name}={api_key}\n"
    lines = _read_env_lines(path)
    updated = False
    new_lines: list[str] = []
    for existing in lines:
        if existing.startswith(f"{var_name}="):
            new_lines.append(line)
            updated = True
        else:
            new_lines.append(existing)
    if not updated:
        new_lines.append(line)
    _write_env_lines(path, new_lines)
    os.environ[var_name] = api_key


def delete_api_key(env_path: str | None, provider_name: str) -> None:
    """从 .env 删除某个 provider 的 key"""
    path = Path(_resolve_env_path(env_path))
    var_name = _env_var_name(provider_name)
    lines = _read_env_lines(path)
    new_lines = [line for line in lines if not line.startswith(f"{var_name}=")]
    _write_env_lines(path, new_lines)
    os.environ.pop(var_name, None)


def get_api_key(env_path: str | None, provider_name: str) -> str | None:
    """从 .env 读取 API Key，优先环境变量"""
    var_name = _env_var_name(provider_name)
    value = os.environ.get(var_name)
    if value:
        return value
    path = Path(_resolve_env_path(env_path))
    if not path.exists():
        return None
    for line in _read_env_lines(path):
        if line.startswith(f"{var_name}="):
            return line.split("=", 1)[1].strip()
    return None


def save_provider(
    config_path: str | None,
    env_path: str | None,
    provider_name: str,
    display_name: str,
    provider_type: str,
    base_url: str,
    api_key: str,
    timeout: int,
    models: list[dict[str, Any]],
    model_map: dict[str, str] | None = None,
    rpm_limit: int = 60,
    set_as_main: bool = False,
) -> None:
    """新增或更新一个 Provider，同时更新 .env 中的 API Key"""
    cfg = load_config(config_path)

    provider_cfg: dict[str, Any] = {
        "name": display_name,
        "type": provider_type,
        "base_url": base_url,
        "api_keys": [f"${{{_env_var_name(provider_name)}}}"],
        "timeout": timeout,
        "rpm_limit": rpm_limit,
    }
    if model_map:
        provider_cfg["model_map"] = model_map

    cfg["providers"][provider_name] = provider_cfg

    # 更新模型配置：先删除该 provider 原有的模型
    cfg["models"] = {
        alias: data
        for alias, data in cfg["models"].items()
        if data.get("provider") != provider_name
    }
    for m in models:
        alias = m["alias"]
        cfg["models"][alias] = {
            "provider": provider_name,
            "model_id": m["model_id"],
            "input_price_per_1m": float(m.get("input_price_per_1m", 0.0)),
            "output_price_per_1m": float(m.get("output_price_per_1m", 0.0)),
            "capabilities": m.get("capabilities", []),
        }

    if set_as_main or not cfg.get("main_model"):
        if models:
            cfg["main_model"] = models[0]["alias"]

    save_yaml(config_path, cfg)
    save_api_key(env_path, provider_name, api_key)


def delete_provider(config_path: str | None, env_path: str | None, provider_name: str) -> None:
    """删除 Provider 及其所属模型"""
    cfg = load_config(config_path)
    cfg["providers"].pop(provider_name, None)
    cfg["models"] = {
        alias: data
        for alias, data in cfg["models"].items()
        if data.get("provider") != provider_name
    }
    if cfg.get("main_model") and cfg["main_model"] not in cfg["models"]:
        cfg["main_model"] = next(iter(cfg["models"]), None)
    save_yaml(config_path, cfg)
    delete_api_key(env_path, provider_name)


def set_main_model(config_path: str | None, model_alias: str) -> None:
    """设置主模型"""
    cfg = load_config(config_path)
    if model_alias not in cfg.get("models", {}):
        raise ValueError(f"未知模型别名: {model_alias}")
    cfg["main_model"] = model_alias
    save_yaml(config_path, cfg)

"""Provider 配置相关 API 路由"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.gateway.connection_test import check_provider_connection
from src.ui import config_manager
from src.ui.presets import (
    build_default_provider_name,
    expand_preset_models,
    get_env_var_name,
    get_preset,
    list_presets,
)

router = APIRouter()


class ModelEntry(BaseModel):
    alias: str = Field(..., min_length=1)
    model_id: str = Field(..., min_length=1)
    input_price_per_1m: float = 0.0
    output_price_per_1m: float = 0.0
    capabilities: list[str] = Field(default_factory=list)


class ProviderForm(BaseModel):
    preset_key: str
    provider_name: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    base_url: str
    api_key: str = Field(..., min_length=1)
    timeout: int = 120
    models: list[ModelEntry] = Field(..., min_length=1)
    set_as_main: bool = False

    @field_validator("base_url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url 必须以 http:// 或 https:// 开头")
        return value


class TestConnectionForm(BaseModel):
    provider_type: str
    base_url: str
    api_key: str = Field(..., min_length=1)
    model_id: str = Field(..., min_length=1)
    timeout: int = 30


class MainModelForm(BaseModel):
    alias: str


@router.get("/api/presets")
def get_presets() -> dict[str, Any]:
    return {"presets": list_presets()}


@router.get("/api/presets/{preset_key}")
def get_preset_detail(preset_key: str) -> dict[str, Any]:
    try:
        preset = get_preset(preset_key)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "key": preset_key,
        "preset": preset,
        "default_models": expand_preset_models(preset_key),
        "default_provider_name": build_default_provider_name(
            preset_key, set(config_manager.load_config().get("providers", {}).keys())
        ),
        "env_var": get_env_var_name(preset_key),
    }


@router.get("/api/config")
def get_config() -> dict[str, Any]:
    cfg = config_manager.load_config()
    # API Key 不返回给前端
    providers: dict[str, Any] = {}
    for name, data in cfg.get("providers", {}).items():
        masked = dict(data)
        masked["api_keys"] = ["${...}"]
        masked["env_var"] = get_env_var_name(name)
        providers[name] = masked
    return {
        "providers": providers,
        "models": cfg.get("models", {}),
        "main_model": cfg.get("main_model"),
    }


@router.post("/api/config/providers")
def create_or_update_provider(form: ProviderForm) -> dict[str, Any]:
    cfg = config_manager.load_config()
    if form.provider_name in cfg.get("providers", {}) and form.set_as_main:
        pass

    preset = get_preset(form.preset_key)
    model_map = preset.get("model_map")

    try:
        config_manager.save_provider(
            config_path=config_manager.DEFAULT_CONFIG_PATH,
            env_path=config_manager.DEFAULT_ENV_PATH,
            provider_name=form.provider_name,
            display_name=form.display_name,
            provider_type=preset["type"],
            base_url=form.base_url,
            api_key=form.api_key,
            timeout=form.timeout,
            models=[m.model_dump() for m in form.models],
            model_map=model_map,
            set_as_main=form.set_as_main,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True, "provider": form.provider_name}


@router.delete("/api/config/providers/{provider_name}")
def remove_provider(provider_name: str) -> dict[str, Any]:
    cfg = config_manager.load_config()
    if provider_name not in cfg.get("providers", {}):
        raise HTTPException(status_code=404, detail=f"Provider {provider_name} 不存在")
    config_manager.delete_provider(
        config_path=config_manager.DEFAULT_CONFIG_PATH,
        env_path=config_manager.DEFAULT_ENV_PATH,
        provider_name=provider_name,
    )
    return {"success": True}


@router.post("/api/config/providers/{provider_name}/test")
def test_provider(provider_name: str, payload: TestConnectionForm) -> dict[str, Any]:
    """测试 Provider 连通性

    若 payload 中未提供 api_key，则尝试从 .env 读取。
    """
    api_key = payload.api_key or config_manager.get_api_key(
        config_manager.DEFAULT_ENV_PATH, provider_name
    )
    if not api_key:
        raise HTTPException(status_code=400, detail="缺少 API Key")

    result = check_provider_connection(
        provider_type=payload.provider_type,
        api_key=api_key,
        base_url=payload.base_url,
        model_id=payload.model_id,
        timeout=payload.timeout,
    )
    return {
        "success": result.success,
        "provider": result.provider_name,
        "base_url": result.base_url,
        "error_message": result.error_message,
        "response_time_ms": round(result.response_time_ms, 1),
    }


@router.post("/api/config/main_model")
def update_main_model(form: MainModelForm) -> dict[str, Any]:
    try:
        config_manager.set_main_model(config_manager.DEFAULT_CONFIG_PATH, form.alias)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "main_model": form.alias}

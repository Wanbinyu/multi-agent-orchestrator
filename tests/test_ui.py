"""UI 配置接口测试

使用 FastAPI TestClient 验证 Provider CRUD、连通性测试与主模型设置。
实际网络请求会被 mock，避免消耗真实 API Key。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.ui.app import app
from src.ui import config_manager


@pytest.fixture
def client(monkeypatch, tmp_path):
    """返回配置隔离到临时目录的 TestClient"""
    config_path = tmp_path / "providers.yaml"
    env_path = tmp_path / ".env"
    monkeypatch.setattr(config_manager, "DEFAULT_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(config_manager, "DEFAULT_ENV_PATH", str(env_path))
    # 重新加载路由以应用新的默认路径
    return TestClient(app)


class TestPages:
    def test_index_returns_html(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        assert "模型连接配置" in res.text

    def test_health(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}

    def test_web_app_loads_dotenv_before_chat_router(self):
        source = Path("src/ui/app.py").read_text(encoding="utf-8")
        assert source.index("load_dotenv()") < source.index(
            "from src.ui.routers import chat"
        )


class TestPresets:
    def test_list_presets(self, client):
        res = client.get("/api/presets")
        assert res.status_code == 200
        data = res.json()
        keys = {p["key"] for p in data["presets"]}
        assert "anthropic" in keys
        assert "openai" in keys
        assert "ark" in keys
        assert "custom-openai" in keys
        assert "custom-anthropic" in keys
        assert "kimi" in keys
        assert "deepseek" in keys
        assert "zhipu-glm" in keys

    def test_get_preset_detail(self, client):
        res = client.get("/api/presets/openai")
        assert res.status_code == 200
        data = res.json()
        assert data["key"] == "openai"
        assert data["preset"]["type"] == "openai"
        assert any(m["alias"] == "gpt-4o" for m in data["default_models"])

    def test_get_unknown_preset_404(self, client):
        res = client.get("/api/presets/not-exist")
        assert res.status_code == 404


class TestProviderCrud:
    def test_create_provider_and_mask_key(self, client, tmp_path):
        payload = {
            "preset_key": "openai",
            "provider_name": "openai-main",
            "display_name": "OpenAI Main",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test",
            "timeout": 60,
            "models": [
                {
                    "alias": "gpt-4o",
                    "model_id": "gpt-4o",
                    "input_price_per_1m": 5.0,
                    "output_price_per_1m": 15.0,
                    "capabilities": ["coding"],
                    "context_window_tokens": 128000,
                    "max_output_tokens": 8192,
                    "context_safety_ratio": 0.1,
                    "compaction_threshold": 0.7,
                    "context_window_source": "user_config",
                }
            ],
            "set_as_main": True,
        }
        res = client.post("/api/config/providers", json=payload)
        assert res.status_code == 200
        assert res.json()["success"] is True

        # key 被写入 .env
        env_text = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "OPENAI_MAIN_API_KEY=sk-test" in env_text

        # 配置读取时 key 被掩码
        res = client.get("/api/config")
        cfg = res.json()
        assert cfg["providers"]["openai-main"]["api_keys"] == ["${...}"]
        assert cfg["models"]["gpt-4o"]["provider"] == "openai-main"
        assert cfg["models"]["gpt-4o"]["context_window_tokens"] == 128000
        assert cfg["models"]["gpt-4o"]["max_output_tokens"] == 8192
        assert cfg["models"]["gpt-4o"]["compaction_threshold"] == 0.7
        assert cfg["main_model"] == "gpt-4o"

    def test_rejects_invalid_context_budget_fields(self, client):
        payload = {
            "preset_key": "openai",
            "provider_name": "bad-budget",
            "display_name": "Bad Budget",
            "base_url": "https://api.openai.com/v1",
            "api_key": "k",
            "models": [{
                "alias": "x",
                "model_id": "x",
                "context_window_tokens": 32000,
                "max_output_tokens": 4096,
                "context_safety_ratio": 0.8,
            }],
        }
        res = client.post("/api/config/providers", json=payload)
        assert res.status_code == 422

    def test_validation_rejects_bad_url(self, client):
        payload = {
            "preset_key": "openai",
            "provider_name": "bad",
            "display_name": "Bad",
            "base_url": "not-a-url",
            "api_key": "k",
            "timeout": 60,
            "models": [{"alias": "x", "model_id": "x"}],
        }
        res = client.post("/api/config/providers", json=payload)
        assert res.status_code == 422
        assert "http" in res.text or "base_url" in res.text

    def test_delete_provider(self, client):
        payload = {
            "preset_key": "openai",
            "provider_name": "to-delete",
            "display_name": "To Delete",
            "base_url": "https://api.openai.com/v1",
            "api_key": "k",
            "timeout": 60,
            "models": [{"alias": "m1", "model_id": "x"}],
        }
        client.post("/api/config/providers", json=payload)

        res = client.delete("/api/config/providers/to-delete")
        assert res.status_code == 200

        cfg = client.get("/api/config").json()
        assert "to-delete" not in cfg["providers"]
        assert "m1" not in cfg["models"]


class TestConnection:
    def test_test_connection_success(self, client, monkeypatch):
        called = {}

        def fake_check(provider_type, api_key, base_url, model_id, timeout=30):
            called.update(
                {
                    "provider_type": provider_type,
                    "api_key": api_key,
                    "base_url": base_url,
                    "model_id": model_id,
                }
            )
            from src.gateway.connection_test import ConnectionTestResult

            return ConnectionTestResult(
                success=True,
                provider_name="openai",
                provider_type="openai",
                base_url=base_url,
                available_models=[],
                response_time_ms=123.4,
            )

        monkeypatch.setattr("src.ui.routers.providers.check_provider_connection", fake_check)

        res = client.post(
            "/api/config/providers/openai-main/test",
            json={
                "provider_type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-123",
                "model_id": "gpt-4o",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["response_time_ms"] == 123.4
        assert called["api_key"] == "sk-123"

    def test_test_connection_failure(self, client, monkeypatch):
        from src.gateway.connection_test import ConnectionTestResult

        def fake_check(*args, **kwargs):
            return ConnectionTestResult(
                success=False,
                provider_name="openai",
                provider_type="openai",
                base_url="https://x",
                available_models=[],
                error_message="鉴权失败",
            )

        monkeypatch.setattr("src.ui.routers.providers.check_provider_connection", fake_check)
        res = client.post(
            "/api/config/providers/x/test",
            json={
                "provider_type": "openai",
                "base_url": "https://x",
                "api_key": "bad",
                "model_id": "m",
            },
        )
        data = res.json()
        assert data["success"] is False
        assert "鉴权失败" in data["error_message"]


class TestMainModel:
    def test_set_main_model(self, client):
        payload = {
            "preset_key": "openai",
            "provider_name": "openai-main",
            "display_name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "api_key": "k",
            "timeout": 60,
            "models": [
                {"alias": "gpt-4o", "model_id": "gpt-4o"},
                {"alias": "gpt-4o-mini", "model_id": "gpt-4o-mini"},
            ],
        }
        client.post("/api/config/providers", json=payload)

        res = client.post("/api/config/main_model", json={"alias": "gpt-4o-mini"})
        assert res.status_code == 200
        assert res.json()["main_model"] == "gpt-4o-mini"

        cfg = client.get("/api/config").json()
        assert cfg["main_model"] == "gpt-4o-mini"

    def test_set_unknown_main_model_400(self, client):
        res = client.post("/api/config/main_model", json={"alias": "not-exist"})
        assert res.status_code == 400

"""Web 对话路由单元测试"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.models.schemas import ChatResponse
from src.ui.app import app
from src.ui.routers import chat as chat_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    """每个测试使用独立会话目录与 mock 网关"""
    from src.core.session import SessionStore

    monkeypatch.setattr(chat_router, "store", SessionStore(base_dir=str(tmp_path / "sessions")))

    mock_gateway = MagicMock()
    mock_gateway.chat_with_main_model.return_value = ChatResponse(
        content="收到",
        model="glm",
        provider="ark",
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.0001,
    )
    monkeypatch.setattr(chat_router, "gateway", mock_gateway)

    return TestClient(app)


def test_chat_page(client):
    r = client.get("/chat")
    assert r.status_code == 200
    assert "对话模式" in r.text


def test_create_and_list_sessions(client):
    r = client.post("/api/chat/sessions", json={"title": "测试会话"})
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "测试会话"
    session_id = data["session_id"]

    r = client.get("/api/chat/sessions")
    assert r.status_code == 200
    sessions = r.json()["sessions"]
    assert any(s["id"] == session_id for s in sessions)


def test_get_session_not_found(client):
    r = client.get("/api/chat/sessions/nonexistent")
    assert r.status_code == 404


def test_send_message(client):
    created = client.post("/api/chat/sessions", json={"title": ""}).json()
    session_id = created["session_id"]

    r = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"message": "你好"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == session_id
    assert data["user_message"] == "你好"
    assert data["assistant_message"] == "收到"
    assert data["input_tokens"] == 10


def test_send_message_not_found(client):
    r = client.post(
        "/api/chat/sessions/nonexistent/messages",
        json={"message": "你好"},
    )
    assert r.status_code == 404


def test_delete_session(client):
    created = client.post("/api/chat/sessions", json={"title": "待删除"}).json()
    session_id = created["session_id"]

    r = client.delete(f"/api/chat/sessions/{session_id}")
    assert r.status_code == 200
    assert r.json()["success"] is True

    r = client.get(f"/api/chat/sessions/{session_id}")
    assert r.status_code == 404


def test_delete_session_not_found(client):
    r = client.delete("/api/chat/sessions/nonexistent")
    assert r.status_code == 404

"""Web 对话路由单元测试"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.models.schemas import ChatResponse, ModelConfig
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
    mock_gateway.main_model = "glm"
    mock_gateway.get_model_config.return_value = ModelConfig(
        provider="ark",
        model_id="ark-code-latest",
        dynamic_model_alias=True,
    )
    monkeypatch.setattr(chat_router, "gateway", mock_gateway)

    return TestClient(app)


def test_chat_page(client):
    r = client.get("/chat")
    assert r.status_code == 200
    assert "对话模式" in r.text
    assert 'id="tab-files"' in r.text
    assert 'id="project-tree"' in r.text
    assert 'id="file-preview"' in r.text


def test_project_directory_is_sorted_and_ignores_heavy_directories(client, tmp_path):
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "node_modules").mkdir()
    (project / ".hidden").mkdir()
    (project / "b.txt").write_text("b", encoding="utf-8")
    (project / "a.txt").write_text("a", encoding="utf-8")

    r = client.post(
        "/api/chat/project/directory",
        json={"path": str(project)},
    )

    assert r.status_code == 200
    data = r.json()
    assert data["path"] == str(project.resolve())
    assert [entry["name"] for entry in data["entries"]] == ["src", "a.txt", "b.txt"]
    assert data["entries"][0]["is_dir"] is True
    assert "node_modules" in data["ignored_directories"]


def test_project_directory_can_include_hidden_and_reports_truncation(client, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env.example").write_text("KEY=value", encoding="utf-8")
    (project / "a.txt").write_text("a", encoding="utf-8")

    r = client.post(
        "/api/chat/project/directory",
        json={"path": str(project), "include_hidden": True, "max_entries": 1},
    )

    assert r.status_code == 200
    assert r.json()["entries"][0]["name"] == ".env.example"
    assert r.json()["truncated"] is True
    assert r.json()["scan_limit"] == 5000


def test_project_file_preview_is_limited_and_rejects_binary(client, tmp_path):
    text_file = tmp_path / "long.txt"
    text_file.write_text("abcdefghij" * 20, encoding="utf-8")
    binary_file = tmp_path / "binary.bin"
    binary_file.write_bytes(b"abc\x00def")

    preview = client.post(
        "/api/chat/project/file",
        json={"path": str(text_file), "max_chars": 100},
    )
    binary = client.post(
        "/api/chat/project/file",
        json={"path": str(binary_file)},
    )

    assert preview.status_code == 200
    assert len(preview.json()["content"]) == 100
    assert preview.json()["size"] == 200
    assert preview.json()["truncated"] is True
    assert binary.status_code == 415


def test_project_browser_reports_invalid_targets(client, tmp_path):
    missing = client.post(
        "/api/chat/project/directory",
        json={"path": str(tmp_path / "missing")},
    )
    wrong_type = client.post(
        "/api/chat/project/file",
        json={"path": str(tmp_path)},
    )

    assert missing.status_code == 404
    assert wrong_type.status_code == 400


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


def test_context_status_is_local_and_explainable(client):
    session_id = client.post("/api/chat/sessions", json={"title": "context"}).json()["session_id"]
    response = client.get(f"/api/chat/sessions/{session_id}/context")

    assert response.status_code == 200
    data = response.json()
    assert data["model_alias"] == "glm"
    assert data["context_window_tokens"] == 0
    assert data["context_window_source"] == "unverified_default"
    assert data["input_budget_tokens"] == 32000 - 4096 - 512
    assert any("动态模型别名" in warning for warning in data["warnings"])
    chat_router.gateway.chat_with_main_model.assert_not_called()


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
    assert data["run_id"]
    assert data["engineering"]["intent"]["kind"] == "unclassified"
    assert data["engineering"]["intent"]["policy"]["allow_project_writes"] is False

    runs = client.get(f"/api/chat/sessions/{session_id}/runs")
    detail = client.get(
        f"/api/chat/sessions/{session_id}/runs/{data['run_id']}"
    )
    assert runs.status_code == 200
    assert runs.json()["runs"][0]["status"] == "completed"
    assert detail.status_code == 200
    assert detail.json()["run_id"] == data["run_id"]


def test_failed_sync_message_persists_session_and_journal(client):
    created = client.post("/api/chat/sessions", json={"title": "sync failure"}).json()
    session_id = created["session_id"]
    chat_router.gateway.chat_with_main_model.side_effect = RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"message": "检查项目"},
        )

    saved_session = client.get(f"/api/chat/sessions/{session_id}").json()
    assert any(
        message["role"] == "user" and message["content"] == "检查项目"
        for message in saved_session["messages"]
    )
    runs = client.get(f"/api/chat/sessions/{session_id}/runs").json()["runs"]
    assert runs[0]["status"] == "failed"


def test_run_journal_routes_report_missing_records(client):
    created = client.post("/api/chat/sessions", json={"title": "run"}).json()
    session_id = created["session_id"]
    missing_run = client.get(f"/api/chat/sessions/{session_id}/runs/missing")
    missing_session = client.get("/api/chat/sessions/missing/runs")

    assert missing_run.status_code == 404
    assert missing_session.status_code == 404


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

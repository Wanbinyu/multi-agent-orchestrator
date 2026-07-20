"""Web 对话路由单元测试"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.core.engineering import RunJournalStore, WorkPlan, WorkPlanStep
from src.gateway.errors import ProviderError
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
    assert 'id="btn-plan-mode"' in r.text
    assert 'id="plan-mode-panel"' in r.text
    assert 'id="recovery-banner"' in r.text
    assert 'id="btn-recovery-continue"' in r.text
    assert 'id="toggle-adversarial"' in r.text


def test_permission_response_rejects_unknown_request(client):
    agent = MagicMock()
    agent.respond_to_permission.return_value = False
    chat_router.active_agents["active-session"] = agent
    try:
        response = client.post(
            "/api/chat/sessions/active-session/permission/missing",
            json={"approved": True},
        )
    finally:
        chat_router.active_agents.pop("active-session", None)

    assert response.status_code == 404
    assert response.json()["detail"] == "权限请求不存在或已经处理"


def test_plan_mode_api_persists_revision_and_approval_handoff(client):
    created = client.post("/api/chat/sessions", json={"title": "plan"}).json()
    session_id = created["session_id"]
    endpoint = f"/api/chat/sessions/{session_id}/plan"

    entered = client.post(
        endpoint, json={"action": "enter", "objective": "refactor auth"}
    )
    assert entered.status_code == 200
    assert entered.json()["state"] == "pending"
    assert client.get(endpoint).json()["artifact"]["objective"] == "refactor auth"

    session = chat_router.store.load(session_id)
    session.activate_plan_mode()
    session.save_plan_artifact("1. inspect\n2. implement\n3. test")
    chat_router.store.save(session)

    revised = client.post(
        endpoint, json={"action": "revise", "feedback": "add rollback"}
    )
    assert revised.status_code == 200
    assert revised.json()["state"] == "active"

    session = chat_router.store.load(session_id)
    session.save_plan_artifact("final approved plan")
    chat_router.store.save(session)
    approved = client.post(endpoint, json={"action": "approve"})

    assert approved.status_code == 200
    payload = approved.json()
    assert payload["state"] == "inactive"
    assert "final approved plan" in payload["implementation_request"]


def test_plan_mode_api_rejects_invalid_transition(client):
    created = client.post("/api/chat/sessions", json={"title": "plan"}).json()
    response = client.post(
        f"/api/chat/sessions/{created['session_id']}/plan",
        json={"action": "approve"},
    )
    assert response.status_code == 409


def test_interrupted_web_session_requires_explicit_recovery_without_provider(client):
    created = client.post("/api/chat/sessions", json={"title": "recovery"}).json()
    session_id = created["session_id"]
    session = chat_router.store.load(session_id)
    runs = RunJournalStore.from_output_dir(session.output_dir)
    interrupted = runs.create(session_id, "build app", "auto")
    interrupted.plan = WorkPlan(
        objective="build app",
        status="in_progress",
        steps=[
            WorkPlanStep(id="done", title="shell", status="completed"),
            WorkPlanStep(id="todo", title="routes", status="in_progress"),
        ],
    )
    interrupted.files_changed = ["src/shell.js"]
    runs.save(interrupted)

    detail = client.get(f"/api/chat/sessions/{session_id}")
    blocked_send = client.post(
        f"/api/chat/sessions/{session_id}/messages", json={"message": "继续"}
    )
    blocked_stream = client.post(
        f"/api/chat/sessions/{session_id}/messages/stream", json={"message": "继续"}
    )

    assert detail.json()["recovery"]["required"] is True
    assert detail.json()["recovery"]["unfinished_step_count"] == 1
    assert blocked_send.status_code == 409
    assert blocked_stream.status_code == 409
    chat_router.gateway.chat_with_main_model.assert_not_called()

    confirmed = client.post(
        f"/api/chat/sessions/{session_id}/recovery", json={"action": "continue"}
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["recovery"]["required"] is False
    chat_router.gateway.chat_with_main_model.assert_not_called()

    continued = client.post(
        f"/api/chat/sessions/{session_id}/messages", json={"message": "继续完成路由"}
    )
    assert continued.status_code == 200
    latest = runs.load(continued.json()["run_id"])
    assert latest.metrics["recovery"]["completed_step_ids"] == ["done"]
    assert latest.metrics["recovery"]["unfinished_step_ids"] == ["todo"]
    assert chat_router.gateway.chat_with_main_model.call_count == 1


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


def test_execution_depth_api_persists_preference_without_provider_call(client):
    session_id = client.post("/api/chat/sessions", json={"title": "depth"}).json()[
        "session_id"
    ]

    response = client.post(
        f"/api/chat/sessions/{session_id}/depth",
        json={"depth": "deep"},
    )

    assert response.status_code == 200
    assert response.json()["depth"] == "deep"
    assert chat_router.store.load(session_id).execution_depth == "deep"
    assert client.get(f"/api/chat/sessions/{session_id}").json()[
        "execution_depth"
    ] == "deep"
    chat_router.gateway.chat_with_main_model.assert_not_called()


def test_model_routing_api_persists_fixed_constraint_without_provider_call(client):
    session_id = client.post("/api/chat/sessions", json={"title": "routing"}).json()[
        "session_id"
    ]

    response = client.post(
        f"/api/chat/sessions/{session_id}/routing",
        json={"mode": "fixed"},
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "fixed"
    assert chat_router.store.load(session_id).model_routing_mode == "fixed"
    assert client.get(f"/api/chat/sessions/{session_id}").json()[
        "model_routing_mode"
    ] == "fixed"
    chat_router.gateway.chat_with_main_model.assert_not_called()


def test_adversarial_testing_api_is_explicit_and_local(client):
    session_id = client.post(
        "/api/chat/sessions", json={"title": "adversarial"}
    ).json()["session_id"]

    initial = client.get(f"/api/chat/sessions/{session_id}").json()
    enabled = client.post(
        f"/api/chat/sessions/{session_id}/adversarial",
        json={"enabled": True},
    )

    assert initial["adversarial_testing"] is False
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True
    assert chat_router.store.load(session_id).adversarial_testing is True
    assert client.get(f"/api/chat/sessions/{session_id}").json()[
        "adversarial_testing"
    ] is True
    chat_router.gateway.chat_with_main_model.assert_not_called()


def test_adversarial_testing_api_rejects_mid_turn_change(client):
    session_id = client.post(
        "/api/chat/sessions", json={"title": "active"}
    ).json()["session_id"]
    chat_router.active_agents[session_id] = MagicMock()
    try:
        response = client.post(
            f"/api/chat/sessions/{session_id}/adversarial",
            json={"enabled": True},
        )
    finally:
        chat_router.active_agents.pop(session_id, None)

    assert response.status_code == 409
    assert chat_router.store.load(session_id).adversarial_testing is False


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


def test_unconfigured_web_can_load_setup_page_and_reports_chat_configuration_gap(
    client, monkeypatch
):
    monkeypatch.setattr(chat_router, "gateway", None)

    def missing_gateway():
        raise FileNotFoundError("config/providers.yaml")

    monkeypatch.setattr(chat_router, "GatewayClient", missing_gateway)
    session_id = client.post("/api/chat/sessions", json={"title": "first run"}).json()["session_id"]

    assert client.get("/").status_code == 200
    response = client.get(f"/api/chat/sessions/{session_id}/context")
    assert response.status_code == 409
    assert "连接配置" in response.json()["detail"]


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
    policy = data["engineering"]["intent"]["policy"]
    assert policy["allow_project_writes"] is False
    assert policy["permission_follows_session"] is True

    runs = client.get(f"/api/chat/sessions/{session_id}/runs")
    detail = client.get(
        f"/api/chat/sessions/{session_id}/runs/{data['run_id']}"
    )
    assert runs.status_code == 200
    assert runs.json()["runs"][0]["status"] == "completed"
    assert detail.status_code == 200
    assert detail.json()["run_id"] == data["run_id"]
    # Web 展开详情依赖的完整字段（renderRunDetail 消费这些键）
    detail_payload = detail.json()
    for key in (
        "objective",
        "intent",
        "plan",
        "evidence",
        "verification",
        "requirements",
        "audit",
        "decisions",
        "files_changed",
        "residual_risks",
        "metrics",
    ):
        assert key in detail_payload, key


def test_sync_message_registers_and_cleans_active_agent(client):
    session_id = client.post(
        "/api/chat/sessions", json={"title": "sync active"}
    ).json()["session_id"]
    response = chat_router.gateway.chat_with_main_model.return_value

    def assert_registered(*args, **kwargs):
        assert session_id in chat_router.active_agents
        return response

    chat_router.gateway.chat_with_main_model.side_effect = assert_registered

    result = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"message": "你好"},
    )

    assert result.status_code == 200
    assert session_id not in chat_router.active_agents


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
    assert session_id not in chat_router.active_agents


def test_sync_provider_error_has_structured_safe_web_response(client):
    created = client.post("/api/chat/sessions", json={"title": "provider"}).json()
    session_id = created["session_id"]
    chat_router.gateway.chat_with_main_model.side_effect = ProviderError(
        "authentication_error",
        provider="anthropic",
        model="claude",
        cause_type="AuthenticationError",
    )

    response = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"message": "回答你好"},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["error_code"] == "authentication_error"
    assert payload["error"]["retryable"] is False
    assert payload["detail"].startswith("[authentication_error]")
    runs = client.get(f"/api/chat/sessions/{session_id}/runs").json()["runs"]
    assert runs[0]["status"] == "failed"


def test_run_journal_routes_report_missing_records(client):
    created = client.post("/api/chat/sessions", json={"title": "run"}).json()
    session_id = created["session_id"]
    missing_run = client.get(f"/api/chat/sessions/{session_id}/runs/missing")
    missing_session = client.get("/api/chat/sessions/missing/runs")

    assert missing_run.status_code == 404
    assert missing_session.status_code == 404


def test_delivery_report_route_aggregates_all_session_runs_locally(client):
    created = client.post("/api/chat/sessions", json={"title": "report"}).json()
    session_id = created["session_id"]
    session = chat_router.store.load(session_id)
    run_store = RunJournalStore.from_output_dir(session.output_dir)
    journal = run_store.create(session_id, "检查项目", "auto")
    journal.finish("completed", metrics={"input_tokens": 12, "output_tokens": 3})
    run_store.save(journal)

    response = client.get(f"/api/chat/sessions/{session_id}/report?scope=session")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "session"
    assert payload["run_count"] == 1
    assert payload["metrics"]["input_tokens"] == 12
    assert payload["runs"][0]["run_id"] == journal.run_id


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


def test_active_session_rejects_parallel_messages_and_delete(client):
    created = client.post("/api/chat/sessions", json={"title": "active"}).json()
    session_id = created["session_id"]
    chat_router.active_agents[session_id] = MagicMock()
    try:
        sync_response = client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"message": "second"},
        )
        stream_response = client.post(
            f"/api/chat/sessions/{session_id}/messages/stream",
            json={"message": "second"},
        )
        delete_response = client.delete(f"/api/chat/sessions/{session_id}")
    finally:
        chat_router.active_agents.pop(session_id, None)

    assert sync_response.status_code == 409
    assert stream_response.status_code == 409
    assert delete_response.status_code == 409
    assert chat_router.store.exists(session_id)


def test_mode_update_persists_on_active_agent_session(client):
    created = client.post("/api/chat/sessions", json={"title": "mode"}).json()
    session_id = created["session_id"]
    active = MagicMock()
    active.session = chat_router.store.load(session_id)
    chat_router.active_agents[session_id] = active
    try:
        response = client.post(
            f"/api/chat/sessions/{session_id}/mode",
            json={"mode": "auto"},
        )
    finally:
        chat_router.active_agents.pop(session_id, None)

    assert response.status_code == 200
    assert active.approval_mode == "auto"
    assert active.session.approval_mode == "auto"
    assert chat_router.store.load(session_id).approval_mode == "auto"

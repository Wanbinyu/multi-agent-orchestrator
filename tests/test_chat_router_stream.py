"""Web 对话流式路由单元测试"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.models.schemas import StreamChunk
from src.ui.app import app
from src.ui.routers import chat as chat_router


def _async_chunks(*chunks: StreamChunk):
    async def _gen():
        for c in chunks:
            yield c

    return _gen()


@pytest.fixture
def client(tmp_path, monkeypatch):
    from src.core.session import SessionStore

    monkeypatch.setattr(
        chat_router, "store", SessionStore(base_dir=str(tmp_path / "sessions"))
    )

    mock_gateway = MagicMock()
    mock_gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(
            type="failover",
            from_model="glm-ark",
            to_model="kimi-for-coding",
            reason="429 quota",
        ),
        StreamChunk(type="delta", content="收到"),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5, cost_usd=0.0001),
    )
    monkeypatch.setattr(chat_router, "gateway", mock_gateway)

    return TestClient(app)


def _parse_sse(response) -> list[tuple[str, dict]]:
    events = []
    current_event = "message"
    for raw_line in response.iter_lines():
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if not line:
            continue
        if line.startswith("event:"):
            current_event = line[6:].strip()
        elif line.startswith("data:"):
            data = json.loads(line[5:].strip())
            events.append((current_event, data))
    return events


def test_send_message_stream(client):
    created = client.post("/api/chat/sessions", json={"title": ""}).json()
    session_id = created["session_id"]

    with client.stream(
        "POST",
        f"/api/chat/sessions/{session_id}/messages/stream",
        json={"message": "你好"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse(response)
        assert any(
            e == "model_failover"
            and d["failover"]["from_model"] == "glm-ark"
            and d["failover"]["to_model"] == "kimi-for-coding"
            for e, d in events
        )
        assert any(e == "delta" and d["delta"] == "收到" for e, d in events)
        engineering = [d for e, d in events if e.startswith("engineering_")]
        assert [d["engineering"]["status"] for d in engineering] == [
            "running",
            "completed",
        ]

        done = [d for e, d in events if e == "done"][0]
        assert done["assistant_message"] == "收到"
        assert done["input_tokens"] == 10
        assert done["output_tokens"] == 5


def test_send_message_stream_not_found(client):
    response = client.post(
        "/api/chat/sessions/nonexistent/messages/stream",
        json={"message": "你好"},
    )
    assert response.status_code == 404


def test_failed_stream_persists_messages_and_failed_journal(client, monkeypatch):
    created = client.post("/api/chat/sessions", json={"title": "failed"}).json()
    session_id = created["session_id"]

    async def _broken_stream(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")
        yield  # pragma: no cover

    chat_router.gateway.chat_with_main_model_stream.side_effect = _broken_stream

    with client.stream(
        "POST",
        f"/api/chat/sessions/{session_id}/messages/stream",
        json={"message": "只分析，不修改文件"},
    ) as response:
        events = _parse_sse(response)

    engineering = [d["engineering"] for e, d in events if e.startswith("engineering_")]
    assert [item["status"] for item in engineering] == ["running", "failed"]
    assert any(e == "error" and "provider unavailable" in d["error"] for e, d in events)

    saved_session = client.get(f"/api/chat/sessions/{session_id}").json()
    assert any(
        message["role"] == "user" and message["content"] == "只分析，不修改文件"
        for message in saved_session["messages"]
    )
    runs = client.get(f"/api/chat/sessions/{session_id}/runs").json()["runs"]
    assert runs[0]["status"] == "failed"

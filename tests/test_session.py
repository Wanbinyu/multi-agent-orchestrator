"""Session 单元测试"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.core.session import Session, SessionStore
from src.models.schemas import ChatMessage, ToolUseContentBlock


def test_create_session(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))
    session = store.create(title="测试会话")

    assert session.title == "测试会话"
    assert session.messages == []
    assert (tmp_path / f"{session.id}.yaml").exists()
    assert (tmp_path / session.id / "output").exists()


def test_save_and_load_session(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))
    session = store.create()
    session.add_message("system", "你是助手")
    session.add_message("user", "你好")

    store.save(session)
    loaded = store.load(session.id)

    assert loaded.id == session.id
    assert len(loaded.messages) == 2
    assert loaded.messages[0].role == "system"
    assert loaded.messages[1].content == "你好"


def test_list_sessions(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))
    s1 = store.create(title="A")
    s1.updated_at = "2020-01-01T00:00:00+00:00"
    store.save(s1)
    s2 = store.create(title="B")
    s2.updated_at = "2021-01-01T00:00:00+00:00"
    store.save(s2)

    sessions = store.list()
    assert len(sessions) == 2
    # 默认按 updated_at 倒序，不依赖同毫秒创建时的 id 字典序
    assert sessions[0].id == s2.id
    assert sessions[1].id == s1.id


def test_delete_session(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))
    session = store.create()
    sid = session.id

    store.delete(sid)
    assert not (tmp_path / f"{sid}.yaml").exists()
    assert not (tmp_path / sid).exists()


def test_session_yaml_is_human_readable(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))
    session = store.create(title="可读")
    session.add_message("user", "你好")
    store.save(session)

    text = (tmp_path / f"{session.id}.yaml").read_text(encoding="utf-8")
    assert "messages:" in text
    assert "你好" in text


def test_session_persists_safe_blocks_but_not_provider_private_state(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))
    session = store.create(title="native")
    session.add_message(
        "assistant",
        "调用 read_file",
        content_blocks=[ToolUseContentBlock(
            id="toolu_session_1",
            name="read_file",
            input={"path": "README.md"},
        )],
        provider_payload=[{
            "type": "thinking",
            "thinking": "private chain of thought",
            "signature": "secret-signature",
        }],
    )

    store.save(session)
    text = (tmp_path / f"{session.id}.yaml").read_text(encoding="utf-8")
    loaded = store.load(session.id)

    assert "private chain of thought" not in text
    assert "secret-signature" not in text
    assert loaded.messages[0].content_blocks[0].type == "tool_use"
    assert loaded.messages[0].provider_payload == []


def test_add_message_updates_updated_at():
    import time

    session = Session(
        id="x",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        output_dir="sessions/x/output",
    )
    old = session.updated_at
    time.sleep(0.005)
    session.add_message("user", "hi")
    assert session.updated_at != old
    assert isinstance(session.messages[-1], ChatMessage)


def test_load_missing_session_raises(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))
    with pytest.raises(FileNotFoundError):
        store.load("not-exist")


def test_plan_mode_state_persists_and_requires_approval(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))
    session = store.create("plan")

    session.enter_plan_mode("refactor auth")
    session.activate_plan_mode()
    session.save_plan_artifact("1. inspect\n2. implement\n3. test")
    store.save(session)
    loaded = store.load(session.id)

    assert loaded.plan_mode == "awaiting_approval"
    assert loaded.plan_artifact is not None
    assert loaded.plan_artifact.revision == 1
    assert loaded.approve_plan().startswith("1. inspect")
    assert loaded.plan_mode == "inactive"


def test_plan_revision_returns_to_active_state(tmp_path):
    store = SessionStore(base_dir=str(tmp_path))
    session = store.create("plan")
    session.enter_plan_mode("build")
    session.save_plan_artifact("draft")

    session.request_plan_revision("add rollback")

    assert session.plan_mode == "active"
    assert session.plan_artifact is not None
    assert session.plan_artifact.feedback == "add rollback"

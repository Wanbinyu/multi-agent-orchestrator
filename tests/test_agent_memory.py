"""Agent 长期记忆注入相关测试"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.agent import Agent
from src.core.memory import MemoryStore
from src.core.session import Session
from src.models.schemas import ChatResponse


def _make_session(tmp_path) -> Session:
    return Session(
        id="test-session",
        title="test",
        created_at="2026-07-12T00:00:00+00:00",
        updated_at="2026-07-12T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
    )


def _mock_gateway(*responses: str) -> MagicMock:
    gateway = MagicMock()
    gateway.chat_with_main_model.side_effect = [
        ChatResponse(
            content=r,
            model="glm",
            provider="ark",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.0001,
        )
        for r in responses
    ]
    return gateway


@pytest.fixture
def memory_store(tmp_path) -> MemoryStore:
    config_path = tmp_path / "memory.yaml"
    config_path.write_text(
        f"enabled: true\nstorage_path: {tmp_path / 'memory'}\n", encoding="utf-8"
    )
    return MemoryStore(config_path=str(config_path))


def test_agent_injects_memory_into_system_prompt(tmp_path, memory_store: MemoryStore):
    session = _make_session(tmp_path)
    memory_store.add(category="preference", content="用户偏好中文回复")
    gateway = _mock_gateway("好的，我用中文回复。")
    agent = Agent(gateway, session, memory_store=memory_store)

    agent.run_turn("你好")

    system_msg = session.messages[0]
    assert system_msg.role == "system"
    assert "用户偏好中文回复" in system_msg.content


def test_agent_rebuilds_system_prompt_per_turn(tmp_path, memory_store: MemoryStore):
    session = _make_session(tmp_path)
    memory_store.add(category="preference", content="中文")
    gateway = _mock_gateway("回复一", "回复二")
    agent = Agent(gateway, session, memory_store=memory_store)

    agent.run_turn("你好")
    memory_store.add(category="decision", content="技术栈使用 FastAPI")

    # 重置 gateway 响应以进行第二轮
    gateway.chat_with_main_model.side_effect = [
        ChatResponse(
            content="回复二",
            model="glm",
            provider="ark",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.0001,
        )
    ]
    agent.run_turn("技术栈")

    assert "使用 FastAPI" in session.messages[0].content


def test_agent_no_memory_store_does_not_inject(tmp_path):
    session = _make_session(tmp_path)
    gateway = _mock_gateway("你好")
    agent = Agent(gateway, session)

    agent.run_turn("你好")

    assert "【项目记忆与上下文】" not in session.messages[0].content


def test_agent_memory_disabled(tmp_path, memory_store: MemoryStore):
    session = _make_session(tmp_path)
    memory_store.add(category="preference", content="中文")
    memory_store.config.enabled = False
    gateway = _mock_gateway("你好")
    agent = Agent(gateway, session, memory_store=memory_store)

    agent.run_turn("你好")

    assert "中文" not in session.messages[0].content


def test_agent_prompt_includes_search_tool_instructions(tmp_path):
    session = _make_session(tmp_path)
    gateway = _mock_gateway("你好")
    agent = Agent(gateway, session)

    agent.run_turn("你好")

    assert "search_project_files" in session.messages[0].content
    assert "search_memory" in session.messages[0].content

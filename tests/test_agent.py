"""Agent 单元测试"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.agent import Agent
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


def test_run_turn_no_tools(tmp_path):
    session = _make_session(tmp_path)
    gateway = _mock_gateway("你好，有什么可以帮你？")
    agent = Agent(gateway, session)

    result = agent.run_turn("你好")

    assert result.assistant_message == "你好，有什么可以帮你？"
    assert len(session.messages) == 3  # system + user + assistant
    assert session.messages[1].role == "user"
    assert session.messages[2].role == "assistant"


def test_run_turn_with_read_file_tool(tmp_path):
    session = _make_session(tmp_path)
    # 第一次模型请求读文件；第二次模型给出总结
    target = tmp_path / "output" / "hello.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("Python 是一门优雅的编程语言。", encoding="utf-8")

    gateway = _mock_gateway(
        '```tool:read_file\n{"path": "hello.txt"}\n```',
        "Python 是一门优雅的编程语言。",
    )
    agent = Agent(gateway, session)

    result = agent.run_turn("总结 hello.txt")

    assert result.tool_calls
    assert result.tool_calls[0]["tool"] == "read_file"
    assert result.tool_calls[0]["success"] is True
    assert "Python 是一门优雅的编程语言" in result.assistant_message
    # 消息历史包含 assistant 原始回复 + tool results user + 最终 assistant
    assert any(m.role == "user" and "[工具 read_file" in m.content for m in session.messages)


def test_run_turn_respects_max_tool_iterations(tmp_path):
    session = _make_session(tmp_path)
    # 每次都返回工具调用，测试最多循环 max_tool_iterations 次
    gateway = _mock_gateway(*(['```tool:read_file\n{"path": "a.txt"}\n```'] * 10))
    agent = Agent(gateway, session, max_tool_iterations=2)

    result = agent.run_turn("测试")

    # 初始调用 + 2 次工具循环 + 1 次最终总结 = 4 次模型调用
    assert gateway.chat_with_main_model.call_count == 4
    assert len(result.tool_calls) == 2


def test_run_turn_writes_code_blocks(tmp_path):
    session = _make_session(tmp_path)
    gateway = _mock_gateway('```python\nprint("hello")\n```')
    agent = Agent(gateway, session)

    result = agent.run_turn("写段代码")

    assert result.files_written
    # 新行为：不再自动抽取正文代码块为 generated_N 文件，仅兜底保存 response.md
    assert any("response.md" in f for f in result.files_written)
    assert not any("generated" in f for f in result.files_written)


def test_run_turn_costs_are_summed(tmp_path):
    session = _make_session(tmp_path)
    gateway = _mock_gateway(
        '```tool:read_file\n{"path": "a.txt"}\n```',
        "总结",
    )
    agent = Agent(gateway, session)

    result = agent.run_turn("两步")

    assert result.input_tokens == 20
    assert result.output_tokens == 10
    assert result.cost_usd == pytest.approx(0.0002)


def test_parse_tool_calls_standard_fence():
    content = '文本\n```tool:write_file\n{"path": "a.txt", "content": "hi"}\n```'
    calls = Agent._parse_tool_calls(content)
    assert len(calls) == 1
    assert calls[0]["tool"] == "write_file"
    assert calls[0]["params"]["path"] == "a.txt"


def test_parse_tool_calls_coding_model_special_token():
    """ark-coding / kimi-for-coding 用 <|tool_calls_section_end|> 闭合，应能解析"""
    content = (
        '我应该使用 write_file 工具。\n'
        '```tool:write_file\n'
        '{"path": "G:\\\\MAO_test\\\\login.html", "content": "<html></html>"}\n'
        '<|tool_calls_section_end|>'
    )
    calls = Agent._parse_tool_calls(content)
    assert len(calls) == 1
    assert calls[0]["tool"] == "write_file"
    assert calls[0]["params"]["path"] == "G:\\MAO_test\\login.html"


def test_strip_toolcall_artifacts():
    content = "前面<|tool_calls_section_start|>中间<|tool_calls_section_end|>后面"
    assert Agent._strip_toolcall_artifacts(content) == "前面中间后面"


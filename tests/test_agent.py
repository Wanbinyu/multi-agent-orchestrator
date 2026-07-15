"""Agent 单元测试"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.agent import Agent
from src.core.engineering import RunJournalStore
from src.core.session import Session
from src.models.schemas import ChatResponse, ModelConfig


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
    gateway.main_model = None
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


def test_context_status_and_system_prompt_use_runtime_facts(tmp_path):
    session = _make_session(tmp_path)
    gateway = _mock_gateway("unused")
    gateway.main_model = "glm-ark"
    gateway.get_model_config.return_value = ModelConfig(
        provider="volcengineark",
        model_id="ark-code-latest",
        max_context_tokens=131072,
    )
    agent = Agent(gateway, session)

    status = agent.get_context_status()
    prompt = agent._build_system_prompt()

    assert status["model_alias"] == "glm-ark"
    assert status["model_id"] == "ark-code-latest"
    assert status["max_context_tokens"] == 131072
    assert status["compaction_limit_tokens"] == 98304
    assert status["max_context_source"] == "model_config"
    assert "anthropic 仅表示 API 兼容协议" in prompt
    assert "不得猜测其他模型配置" in prompt


def test_context_status_uses_agent_default_when_model_has_no_limit(tmp_path):
    session = _make_session(tmp_path)
    gateway = _mock_gateway("unused")
    gateway.main_model = "glm-ark"
    gateway.get_model_config.return_value = ModelConfig(
        provider="volcengineark",
        model_id="ark-code-latest",
    )
    agent = Agent(gateway, session, max_context_tokens=32000)

    status = agent.get_context_status()

    assert status["max_context_tokens"] == 32000
    assert status["compaction_limit_tokens"] == 24000
    assert status["max_context_source"] == "agent_default"


def test_run_turn_no_tools(tmp_path):
    session = _make_session(tmp_path)
    gateway = _mock_gateway("你好，有什么可以帮你？")
    agent = Agent(gateway, session)

    result = agent.run_turn("你好")

    assert result.assistant_message == "你好，有什么可以帮你？"
    assert len(session.messages) == 3  # system + user + assistant
    assert session.messages[1].role == "user"
    assert session.messages[2].role == "assistant"
    journal = RunJournalStore.from_output_dir(session.output_dir).load(result.run_id)
    assert journal.status == "completed"
    assert result.engineering["run_id"] == result.run_id
    assert journal.metrics["input_tokens"] == 10


def test_auto_explain_task_rejects_model_write_attempt(tmp_path):
    session = _make_session(tmp_path)
    gateway = _mock_gateway(
        '```tool:write_file\n{"path": "should-not-exist.txt", "content": "bad"}\n```',
        "只读解释完成",
    )
    agent = Agent(gateway, session, approval_mode="auto")

    result = agent.run_turn("解释一下这段逻辑")

    assert result.engineering["intent"]["kind"] == "explain"
    assert result.engineering["intent"]["write_authorized"] is False
    assert result.tool_calls[0]["success"] is False
    assert "仅允许只读工具" in result.tool_calls[0]["error"]
    assert not (tmp_path / "output" / "should-not-exist.txt").exists()
    journal = RunJournalStore.from_output_dir(session.output_dir).load(result.run_id)
    assert journal.evidence == []
    assert journal.reconnaissance.tool_calls == 0


def test_auto_change_task_records_write_authorization(tmp_path):
    session = _make_session(tmp_path)
    gateway = _mock_gateway(
        '```tool:write_file\n{"path": "fixed.txt", "content": "ok"}\n```',
        "修复完成",
    )
    agent = Agent(gateway, session, approval_mode="auto")

    result = agent.run_turn("修复这个文件并写入 fixed.txt")

    assert result.engineering["intent"]["kind"] == "change"
    assert result.engineering["intent"]["write_authorized"] is True
    assert (tmp_path / "output" / "fixed.txt").exists()


def test_run_turn_failure_marks_journal_failed(tmp_path):
    session = _make_session(tmp_path)
    gateway = MagicMock()
    gateway.chat_with_main_model.side_effect = RuntimeError("gateway down")
    agent = Agent(gateway, session)

    with pytest.raises(RuntimeError, match="gateway down"):
        agent.run_turn("执行任务")

    journal = RunJournalStore.from_output_dir(session.output_dir).latest()
    assert journal is not None
    assert journal.status == "failed"
    assert journal.residual_risks == ["gateway down"]


def test_run_turn_compaction_failure_marks_journal_failed(tmp_path):
    session = _make_session(tmp_path)
    agent = Agent(_mock_gateway("unused"), session)
    agent._maybe_compact_context = MagicMock(side_effect=RuntimeError("compact down"))

    with pytest.raises(RuntimeError, match="compact down"):
        agent.run_turn("执行任务")

    journal = RunJournalStore.from_output_dir(session.output_dir).latest()
    assert journal is not None
    assert journal.status == "failed"
    assert journal.residual_risks == ["compact down"]


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
    journal = RunJournalStore.from_output_dir(session.output_dir).load(result.run_id)
    assert len(journal.evidence) == 1
    assert journal.evidence[0].tool_name == "read_file"
    assert journal.reconnaissance.tool_calls == 1
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

"""Agent 权限模式单元测试"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from src.core.agent import Agent
from src.core.permission_rules import PermissionRuleEngine
from src.core.session import Session
from src.models.schemas import ChatResponse, ChatStreamEvent, StreamChunk


def _make_session(tmp_path, approval_mode: str = "auto") -> Session:
    return Session(
        id="test-session",
        title="test",
        created_at="2026-07-12T00:00:00+00:00",
        updated_at="2026-07-12T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
        approval_mode=approval_mode,
    )


def _async_chunks(*chunks: StreamChunk):
    async def _gen():
        for c in chunks:
            yield c

    return _gen()


def test_readonly_denies_tool_call(tmp_path):
    """readonly 模式下工具调用应被拒绝，且不产生权限请求"""
    session = _make_session(tmp_path, approval_mode="readonly")
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content='```tool:write_file\n{"path": "foo.txt", "content": "hello"}\n```'),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5, cost_usd=0.0001),
    )

    agent = Agent(gateway, session)

    async def _run():
        events = [e async for e in agent.run_turn_stream("写文件")]
        return events

    events = asyncio.run(_run())

    permission_events = [e for e in events if e.type == "permission_request"]
    done = [e for e in events if e.type == "done"][0]

    assert not permission_events
    assert done.tool_calls
    assert done.tool_calls[0]["tool"] == "write_file"
    assert done.tool_calls[0]["success"] is False
    assert "只读模式" in done.tool_calls[0]["error"]
    assert not done.files_written


def test_readonly_allows_read_tool_without_permission_request(tmp_path):
    session = _make_session(tmp_path, approval_mode="readonly")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "note.txt").write_text("hello", encoding="utf-8")
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(
            type="delta",
            content='```tool:read_file\n{"path": "note.txt"}\n```',
        ),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5),
    )
    agent = Agent(gateway, session)

    events = asyncio.run(_collect_events(agent, "读取 note.txt"))
    done = next(event for event in events if event.type == "done")

    assert not any(event.type == "permission_request" for event in events)
    assert done.tool_calls[0]["success"] is True
    assert done.tool_calls[0]["output"] == "hello"


def test_approve_yields_permission_request_and_executes_when_approved(tmp_path):
    """approve 模式下应产出权限请求；用户批准后真正执行工具"""
    session = _make_session(tmp_path, approval_mode="approve")
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content='```tool:write_file\n{"path": "approved.txt", "content": "ok"}\n```'),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5, cost_usd=0.0001),
    )

    agent = Agent(gateway, session)

    async def _run():
        events: list[ChatStreamEvent] = []
        async for event in agent.run_turn_stream("写文件"):
            events.append(event)
            if event.type == "permission_request":
                req_id = event.permission_request["request_id"]
                # 在下一事件循环迭代中批准
                asyncio.get_event_loop().call_soon(
                    agent.respond_to_permission, req_id, True
                )
        return events

    events = asyncio.run(_run())

    permission_events = [e for e in events if e.type == "permission_request"]
    done = [e for e in events if e.type == "done"][0]

    assert len(permission_events) == 1
    req = permission_events[0].permission_request
    assert req["tool"] == "write_file"
    assert req["params"]["path"] == "approved.txt"

    assert done.tool_calls[0]["success"] is True
    assert done.tool_calls[0]["permission"]["action"] == "ask"
    assert agent._pending_permissions == {}
    assert agent._permission_results == {}
    assert any("approved.txt" in f for f in done.files_written)

    # 文件确实落盘
    written = tmp_path / "output" / "approved.txt"
    assert written.exists()
    assert written.read_text(encoding="utf-8") == "ok"


def test_unknown_permission_response_is_ignored(tmp_path):
    session = _make_session(tmp_path, approval_mode="approve")
    agent = Agent(MagicMock(), session)

    assert agent.respond_to_permission("perm-not-live", True) is False
    assert agent._pending_permissions == {}
    assert agent._permission_results == {}


def test_approve_denies_tool_when_rejected(tmp_path):
    """approve 模式下用户拒绝后工具不应执行"""
    session = _make_session(tmp_path, approval_mode="approve")
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content='```tool:write_file\n{"path": "rejected.txt", "content": "no"}\n```'),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5, cost_usd=0.0001),
    )

    agent = Agent(gateway, session)

    async def _run():
        events: list[ChatStreamEvent] = []
        async for event in agent.run_turn_stream("写文件"):
            events.append(event)
            if event.type == "permission_request":
                req_id = event.permission_request["request_id"]
                asyncio.get_event_loop().call_soon(
                    agent.respond_to_permission, req_id, False
                )
        return events

    events = asyncio.run(_run())

    done = [e for e in events if e.type == "done"][0]
    assert done.tool_calls[0]["success"] is False
    assert "拒绝" in done.tool_calls[0]["error"]
    assert not done.files_written

    written = tmp_path / "output" / "rejected.txt"
    assert not written.exists()


def test_approve_unclassified_request_can_ask_before_writing(tmp_path):
    session = _make_session(tmp_path, approval_mode="approve")
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(
            type="delta",
            content='```tool:write_file\n{"path": "approved-unknown.txt", "content": "ok"}\n```',
        ),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5),
    )
    agent = Agent(gateway, session)

    async def _run():
        events: list[ChatStreamEvent] = []
        async for event in agent.run_turn_stream("处理一下"):
            events.append(event)
            if event.type == "permission_request":
                asyncio.get_event_loop().call_soon(
                    agent.respond_to_permission,
                    event.permission_request["request_id"],
                    True,
                )
        return events

    events = asyncio.run(_run())
    start = next(event for event in events if event.type == "engineering_start")
    complete = next(event for event in events if event.type == "engineering_complete")

    assert start.engineering["intent"]["kind"] == "unclassified"
    assert start.engineering["intent"]["policy"]["permission_follows_session"] is True
    assert any(event.type == "permission_request" for event in events)
    assert complete.engineering["intent"]["write_authorized"] is True
    assert (tmp_path / "output" / "approved-unknown.txt").exists()


def test_approve_allows_read_tool_without_permission_request(tmp_path):
    session = _make_session(tmp_path, approval_mode="approve")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "note.txt").write_text("hello", encoding="utf-8")
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(
            type="delta",
            content='```tool:read_file\n{"path": "note.txt"}\n```',
        ),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5),
    )
    agent = Agent(gateway, session)

    events = asyncio.run(_collect_events(agent, "读取 note.txt"))
    done = next(event for event in events if event.type == "done")

    assert not any(event.type == "permission_request" for event in events)
    assert done.tool_calls[0]["success"] is True


def test_auto_unclassified_request_can_write_without_permission(tmp_path):
    session = _make_session(tmp_path, approval_mode="auto")
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(
            type="delta",
            content='```tool:write_file\n{"path": "created.txt", "content": "ok"}\n```',
        ),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5),
    )
    agent = Agent(gateway, session)

    events = asyncio.run(_collect_events(agent, "处理一下"))
    start = next(event for event in events if event.type == "engineering_start")
    complete = next(event for event in events if event.type == "engineering_complete")
    done = next(event for event in events if event.type == "done")

    assert start.engineering["intent"]["kind"] == "unclassified"
    assert start.engineering["intent"]["write_authorized"] is True
    assert not any(event.type == "permission_request" for event in events)
    assert done.tool_calls[0]["success"] is True
    assert (tmp_path / "output" / "created.txt").read_text(encoding="utf-8") == "ok"
    assert complete.engineering["effective_intent"]["kind"] == "change"
    assert complete.engineering["observed_mutation"]["project_file_count"] == 1
    assert complete.engineering["audit"]["status"] == "blocked"


def test_external_project_write_is_observed_with_canonical_path(tmp_path):
    session = _make_session(tmp_path, approval_mode="auto")
    project_dir = tmp_path / "external-project"
    project_dir.mkdir()
    target = project_dir / "app.py"
    tool_call = "```tool:write_file\n" + json.dumps(
        {"path": str(target), "content": "VALUE = 1"}
    ) + "\n```"
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content=tool_call),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5),
    )
    agent = Agent(gateway, session)

    events = asyncio.run(_collect_events(agent, "处理一下"))
    complete = next(event for event in events if event.type == "engineering_complete")

    assert target.read_text(encoding="utf-8") == "VALUE = 1"
    mutation = complete.engineering["observed_mutation"]
    assert mutation["project_files"] == [str(target.resolve())]
    assert mutation["project_file_count"] == 1
    assert complete.engineering["effective_intent"]["kind"] == "change"
    assert complete.engineering["audit"]["status"] == "blocked"


def test_auto_create_it_for_me_writes_without_permission(tmp_path):
    session = _make_session(tmp_path, approval_mode="auto")
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(
            type="delta",
            content='```tool:write_file\n{"path": "index.html", "content": "<h1>ok</h1>"}\n```',
        ),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5),
    )
    agent = Agent(gateway, session)

    events = asyncio.run(_collect_events(agent, "帮我创建好"))
    start = next(event for event in events if event.type == "engineering_start")
    done = next(event for event in events if event.type == "done")

    assert start.engineering["intent"]["kind"] == "build"
    assert not any(event.type == "permission_request" for event in events)
    assert done.tool_calls[0]["success"] is True
    assert (tmp_path / "output" / "index.html").exists()


def test_auto_executes_without_permission_event(tmp_path):
    """auto 模式下应直接执行工具，不产生权限请求，并自动落盘 response.md"""
    session = _make_session(tmp_path, approval_mode="auto")
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content="这是最终回答。"),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5, cost_usd=0.0001),
    )

    agent = Agent(gateway, session)

    events = asyncio.run(_collect_events(agent, "问题"))
    done = [e for e in events if e.type == "done"][0]

    assert not any(e.type == "permission_request" for e in events)
    assert done.files_written
    assert any("response.md" in f for f in done.files_written)


def test_approve_does_not_auto_write_response_md(tmp_path):
    """approve 模式下没有明确批准的 write_file 时，不应自动写 response.md"""
    session = _make_session(tmp_path, approval_mode="approve")
    gateway = MagicMock()
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content="这是最终回答。"),
        StreamChunk(type="usage", input_tokens=10, output_tokens=5, cost_usd=0.0001),
    )

    agent = Agent(gateway, session)
    events = asyncio.run(_collect_events(agent, "问题"))
    done = [e for e in events if e.type == "done"][0]

    assert not done.files_written


def test_sync_approve_rejects_non_read_tool_without_interactive_confirmation(tmp_path):
    session = _make_session(tmp_path, approval_mode="approve")
    gateway = MagicMock()
    gateway.main_model = None
    gateway.chat_with_main_model.side_effect = [
        ChatResponse(
            content='```tool:write_file\n{"path": "sync.txt", "content": "no"}\n```',
            model="test",
            provider="test",
        ),
        ChatResponse(content="未写入", model="test", provider="test"),
    ]
    agent = Agent(gateway, session)

    result = agent.run_turn("修改并写入 sync.txt")

    assert result.tool_calls[0]["success"] is False
    assert "同步执行无法交互确认" in result.tool_calls[0]["error"]
    assert not (tmp_path / "output" / "sync.txt").exists()
    assert result.engineering["intent"]["write_authorized"] is False


def test_plan_mode_blocks_write_and_persists_plan_artifact(tmp_path):
    session = _make_session(tmp_path, approval_mode="auto")
    session.enter_plan_mode("create an index page")
    gateway = MagicMock()
    gateway.main_model = None
    gateway.chat_with_main_model.side_effect = [
        ChatResponse(
            content='```tool:write_file\n{"path":"index.html","content":"bad"}\n```',
            model="test",
            provider="test",
        ),
        ChatResponse(
            content="Plan: inspect structure, implement index.html, then run smoke tests.",
            model="test",
            provider="test",
        ),
    ]
    agent = Agent(gateway, session)

    result = agent.run_turn("make a plan first")

    assert result.tool_calls[0]["success"] is False
    assert "只读子任务禁止" in result.tool_calls[0]["error"]
    assert not (tmp_path / "output" / "index.html").exists()
    assert not (tmp_path / "output" / "response.md").exists()
    assert session.plan_mode == "awaiting_approval"
    assert session.plan_artifact is not None
    assert "smoke tests" in session.plan_artifact.content


def test_auto_mode_cannot_bypass_explicit_deny_rule(tmp_path):
    project = tmp_path / "project"
    rules = project / ".mao" / "permissions.yaml"
    rules.parent.mkdir(parents=True)
    rules.write_text(
        'rules:\n  - action: deny\n    tool: write_file\n    pattern: "**/*.txt"\n',
        encoding="utf-8",
    )
    engine = PermissionRuleEngine.load(project_root=project, workspace=project)
    session = _make_session(tmp_path, approval_mode="auto")
    gateway = MagicMock()
    gateway.main_model = None
    gateway.chat_with_main_model.side_effect = [
        ChatResponse(
            content='```tool:write_file\n{"path":"blocked.txt","content":"bad"}\n```',
            model="test",
            provider="test",
        ),
        ChatResponse(content="blocked", model="test", provider="test"),
    ]
    agent = Agent(gateway, session, permission_rule_engine=engine)

    result = agent.run_turn("create blocked.txt")

    assert result.tool_calls[0]["success"] is False
    assert result.tool_calls[0]["permission"]["rule"]["action"] == "deny"
    assert not (tmp_path / "output" / "blocked.txt").exists()


def test_denied_command_returns_one_retry_guidance(tmp_path):
    project = tmp_path / "project"
    rules = project / ".mao" / "permissions.yaml"
    rules.parent.mkdir(parents=True)
    rules.write_text(
        "rules:\n"
        "  - action: deny\n"
        "    tool: run_command\n"
        "    pattern: 'npm *'\n"
        "    justification: '项目禁止 npm 命令'\n",
        encoding="utf-8",
    )
    engine = PermissionRuleEngine.load(project_root=project, workspace=project)
    session = _make_session(tmp_path, approval_mode="auto")
    gateway = MagicMock()
    gateway.main_model = None
    gateway.chat_with_main_model.side_effect = [
        ChatResponse(
            content='```tool:run_command\n{"command":"npm test","cwd":"."}\n```',
            model="test",
            provider="test",
        ),
        ChatResponse(content="停止执行", model="test", provider="test"),
    ]
    agent = Agent(gateway, session, permission_rule_engine=engine)

    result = agent.run_turn("修复测试")

    call = result.tool_calls[0]
    assert call["success"] is False
    assert call["metadata"]["error_code"] == "permission_denied"
    assert "最多修正一次" in call["error"]
    assert result.engineering["metrics"]["preflight_failures"] == 1


async def _collect_events(agent: Agent, text: str) -> list[ChatStreamEvent]:
    return [e async for e in agent.run_turn_stream(text)]

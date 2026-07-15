"""Agent 多模型协作分支单元测试"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from src.core.agent import Agent
from src.core.session import Session
from src.models.schemas import (
    ChatResponse,
    ChatStreamEvent,
    ReviewResult,
    StreamChunk,
    Task,
    TaskPlan,
    TaskResult,
    ModelConfig,
)


def _make_session(tmp_path) -> Session:
    return Session(
        id="test-session",
        title="test",
        created_at="2026-07-12T00:00:00+00:00",
        updated_at="2026-07-12T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
    )


def _collect_events(agent: Agent, text: str) -> list[ChatStreamEvent]:
    async def _run():
        return [e async for e in agent.run_turn_stream(text)]

    return asyncio.run(_run())


def _mock_gateway(collaborate: bool = True):
    gateway = MagicMock()
    gateway.billing.summary.side_effect = [
        {"total_input_tokens": 0, "total_output_tokens": 0, "total_cost_usd": 0.0},
        {"total_input_tokens": 100, "total_output_tokens": 50, "total_cost_usd": 0.001},
    ]
    gateway.chat_with_main_model.return_value = ChatResponse(
        content=f'{{"collaborate": {str(collaborate).lower()}}}',
        model="main",
        provider="test",
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.0001,
    )
    return gateway


def test_should_collaborate_false_goes_single_model(tmp_path):
    session = _make_session(tmp_path)
    gateway = _mock_gateway(collaborate=False)
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content="你好"),
        StreamChunk(type="usage", input_tokens=5, output_tokens=3, cost_usd=0.00005),
    )
    agent = Agent(gateway, session)

    events = _collect_events(agent, "你好")

    assert any(e.type == "delta" for e in events)
    done = [e for e in events if e.type == "done"][0]
    assert done.assistant_message == "你好"


@pytest.mark.parametrize("keyword", ["只做方案", "不要修改"])
def test_analysis_only_request_skips_collaboration_without_llm_routing(tmp_path, keyword):
    session = _make_session(tmp_path)
    gateway = _mock_gateway(collaborate=True)
    agent = Agent(gateway, session)

    should_collaborate = asyncio.run(
        agent._should_collaborate(
            f"分析 G:\\MAO_test 的项目结构并给出 Java 重构方案，{keyword}。"
        )
    )

    assert should_collaborate is False
    gateway.chat_with_main_model.assert_not_called()


def test_collaboration_stream_yields_plan_tasks_review_done(tmp_path):
    session = _make_session(tmp_path)
    gateway = _mock_gateway(collaborate=True)
    agent = Agent(gateway, session)

    t1 = Task(id="t1", type="frontend", title="写前端", input="", assigned_model="glm-ark")
    t2 = Task(id="t2", type="backend", title="写后端", input="", assigned_model="glm-ark")
    plan = TaskPlan(summary="开发登录功能", tasks=[t1, t2])

    def _fake_dispatch(plan_obj, output_dir, progress_callback=None, memory_context=None):
        if progress_callback:
            progress_callback("task_start", {"id": "t1", "type": "frontend", "title": "写前端", "assigned_model": "glm-ark"})
            progress_callback("task_complete", {
                "id": "t1",
                "type": "frontend",
                "title": "写前端",
                "assigned_model": "glm-ark",
                "success": True,
                "files_written": ["output/frontend_t1/page.tsx"],
                "content": "frontend code",
            })
            progress_callback("task_start", {"id": "t2", "type": "backend", "title": "写后端", "assigned_model": "glm-ark"})
            progress_callback("task_complete", {
                "id": "t2",
                "type": "backend",
                "title": "写后端",
                "assigned_model": "glm-ark",
                "success": True,
                "files_written": ["output/backend_t2/api.py"],
                "content": "backend code",
            })
        return [
            TaskResult(task=t1, success=True, content="frontend code", files_written=["output/frontend_t1/page.tsx"]),
            TaskResult(task=t2, success=True, content="backend code", files_written=["output/backend_t2/api.py"]),
        ]

    with patch("src.core.orchestrator.Orchestrator") as MockOrchestrator, \
         patch("src.core.dispatcher.Dispatcher") as MockDispatcher, \
         patch("src.core.reviewer.Reviewer") as MockReviewer:
        MockOrchestrator.return_value.plan.return_value = plan
        MockDispatcher.return_value.dispatch.side_effect = _fake_dispatch
        MockReviewer.return_value.review.return_value = ReviewResult(
            passed=True,
            issues=[],
            final_output="已完成前后端登录功能。",
        )

        events = _collect_events(agent, "开发一个登录功能")

    plan_events = [e for e in events if e.type == "plan"]
    task_starts = [e for e in events if e.type == "task_start"]
    task_completes = [e for e in events if e.type == "task_complete"]
    review_events = [e for e in events if e.type == "review_complete"]
    done_events = [e for e in events if e.type == "done"]

    assert len(plan_events) == 1
    assert plan_events[0].plan["summary"] == "开发登录功能"
    assert len(plan_events[0].plan["tasks"]) == 2

    assert len(task_starts) == 2
    assert len(task_completes) == 2

    assert len(review_events) == 1
    assert review_events[0].review["passed"] is True
    assert "已完成前后端登录功能" in review_events[0].review["final_output"]

    assert len(done_events) == 1
    done = done_events[0]
    assert done.assistant_message.startswith("已完成前后端登录功能。")
    assert "验证未闭环" in done.assistant_message
    assert "output/frontend_t1/page.tsx" in done.files_written
    assert "output/backend_t2/api.py" in done.files_written
    assert done.input_tokens == 100
    assert done.output_tokens == 50
    assert done.cost_usd == pytest.approx(0.001)
    engineering = next(
        event.engineering for event in events if event.type == "engineering_complete"
    )
    assert engineering["status"] == "blocked"
    assert engineering["audit"]["missing_checks"] == [
        "实现证据",
        "针对性验证",
        "集成测试",
        "全量回归",
        "运行时 smoke 验证",
        "使用说明",
    ]

    # 最终答案应被追加到会话历史
    assert session.messages[-1].role == "assistant"
    assert session.messages[-1].content == done.assistant_message


def test_collaboration_worker_tool_trace_can_satisfy_deep_completion_audit(tmp_path):
    session = _make_session(tmp_path)
    gateway = _mock_gateway(collaborate=True)
    agent = Agent(gateway, session, approval_mode="auto")
    implementation = Task(
        id="impl", type="backend_dev", title="实现", input="", assigned_model="glm-ark"
    )
    testing = Task(
        id="test", type="tester", title="验证", input="", assigned_model="glm-ark",
        depends_on=["impl"], execution_mode="verify",
    )
    plan = TaskPlan(summary="完整实现", tasks=[implementation, testing])
    write_calls = [
        {
            "tool": "write_file",
            "params": {"path": "src/login.py"},
            "success": True,
            "output": "已写入",
            "error": "",
        },
        {
            "tool": "write_file",
            "params": {"path": "README.md"},
            "success": True,
            "output": "已写入",
            "error": "",
        },
    ]
    test_commands = [
        "pytest tests/test_login.py",
        "pytest tests/integration/test_login.py",
        "python -m pytest -q",
        "pytest tests/smoke/test_login.py",
    ]
    test_calls = [
        {
            "tool": "run_command",
            "params": {"command": command},
            "success": True,
            "output": "1 passed",
            "error": "",
        }
        for command in test_commands
    ]
    results = [
        TaskResult(
            task=implementation,
            success=True,
            content="implemented",
            files_written=["src/login.py", "README.md"],
            tool_calls=write_calls,
            acceptance_evidence=["实现文件", "使用说明"],
        ),
        TaskResult(
            task=testing,
            success=True,
            content="verified",
            tool_calls=test_calls,
            acceptance_evidence=["四层验证通过"],
        ),
    ]

    def dispatch(_plan, output_dir, progress_callback=None, memory_context=None):
        for result in results:
            if progress_callback:
                progress_callback("task_complete", {
                    "id": result.task.id,
                    "type": result.task.type,
                    "title": result.task.title,
                    "assigned_model": result.task.assigned_model,
                    "success": result.success,
                    "files_written": result.files_written,
                    "content": result.content,
                    "tool_calls": result.tool_calls,
                    "attempts": result.attempts,
                    "retry_errors": [],
                    "acceptance_evidence": result.acceptance_evidence,
                })
        return results

    with patch("src.core.orchestrator.Orchestrator") as MockOrchestrator, \
         patch("src.core.dispatcher.Dispatcher") as MockDispatcher, \
         patch("src.core.reviewer.Reviewer") as MockReviewer:
        MockOrchestrator.return_value.plan.return_value = plan
        MockDispatcher.return_value.dispatch.side_effect = dispatch
        MockReviewer.return_value.review.return_value = ReviewResult(
            passed=True, issues=[], final_output="实现与验证完成"
        )
        events = _collect_events(agent, "实现一个完整登录功能")

    engineering = next(
        event.engineering for event in events if event.type == "engineering_complete"
    )
    done = next(event for event in events if event.type == "done")
    assert engineering["status"] == "completed"
    assert engineering["audit"]["status"] == "passed"
    assert engineering["verification_count"] == 4
    assert engineering["requirement_counts"]["satisfied"] == 6
    assert done.assistant_message == "实现与验证完成"


def test_collaboration_stream_handles_task_failure(tmp_path):
    session = _make_session(tmp_path)
    gateway = _mock_gateway(collaborate=True)
    agent = Agent(gateway, session)

    t1 = Task(id="t1", type="frontend", title="写前端", input="", assigned_model="glm-ark")
    plan = TaskPlan(summary="开发登录功能", tasks=[t1])

    def _fake_dispatch(plan_obj, output_dir, progress_callback=None, memory_context=None):
        if progress_callback:
            progress_callback("task_start", {"id": "t1", "type": "frontend", "title": "写前端", "assigned_model": "glm-ark"})
            progress_callback("task_complete", {
                "id": "t1",
                "type": "frontend",
                "title": "写前端",
                "assigned_model": "glm-ark",
                "success": False,
                "error": "模型调用失败",
                "files_written": [],
            })
        return [TaskResult(task=t1, success=False, content="", error="模型调用失败")]

    with patch("src.core.orchestrator.Orchestrator") as MockOrchestrator, \
         patch("src.core.dispatcher.Dispatcher") as MockDispatcher, \
         patch("src.core.reviewer.Reviewer") as MockReviewer:
        MockOrchestrator.return_value.plan.return_value = plan
        MockDispatcher.return_value.dispatch.side_effect = _fake_dispatch
        MockReviewer.return_value.review.return_value = ReviewResult(
            passed=False,
            issues=["前端任务失败"],
            final_output="前端任务执行失败，请检查模型配置。",
        )

        events = _collect_events(agent, "开发一个登录功能")

    complete = [e for e in events if e.type == "task_complete"][0]
    assert complete.task["success"] is False
    assert "模型调用失败" in complete.task["error"]

    review = [e for e in events if e.type == "review_complete"][0]
    assert review.review["passed"] is False


def test_collaboration_real_worker_lists_reads_and_writes_file(tmp_path):
    """贯穿 Agent/Dispatcher/Worker，证明目录工具结果会回填并显式写文件。"""
    session = _make_session(tmp_path)
    gateway = _mock_gateway(collaborate=True)
    gateway.resolve_model.return_value = "glm-ark"
    gateway.get_model_config.return_value = ModelConfig(
        provider="ark", model_id="ark-code-latest", capabilities=[]
    )
    project_dir = tmp_path / "external-project"
    project_dir.mkdir()
    (project_dir / "seed.txt").write_text("seed", encoding="utf-8")

    def _worker_chat(*args, **kwargs):
        messages = kwargs["messages"]
        worker_calls = gateway.chat.call_count
        if worker_calls == 1:
            return ChatResponse(
                content=(
                    '```tool:list_dir\n'
                    f'{{"path":{json.dumps(str(project_dir))}}}\n```'
                ),
                model="glm-ark", provider="ark",
            )
        if worker_calls == 2:
            assert "seed.txt" in messages[-1].content
            return ChatResponse(
                content=(
                    '```tool:write_file\n'
                    '{"path":"result.txt","content":"built from seed"}\n```'
                ),
                model="glm-ark", provider="ark",
            )
        return ChatResponse(content="任务完成。", model="glm-ark", provider="ark")

    gateway.chat.side_effect = _worker_chat
    agent = Agent(gateway, session, approval_mode="auto")
    task = Task(
        id="t1",
        type="frontend_dev",
        title="读取并实现",
        input=f"检查 {project_dir} 并创建结果文件",
        assigned_model="glm-ark",
    )
    plan = TaskPlan(summary="项目实现", tasks=[task])
    worker_config = {
        "frontend_dev": {
            "name": "前端",
            "default_model": "glm-ark",
            "system_prompt": "完成实现任务",
            "tools": ["write_file", "read_file"],
        }
    }

    with patch("src.core.orchestrator.Orchestrator") as MockOrchestrator, \
         patch("src.core.reviewer.Reviewer") as MockReviewer, \
         patch("src.core.worker.load_workers_config", return_value=worker_config):
        MockOrchestrator.return_value.plan.return_value = plan
        MockReviewer.return_value.review.return_value = ReviewResult(
            passed=True, issues=[], final_output="项目已完成。"
        )
        events = _collect_events(agent, "开发一个项目并检查外部目录")

    done = [event for event in events if event.type == "done"][0]
    output_file = tmp_path / "output" / "frontend_dev_t1" / "result.txt"
    assert output_file.read_text(encoding="utf-8") == "built from seed"
    assert str(output_file.resolve()) in done.files_written
    assert not list((tmp_path / "output").rglob("generated_*"))
    assert gateway.chat.call_count == 3


def _async_chunks(*events: ChatStreamEvent):
    async def _gen():
        for e in events:
            yield e
    return _gen()


def test_collaboration_approve_mode_requests_permission_then_runs(tmp_path):
    """approve 模式：协作前产出 permission_request，批准后正常 dispatch"""
    session = _make_session(tmp_path)
    session.approval_mode = "approve"
    gateway = _mock_gateway(collaborate=True)
    agent = Agent(gateway, session)

    t1 = Task(id="t1", type="frontend", title="写前端", input="", assigned_model="glm-ark")
    plan = TaskPlan(summary="开发登录功能", tasks=[t1])

    dispatch_count = {"n": 0}

    def _fake_dispatch(plan_obj, output_dir, progress_callback=None, memory_context=None):
        dispatch_count["n"] += 1
        if progress_callback:
            progress_callback("task_complete", {
                "id": "t1",
                "type": "frontend",
                "title": "写前端",
                "assigned_model": "glm-ark",
                "success": True,
                "files_written": ["output/frontend_t1/page.tsx"],
                "content": "code",
            })
        return [TaskResult(task=t1, success=True, content="code", files_written=["output/frontend_t1/page.tsx"])]

    with patch("src.core.orchestrator.Orchestrator") as MockOrchestrator, \
         patch("src.core.dispatcher.Dispatcher") as MockDispatcher, \
         patch("src.core.reviewer.Reviewer") as MockReviewer:
        MockOrchestrator.return_value.plan.return_value = plan
        MockDispatcher.return_value.dispatch.side_effect = _fake_dispatch
        MockReviewer.return_value.review.return_value = ReviewResult(
            passed=True, issues=[], final_output="已完成登录功能。"
        )

        async def _run():
            events = []
            async for event in agent.run_turn_stream("开发登录功能"):
                events.append(event)
                if event.type == "permission_request":
                    req_id = event.permission_request["request_id"]
                    asyncio.get_event_loop().call_soon(agent.respond_to_permission, req_id, True)
            return events

        events = asyncio.run(_run())

    perm = [e for e in events if e.type == "permission_request"]
    assert len(perm) == 1
    assert perm[0].permission_request["tool"] == "collaboration"
    assert perm[0].permission_request["params"]["task_count"] == 1
    assert dispatch_count["n"] == 1
    done = [e for e in events if e.type == "done"][0]
    assert done.assistant_message.startswith("已完成登录功能。")
    assert "验证未闭环" in done.assistant_message


def test_collaboration_approve_mode_cancelled_when_denied(tmp_path):
    """approve 模式：拒绝后不 dispatch，done 提示已取消"""
    session = _make_session(tmp_path)
    session.approval_mode = "approve"
    gateway = _mock_gateway(collaborate=True)
    agent = Agent(gateway, session)

    t1 = Task(id="t1", type="frontend", title="写前端", input="", assigned_model="glm-ark")
    plan = TaskPlan(summary="开发登录功能", tasks=[t1])

    with patch("src.core.orchestrator.Orchestrator") as MockOrchestrator, \
         patch("src.core.dispatcher.Dispatcher") as MockDispatcher, \
         patch("src.core.reviewer.Reviewer") as MockReviewer:
        MockOrchestrator.return_value.plan.return_value = plan

        async def _run():
            events = []
            async for event in agent.run_turn_stream("开发登录功能"):
                events.append(event)
                if event.type == "permission_request":
                    req_id = event.permission_request["request_id"]
                    asyncio.get_event_loop().call_soon(agent.respond_to_permission, req_id, False)
            return events

        events = asyncio.run(_run())

    perm = [e for e in events if e.type == "permission_request"]
    assert len(perm) == 1
    assert MockDispatcher.return_value.dispatch.called is False
    done = [e for e in events if e.type == "done"][0]
    assert "取消" in done.assistant_message
    assert done.files_written == []


def test_collaboration_skipped_in_readonly_mode(tmp_path):
    """readonly 模式：不触发协作，走单模型路径"""
    session = _make_session(tmp_path)
    session.approval_mode = "readonly"
    gateway = _mock_gateway(collaborate=True)
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content="只读模式回答"),
        StreamChunk(type="usage", input_tokens=5, output_tokens=3, cost_usd=0.0),
    )
    agent = Agent(gateway, session)

    with patch("src.core.orchestrator.Orchestrator") as MockOrchestrator:
        events = _collect_events(agent, "开发登录功能")

    assert not any(e.type == "plan" for e in events)
    assert not any(e.type == "permission_request" for e in events)
    assert not any(e.type == "task_start" for e in events)
    done = [e for e in events if e.type == "done"][0]
    assert done.assistant_message == "只读模式回答"

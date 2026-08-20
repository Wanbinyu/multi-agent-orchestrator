"""P0-8: default single-Agent collaboration gate."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from src.core.agent import Agent
from src.core.engineering import (
    ExecutionDepthResolver,
    TaskIntentClassifier,
    decide_collaboration,
    load_collaboration_force,
)
from src.core.session import Session
from src.models.schemas import ChatResponse, StreamChunk


def _intent(text: str):
    return TaskIntentClassifier().classify(text, "auto")


def _depth(intent, requested="auto"):
    return ExecutionDepthResolver().resolve(intent, requested)


def test_small_change_defaults_to_single_agent():
    intent = _intent("修复 CLI 输出")
    decision = decide_collaboration(
        session_mode="auto",
        intent=intent,
        execution_depth=_depth(intent),
    )
    assert intent.kind == "change"
    assert decision.triggered is False
    assert decision.reason == "default_single"


def test_diagnose_and_question_never_collaborate():
    for text, kind in (("为什么 CLI 报错", "diagnose"), ("现在上下文是多少？", "answer")):
        intent = _intent(text)
        decision = decide_collaboration(
            session_mode="auto",
            intent=intent,
            execution_depth=_depth(intent),
        )
        assert intent.kind == kind
        assert decision.triggered is False
        assert decision.reason in {"policy_disallowed", "default_single", "workers_disabled"}


def test_deep_build_collaborates_without_user_override():
    text = "开发一个登录功能"
    intent = _intent(text)
    decision = decide_collaboration(
        session_mode="auto",
        intent=intent,
        execution_depth=_depth(intent),
        user_input=text,
    )
    assert intent.kind == "build"
    assert decision.triggered is True
    assert decision.reason == "deep_change_or_build"


def test_explicit_multi_allows_standard_change():
    intent = _intent("修复 CLI 输出")
    decision = decide_collaboration(
        session_mode="multi",
        intent=intent,
        execution_depth=_depth(intent),
    )
    assert decision.triggered is True
    assert decision.reason == "user_explicit"


def test_explicit_multi_cannot_expand_readonly_policy():
    intent = _intent("解释一下递归")
    decision = decide_collaboration(
        session_mode="multi",
        intent=intent,
        execution_depth=_depth(intent),
    )
    assert decision.triggered is False
    assert decision.reason == "policy_disallowed"


def test_single_file_create_does_not_collaborate():
    for text in ("写文件", "帮我创建好"):
        intent = _intent(text)
        decision = decide_collaboration(
            session_mode="auto",
            intent=intent,
            execution_depth=_depth(intent),
            user_input=text,
        )
        assert decision.triggered is False
        assert decision.reason == "default_single"


def test_user_single_blocks_deep_build():
    intent = _intent("实现一个完整网站")
    decision = decide_collaboration(
        session_mode="single",
        intent=intent,
        execution_depth=_depth(intent),
        user_input="实现一个完整网站",
    )
    assert decision.triggered is False
    assert decision.reason == "user_single"


def test_config_force_triggers_on_allowed_change():
    intent = _intent("修复 CLI 输出")
    decision = decide_collaboration(
        session_mode="auto",
        intent=intent,
        execution_depth=_depth(intent),
        config_force=True,
    )
    assert decision.triggered is True
    assert decision.reason == "config_force"


def test_load_collaboration_force_reads_workers_yaml(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "workers.yaml").write_text(
        "collaboration:\n  force: true\navailable_workers: {}\n",
        encoding="utf-8",
    )
    assert load_collaboration_force(config_dir) is True
    (config_dir / "workers.yaml").write_text("available_workers: {}\n", encoding="utf-8")
    assert load_collaboration_force(config_dir) is False


def _session(tmp_path) -> Session:
    return Session(
        id="collab-session",
        title="t",
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
    )


def _async_chunks(*chunks: StreamChunk):
    async def _gen():
        for chunk in chunks:
            yield chunk

    return _gen()


def test_small_change_stream_does_not_construct_orchestrator(tmp_path):
    session = _session(tmp_path)
    gateway = MagicMock()
    gateway.billing.summary.return_value = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": 0.0,
    }
    gateway.chat_with_main_model.return_value = ChatResponse(
        content='{"collaborate": true}',
        model="main",
        provider="test",
        input_tokens=1,
        output_tokens=1,
        cost_usd=0.0,
    )
    gateway.chat_with_main_model_stream.return_value = _async_chunks(
        StreamChunk(type="delta", content="已给出修复建议"),
        StreamChunk(type="usage", input_tokens=5, output_tokens=3, cost_usd=0.00005),
    )
    agent = Agent(gateway, session)

    async def _run():
        return [event async for event in agent.run_turn_stream("修复 CLI 输出")]

    with patch("src.core.orchestrator.Orchestrator") as mock_orchestrator:
        events = asyncio.run(_run())

    mock_orchestrator.assert_not_called()
    gateway.chat_with_main_model.assert_not_called()
    engineering = next(
        event.engineering for event in events if event.type == "engineering_complete"
    )
    assert engineering["metrics"]["collaboration_triggered"] is False
    assert engineering["metrics"]["collaboration_trigger_reason"] == "default_single"


def test_project_build_language_still_collaborates_without_llm(tmp_path):
    session = _session(tmp_path)
    gateway = MagicMock()
    agent = Agent(gateway, session)
    should = asyncio.run(
        agent._should_collaborate("把这几个页面综合起来做一个前后端交互的小项目")
    )
    assert should is True
    gateway.chat_with_main_model.assert_not_called()

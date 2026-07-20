"""B5.4 headless execution and three-strategy comparison contracts."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.benchmark_engineering import run_benchmark
from src.core.agent import Agent
from src.core.engineering import LiveBenchmarkAuthorization, LiveBenchmarkSpendGuard
from src.core.engineering.benchmark_agent import (
    apply_benchmark_policy,
    resolve_benchmark_policy,
    run_headless_benchmark_agent,
)
from src.core.session import Session
from src.models.schemas import ChatStreamEvent


def _session(tmp_path: Path) -> Session:
    return Session(
        id="benchmark-session",
        created_at="2026-07-19T00:00:00+00:00",
        updated_at="2026-07-19T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
    )


def test_strategy_policies_isolate_routing_and_collaboration_variables(tmp_path):
    fixed = resolve_benchmark_policy("fixed-single", main_model="glm-ark")
    automatic = resolve_benchmark_policy(
        "auto-route", allowed_models=["glm-ark", "qwen-coder"]
    )
    multi = resolve_benchmark_policy(
        "multi-model",
        execution_depth="deep",
        allowed_models=["glm-ark", "qwen-coder"],
    )

    assert (fixed.routing_mode, fixed.collaboration_mode) == ("fixed", "single")
    assert fixed.allowed_models == ["glm-ark"]
    assert resolve_benchmark_policy(
        "fixed-single",
        main_model="glm-ark",
        allowed_models=["glm-ark", "qwen-coder"],
    ).allowed_models == ["glm-ark"]
    assert (automatic.routing_mode, automatic.collaboration_mode) == ("auto", "single")
    assert (multi.routing_mode, multi.collaboration_mode) == ("auto", "multi")
    assert multi.execution_depth == "deep"
    with pytest.raises(ValueError, match="main_model"):
        resolve_benchmark_policy("fixed-single")
    with pytest.raises(ValueError, match="fast"):
        resolve_benchmark_policy(
            "multi-model",
            execution_depth="fast",
            allowed_models=["glm-ark", "qwen-coder"],
        )
    with pytest.raises(ValueError, match="至少两个"):
        resolve_benchmark_policy("auto-route", allowed_models=["glm-ark"])

    session = _session(tmp_path)
    apply_benchmark_policy(session, fixed)
    assert session.approval_mode == "auto"
    assert session.model_routing_mode == "fixed"
    assert session.collaboration_mode == "single"


def test_agent_honors_forced_single_and_multi_without_routing_call(tmp_path):
    gateway = MagicMock()
    session = _session(tmp_path)
    agent = Agent(gateway, session)

    session.collaboration_mode = "single"
    assert asyncio.run(agent._should_collaborate("开发一个完整系统")) is False
    session.collaboration_mode = "multi"
    assert asyncio.run(agent._should_collaborate("开发一个完整系统")) is True
    gateway.chat_with_main_model.assert_not_called()


def test_offline_harness_reports_all_three_controlled_strategies(tmp_path):
    report = run_benchmark(tmp_path / "runs", repeats=3)

    assert report.passed is True
    assert report.provider_calls == 0
    assert len(report.results) == 54
    assert {
        profile.comparison_strategy
        for profile in report.strategy_profiles.values()
    } == {"fixed-single", "auto-route", "multi-model"}
    assert all(item.data_kind == "synthetic_contract" for item in report.results)
    markdown = report.to_markdown()
    assert "fixed-single" in markdown
    assert "auto-route" in markdown
    assert "multi-model" in markdown


def test_live_spend_guard_requires_owner_boundary_and_stops_future_runs():
    authorization = LiveBenchmarkAuthorization(
        confirmation_reference="owner-confirmed-2026-07-19",
        allowed_models=["glm-ark"],
        max_provider_calls=2,
        stop_after_cost_usd=0.02,
        result_visibility="private",
    )
    guard = LiveBenchmarkSpendGuard(authorization)

    assert guard.record(
        provider_calls=2, provider_attempts=2, cost_usd=0.01
    ) == []
    with pytest.raises(RuntimeError, match="Provider"):
        guard.ensure_can_start()

    with pytest.raises(ValueError, match="allowed_models"):
        LiveBenchmarkAuthorization(
            confirmation_reference="confirmed",
            allowed_models=[],
            max_provider_calls=1,
            stop_after_cost_usd=0.01,
        )


def test_live_spend_guard_reserves_attempts_before_provider_calls():
    guard = LiveBenchmarkSpendGuard(
        LiveBenchmarkAuthorization(
            confirmation_reference="owner-confirmed",
            allowed_models=["glm-ark"],
            max_provider_calls=2,
            stop_after_cost_usd=0.02,
        )
    )

    guard.reserve_provider_attempt()
    guard.reserve_provider_attempt()
    with pytest.raises(RuntimeError, match="Provider"):
        guard.reserve_provider_attempt()

    issues = guard.record(
        provider_calls=2,
        provider_attempts=2,
        cost_usd=0.01,
        attempts_reserved=True,
    )
    assert issues == []
    assert guard.provider_attempts == 2


def test_live_spend_guard_hard_ceiling_is_thread_safe():
    guard = LiveBenchmarkSpendGuard(
        LiveBenchmarkAuthorization(
            confirmation_reference="owner-confirmed",
            allowed_models=["glm-ark"],
            max_provider_calls=5,
            stop_after_cost_usd=0.02,
        )
    )

    def reserve() -> bool:
        try:
            guard.reserve_provider_attempt()
        except RuntimeError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=16) as executor:
        accepted = list(executor.map(lambda _: reserve(), range(100)))

    assert sum(accepted) == 5
    assert guard.provider_attempts == 5


def test_headless_entry_uses_production_stream_and_emits_machine_result(tmp_path):
    project = tmp_path / "project"
    config = tmp_path / "config"
    state = tmp_path / "state"
    project.mkdir()
    config.mkdir()
    (config / "providers.yaml").write_text("models: {}\n", encoding="utf-8")

    class _Billing:
        def summary(self):
            return {
                "calls": [
                    {
                        "model": "glm-ark",
                        "input_tokens": 12,
                        "output_tokens": 5,
                        "cost_usd": 0.001,
                    }
                ]
            }

    class _Gateway:
        def __init__(self, config_path):
            self.config_path = config_path
            self.models = {"glm-ark": object()}
            self.main_model = "glm-ark"
            self.billing = _Billing()

    class _Agent:
        def __init__(self, gateway, session, approval_mode, memory_store):
            assert Path.cwd() != project
            self.session = session
            assert memory_store.file_index_path.is_relative_to(state)

        async def run_turn_stream(self, request):
            assert Path.cwd() == project
            assert str(project) in request
            assert request.startswith("只修复指定文件")
            assert "只修复指定文件" in request
            yield ChatStreamEvent(type="task_start", task={"id": "impl"})
            yield ChatStreamEvent(
                type="engineering_complete",
                engineering={"run_id": "run-1", "status": "completed"},
            )
            yield ChatStreamEvent(
                type="done",
                assistant_message="done",
                input_tokens=12,
                output_tokens=5,
                cost_usd=0.001,
                files_written=[str(project / "fixed.txt")],
                tool_calls=[{"tool": "write_file", "success": True}],
            )

    previous = Path.cwd()
    with patch(
        "src.core.engineering.benchmark_agent.GatewayClient", _Gateway
    ), patch("src.core.engineering.benchmark_agent.Agent", _Agent):
        result = asyncio.run(
            run_headless_benchmark_agent(
                "只修复指定文件",
                project_root=project,
                config_dir=config,
                state_dir=state,
                strategy="fixed-single",
                main_model="glm-ark",
            )
        )

    assert Path.cwd() == previous
    assert result.status == "completed"
    assert result.provider_calls == 1
    assert result.provider_attempts == 1
    assert result.actual_models == ["glm-ark"]
    assert result.tool_calls == 1
    assert result.policy.routing_mode == "fixed"
    assert result.policy.collaboration_mode == "single"
    assert (state / "sessions" / f"{result.session_id}.yaml").is_file()

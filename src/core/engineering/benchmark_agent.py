"""Headless MAO execution contract used by controlled capability benchmarks."""
from __future__ import annotations

import asyncio
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from pydantic import BaseModel, Field

from src.core.agent import Agent
from src.core.memory import MemoryStore
from src.core.session import Session, SessionStore
from src.gateway.client import GatewayClient
from src.models.schemas import (
    BenchmarkAgentStrategy,
    CollaborationMode,
    ExecutionDepthPreference,
    ModelRoutingMode,
)


class BenchmarkAgentPolicy(BaseModel):
    """Independent variables for one benchmark strategy."""

    strategy: BenchmarkAgentStrategy
    routing_mode: ModelRoutingMode
    collaboration_mode: CollaborationMode
    execution_depth: ExecutionDepthPreference
    main_model: str = ""
    allowed_models: list[str] = Field(default_factory=list)


class BenchmarkAgentResult(BaseModel):
    """Machine-readable result emitted by the headless benchmark entry point."""

    schema_version: Literal[1] = 1
    session_id: str
    run_id: str = ""
    status: Literal["completed", "failed", "blocked"] = "failed"
    policy: BenchmarkAgentPolicy
    response: str = ""
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    provider_calls: int = Field(default=0, ge=0)
    provider_attempts: int = Field(default=0, ge=0)
    actual_models: list[str] = Field(default_factory=list)
    upstream_model_ids: list[str] = Field(default_factory=list)
    tool_calls: int = Field(default=0, ge=0)
    files_written: list[str] = Field(default_factory=list)
    trajectory: list[dict[str, Any]] = Field(default_factory=list)
    engineering: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


def resolve_benchmark_policy(
    strategy: BenchmarkAgentStrategy,
    *,
    execution_depth: ExecutionDepthPreference = "standard",
    main_model: str = "",
    allowed_models: list[str] | None = None,
) -> BenchmarkAgentPolicy:
    """Resolve strategy controls without contacting a Provider."""
    normalized_model = main_model.strip()
    normalized_allowed = list(dict.fromkeys(
        item.strip() for item in (allowed_models or []) if item.strip()
    ))
    if normalized_model and normalized_allowed and normalized_model not in normalized_allowed:
        raise ValueError("benchmark main_model 必须位于 allowed_models 中")
    if strategy == "fixed-single":
        if not normalized_model:
            raise ValueError("fixed-single benchmark 必须指定 main_model")
        normalized_allowed = [normalized_model]
        routing_mode: ModelRoutingMode = "fixed"
        collaboration_mode: CollaborationMode = "single"
    elif strategy == "auto-route":
        if len(normalized_allowed) < 2:
            raise ValueError("auto-route benchmark 必须明确允许至少两个模型")
        routing_mode = "auto"
        collaboration_mode = "single"
    else:
        if len(normalized_allowed) < 2:
            raise ValueError("multi-model benchmark 必须明确允许至少两个模型")
        if execution_depth == "fast":
            raise ValueError("multi-model benchmark 不能使用 fast 执行深度")
        routing_mode = "auto"
        collaboration_mode = "multi"
    return BenchmarkAgentPolicy(
        strategy=strategy,
        routing_mode=routing_mode,
        collaboration_mode=collaboration_mode,
        execution_depth=execution_depth,
        main_model=normalized_model,
        allowed_models=normalized_allowed,
    )


def apply_benchmark_policy(session: Session, policy: BenchmarkAgentPolicy) -> None:
    """Apply all controlled variables to a fresh benchmark session."""
    session.approval_mode = "auto"
    session.model_routing_mode = policy.routing_mode
    session.model_routing_allowed_models = list(policy.allowed_models)
    session.collaboration_mode = policy.collaboration_mode
    session.execution_depth = policy.execution_depth


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _bounded_trajectory(events: list[Any]) -> list[dict[str, Any]]:
    trajectory: list[dict[str, Any]] = []
    for event in events:
        item: dict[str, Any] = {"type": event.type}
        if event.task:
            item["task"] = {
                key: event.task.get(key)
                for key in ("id", "type", "assigned_model", "success")
                if key in event.task
            }
            if event.task.get("tool_calls"):
                item["task"]["tool_calls"] = len(event.task["tool_calls"])
        if event.failover:
            item["failover"] = {
                key: event.failover.get(key)
                for key in ("from_model", "to_model", "reason", "error_code")
                if key in event.failover
            }
        if event.engineering:
            item["engineering_status"] = event.engineering.get("status", "")
        trajectory.append(item)
    return trajectory[-200:]


async def run_headless_benchmark_agent(
    instruction: str,
    *,
    project_root: str | Path,
    config_dir: str | Path,
    state_dir: str | Path,
    strategy: BenchmarkAgentStrategy,
    execution_depth: ExecutionDepthPreference = "standard",
    main_model: str = "",
    allowed_models: list[str] | None = None,
    provider_attempt_guard: Callable[[], None] | None = None,
) -> BenchmarkAgentResult:
    """Execute one isolated benchmark turn through MAO's production Agent path."""
    project = Path(project_root).expanduser().resolve()
    config = Path(config_dir).expanduser().resolve()
    state = Path(state_dir).expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"benchmark project_root 不存在：{project}")
    if not (config / "providers.yaml").is_file():
        raise ValueError(f"benchmark Provider 配置不存在：{config / 'providers.yaml'}")
    state.mkdir(parents=True, exist_ok=True)

    policy = resolve_benchmark_policy(
        strategy,
        execution_depth=execution_depth,
        main_model=main_model,
        allowed_models=allowed_models,
    )
    gateway = GatewayClient(config_path=str(config / "providers.yaml"))
    gateway.before_provider_attempt = provider_attempt_guard
    unknown_models = [
        model for model in policy.allowed_models if model not in gateway.models
    ]
    if unknown_models:
        raise ValueError(f"benchmark 允许模型未配置：{unknown_models}")
    if policy.main_model:
        if policy.main_model not in gateway.models:
            raise ValueError(f"benchmark 模型未配置：{policy.main_model}")
        gateway.main_model = policy.main_model
    if policy.allowed_models:
        if gateway.main_model not in policy.allowed_models:
            raise ValueError("benchmark main_model 必须位于 allowed_models 中")
        gateway.models = {
            alias: config
            for alias, config in gateway.models.items()
            if alias in policy.allowed_models
        }
        router = getattr(gateway, "router", None)
        if router is not None:
            router.models = gateway.models

    store = SessionStore(base_dir=str(state / "sessions"))
    session = store.create(title=f"benchmark:{policy.strategy}")
    session.config_dir = str(config)
    apply_benchmark_policy(session, policy)
    store.save(session)
    memory_store = MemoryStore(config_path=str(state / "config" / "memory.yaml"))
    agent = Agent(
        gateway,
        session,
        approval_mode="auto",
        memory_store=memory_store,
    )
    bounded_request = (
        f"{instruction.strip()}\n\n"
        f"评测边界：项目根目录为 {project}。"
        "所有读取、写入和命令必须限制在该根目录内，相对路径以该目录为基准。\n\n"
    )
    events: list[Any] = []
    caught_error: Exception | None = None
    try:
        with _working_directory(project):
            async for event in agent.run_turn_stream(bounded_request):
                events.append(event)
    except Exception as exc:
        caught_error = exc
    store.save(session)

    done = next((event for event in reversed(events) if event.type == "done"), None)
    engineering_event = next(
        (event for event in reversed(events) if event.type == "engineering_complete"),
        None,
    )
    engineering = engineering_event.engineering if engineering_event else {}
    billing = gateway.billing.summary()
    calls = list(billing.get("calls") or [])
    trace = list(getattr(gateway, "last_attempt_trace", []) or [])
    total_provider_attempts = int(
        getattr(gateway, "provider_attempts_total", len(trace)) or 0
    )
    upstream_model_ids = list(dict.fromkeys(
        str(item.get("model", "")).strip()
        for item in calls
        if str(item.get("model", "")).strip()
    ))
    actual_models: list[str] = []
    for item in [*trace, *calls]:
        raw_model = str(item.get("model", "")).strip()
        if not raw_model:
            continue
        alias = raw_model
        if raw_model not in gateway.models:
            alias = next(
                (
                    name
                    for name, model_config in gateway.models.items()
                    if getattr(model_config, "model_id", "") == raw_model
                ),
                raw_model,
            )
        if alias not in actual_models:
            actual_models.append(alias)
    collaboration_tool_calls = sum(
        len(event.task.get("tool_calls") or [])
        for event in events
        if event.type == "task_complete" and event.task
    )
    if done is None:
        error = next((event.error for event in reversed(events) if event.error), "")
        error = error or (str(caught_error) if caught_error else "")
        return BenchmarkAgentResult(
            session_id=session.id,
            run_id=str(engineering.get("run_id", "")),
            status="failed",
            policy=policy,
            provider_calls=len(calls),
            provider_attempts=max(
                total_provider_attempts,
                len(trace),
                int(getattr(caught_error, "attempts", 0) or 0),
            ),
            actual_models=actual_models,
            upstream_model_ids=upstream_model_ids,
            trajectory=_bounded_trajectory(events),
            engineering=engineering,
            error=error or "benchmark Agent 未返回 done 事件",
        )
    return BenchmarkAgentResult(
        session_id=session.id,
        run_id=str(engineering.get("run_id", "")),
        status=engineering.get("status", "completed"),
        policy=policy,
        response=done.assistant_message,
        input_tokens=done.input_tokens,
        output_tokens=done.output_tokens,
        cost_usd=done.cost_usd,
        provider_calls=len(calls),
        provider_attempts=max(total_provider_attempts, len(trace), len(calls)),
        actual_models=actual_models,
        upstream_model_ids=upstream_model_ids,
        tool_calls=len(done.tool_calls) + collaboration_tool_calls,
        files_written=done.files_written,
        trajectory=_bounded_trajectory(events),
        engineering=engineering,
        error=str(caught_error) if caught_error else "",
    )


def run_headless_benchmark_agent_sync(*args: Any, **kwargs: Any) -> BenchmarkAgentResult:
    """Synchronous wrapper for CLI and benchmark harness integrations."""
    return asyncio.run(run_headless_benchmark_agent(*args, **kwargs))

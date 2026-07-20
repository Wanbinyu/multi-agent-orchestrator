"""Reproducible engineering benchmark contracts and isolated harness."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import shlex
import shutil
import threading
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from src.core.engineering.models import utc_now
from src.tools.worker_tools import run_command


BenchmarkCategory = Literal[
    "question",
    "diagnosis",
    "small_change",
    "build",
    "review",
    "migration",
]
BenchmarkExecutionStatus = Literal["completed", "failed", "timeout"]
BenchmarkDataKind = Literal["synthetic_contract", "live_provider"]
BenchmarkComparisonStrategy = Literal[
    "contract-only", "fixed-single", "auto-route", "multi-model"
]
_TASK_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_VERIFICATION_EXECUTABLES = {
    "node", "npm", "npm.cmd", "npx", "npx.cmd", "pnpm", "pnpm.cmd",
    "pytest", "python", "python.exe", "python3", "yarn", "yarn.cmd",
}
_INLINE_EXECUTION_FLAGS = {"-c", "-e", "--eval", "--print", "-p"}


def _relative_path(value: str, *, allow_glob: bool = False) -> str:
    normalized = value.strip().replace("\\", "/")
    if not normalized:
        raise ValueError("benchmark 路径不能为空")
    if re.match(r"^[A-Za-z]:", normalized) or normalized.startswith("/"):
        raise ValueError(f"benchmark 路径必须是相对路径：{value}")
    path = PurePosixPath(normalized)
    if ".." in path.parts or "." in path.parts:
        raise ValueError(f"benchmark 路径不能越出夹具目录：{value}")
    if not allow_glob and any(char in normalized for char in "*?[]"):
        raise ValueError(f"benchmark 文件路径不能包含 glob：{value}")
    return path.as_posix()


def _matches_any(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatchcase(path, pattern):
            return True
        if pattern.endswith("/**") and path.startswith(pattern[:-3].rstrip("/") + "/"):
            return True
    return False


def _verification_command(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("benchmark verification commands 不能为空")
    try:
        argv = shlex.split(normalized)
    except ValueError as exc:
        raise ValueError("benchmark verification command 无法解析") from exc
    executable = Path(argv[0]).name.casefold()
    if executable not in _VERIFICATION_EXECUTABLES:
        raise ValueError(f"benchmark verification executable 不允许：{executable}")
    if _INLINE_EXECUTION_FLAGS.intersection(arg.casefold() for arg in argv[1:]):
        raise ValueError("benchmark verification command 禁止解释器内联代码")
    for argument in argv[1:]:
        candidate = argument.split("=", 1)[-1].replace("\\", "/")
        if re.match(r"^[A-Za-z]:", candidate) or candidate.startswith("/"):
            raise ValueError("benchmark verification command 禁止绝对路径")
        if ".." in PurePosixPath(candidate).parts:
            raise ValueError("benchmark verification command 禁止父目录路径")
    return normalized


class BenchmarkFileExpectation(BaseModel):
    """Expected workspace state after one strategy execution."""

    path: str = Field(..., min_length=1)
    exists: bool = True
    equals: str | None = None
    contains: str | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _relative_path(value)

    @model_validator(mode="after")
    def validate_content_contract(self) -> "BenchmarkFileExpectation":
        if not self.exists and (self.equals is not None or self.contains is not None):
            raise ValueError("不存在的文件不能声明 equals/contains")
        return self


class BenchmarkVerificationContract(BaseModel):
    """Deterministic checks shared by every benchmark strategy."""

    response_contains: list[str] = Field(default_factory=list)
    files: list[BenchmarkFileExpectation] = Field(default_factory=list)
    commands: list[str] = Field(..., min_length=1)

    @field_validator("response_contains")
    @classmethod
    def normalize_response_contains(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("commands")
    @classmethod
    def normalize_commands(cls, values: list[str]) -> list[str]:
        normalized = list(
            dict.fromkeys(_verification_command(value) for value in values)
        )
        if not normalized:
            raise ValueError("benchmark verification commands 不能为空")
        return normalized

    @model_validator(mode="after")
    def validate_unique_file_checks(self) -> "BenchmarkVerificationContract":
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("benchmark verification 不能重复检查同一文件")
        return self


class BenchmarkFixtureWrite(BaseModel):
    """One bounded mutation produced by the offline fixture strategy."""

    path: str = Field(..., min_length=1)
    content: str = ""

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _relative_path(value)


class BenchmarkOfflineFixture(BaseModel):
    """Synthetic execution used to validate the harness without a Provider."""

    response: str = Field(..., min_length=1)
    writes: list[BenchmarkFixtureWrite] = Field(default_factory=list)
    deletes: list[str] = Field(default_factory=list)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @field_validator("deletes")
    @classmethod
    def validate_deletes(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(_relative_path(value) for value in values))

    @model_validator(mode="after")
    def validate_unique_mutations(self) -> "BenchmarkOfflineFixture":
        writes = [item.path for item in self.writes]
        if len(writes) != len(set(writes)):
            raise ValueError("offline fixture 不能重复写同一路径")
        overlap = set(writes).intersection(self.deletes)
        if overlap:
            raise ValueError(f"offline fixture 不能同时写入和删除：{sorted(overlap)}")
        return self


class BenchmarkTask(BaseModel):
    """One public engineering task and its deterministic acceptance contract."""

    id: str = Field(..., min_length=2, max_length=64)
    category: BenchmarkCategory
    request: str = Field(..., min_length=1, max_length=20_000)
    source: str = Field(..., min_length=1, max_length=500)
    risk_level: Literal["low", "medium", "high"]
    project_dir: str = Field(..., min_length=1)
    allowed_mutations: list[str] = Field(default_factory=list)
    verification: BenchmarkVerificationContract
    offline_fixture: BenchmarkOfflineFixture

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not _TASK_ID.fullmatch(normalized):
            raise ValueError("benchmark task id 只能使用小写字母、数字、_ 和 -")
        return normalized

    @field_validator("project_dir")
    @classmethod
    def validate_project_dir(cls, value: str) -> str:
        return _relative_path(value)

    @field_validator("allowed_mutations")
    @classmethod
    def validate_allowed_mutations(cls, values: list[str]) -> list[str]:
        return list(
            dict.fromkeys(_relative_path(value, allow_glob=True) for value in values)
        )

    @model_validator(mode="after")
    def validate_fixture_boundaries(self) -> "BenchmarkTask":
        mutated = [item.path for item in self.offline_fixture.writes]
        mutated.extend(self.offline_fixture.deletes)
        rejected = [
            path for path in mutated if not _matches_any(path, self.allowed_mutations)
        ]
        if rejected:
            raise ValueError(
                f"offline fixture mutation 未在 allowed_mutations 声明：{rejected}"
            )
        return self


class BenchmarkSuite(BaseModel):
    """Versioned collection of benchmark tasks."""

    schema_version: Literal[1] = 1
    id: str = Field(..., min_length=2, max_length=64)
    description: str = Field(..., min_length=1)
    data_policy: str = Field(..., min_length=1)
    tasks: list[BenchmarkTask] = Field(..., min_length=1, max_length=200)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not _TASK_ID.fullmatch(normalized):
            raise ValueError("benchmark suite id 格式无效")
        return normalized

    @model_validator(mode="after")
    def validate_unique_tasks(self) -> "BenchmarkSuite":
        task_ids = [task.id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("benchmark suite task id 必须唯一")
        return self


class BenchmarkExecution(BaseModel):
    """Raw strategy output before deterministic harness verification."""

    status: BenchmarkExecutionStatus = "completed"
    response: str = ""
    error: str = ""
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    tool_calls: int = Field(default=0, ge=0)
    provider_calls: int = Field(default=0, ge=0)
    provider_attempts: int = Field(default=0, ge=0)
    synthetic_usage: bool = False
    actual_models: list[str] = Field(default_factory=list)
    upstream_model_ids: list[str] = Field(default_factory=list)
    internal_status: str = ""
    trajectory: list[dict[str, Any]] = Field(default_factory=list)


class LiveBenchmarkAuthorization(BaseModel):
    """Owner-confirmed boundary required before any live benchmark call."""

    confirmation_reference: str = Field(..., min_length=1)
    allowed_models: list[str] = Field(..., min_length=1)
    max_provider_calls: int = Field(..., ge=1)
    stop_after_cost_usd: float = Field(..., gt=0.0)
    result_visibility: Literal["private", "aggregate", "full"] = "private"

    @field_validator("allowed_models")
    @classmethod
    def normalize_allowed_models(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip() for item in values if item.strip()))
        if not normalized:
            raise ValueError("live benchmark allowed_models 不能为空")
        return normalized


class LiveBenchmarkSpendGuard:
    """Shared hard attempt ceiling and post-paid cost threshold."""

    def __init__(self, authorization: LiveBenchmarkAuthorization):
        self.authorization = authorization
        self.provider_calls = 0
        self.provider_attempts = 0
        self.cost_usd = 0.0
        self._lock = threading.Lock()

    def ensure_can_start(self) -> None:
        with self._lock:
            self._ensure_can_start_unlocked()

    def _ensure_can_start_unlocked(self) -> None:
        if self.provider_attempts >= self.authorization.max_provider_calls:
            raise RuntimeError("live benchmark Provider 调用次数已到停止阈值")
        if self.cost_usd >= self.authorization.stop_after_cost_usd:
            raise RuntimeError("live benchmark 费用已到停止阈值")

    def reserve_provider_attempt(self) -> None:
        """Reserve one attempt before a Provider network request is sent."""
        with self._lock:
            self._ensure_can_start_unlocked()
            self.provider_attempts += 1

    def record(
        self,
        *,
        provider_calls: int,
        provider_attempts: int,
        cost_usd: float,
        attempts_reserved: bool = False,
    ) -> list[str]:
        with self._lock:
            self.provider_calls += provider_calls
            if not attempts_reserved:
                self.provider_attempts += provider_attempts
            self.cost_usd = round(self.cost_usd + cost_usd, 9)
            issues: list[str] = []
            if self.provider_attempts > self.authorization.max_provider_calls:
                issues.append("Provider 调用次数超过停止阈值")
            if self.cost_usd > self.authorization.stop_after_cost_usd:
                issues.append("费用超过本地后付费停止阈值")
            return issues


class BenchmarkStrategyProfile(BaseModel):
    """Controlled variables attached to every reported strategy."""

    comparison_strategy: BenchmarkComparisonStrategy = "contract-only"
    routing_mode: Literal["auto", "fixed"] = "fixed"
    collaboration_mode: Literal["auto", "single", "multi"] = "single"
    execution_depth: Literal["auto", "fast", "standard", "deep"] = "standard"
    configured_models: list[str] = Field(default_factory=list)


class BenchmarkStrategy(Protocol):
    """Execution adapter; fixture and live strategies share this boundary."""

    strategy_id: str
    data_kind: BenchmarkDataKind
    profile: BenchmarkStrategyProfile

    def execute(self, task: BenchmarkTask, workspace: Path) -> BenchmarkExecution:
        """Execute exactly one task inside its isolated workspace."""


class FixtureBenchmarkStrategy:
    """Apply declared synthetic output without reading Provider configuration."""

    data_kind: BenchmarkDataKind = "synthetic_contract"

    def __init__(
        self,
        strategy_id: str,
        *,
        profile: BenchmarkStrategyProfile | None = None,
    ):
        if not _TASK_ID.fullmatch(strategy_id):
            raise ValueError("benchmark strategy id 格式无效")
        self.strategy_id = strategy_id
        self.profile = profile or BenchmarkStrategyProfile()

    def execute(self, task: BenchmarkTask, workspace: Path) -> BenchmarkExecution:
        fixture = task.offline_fixture
        for item in fixture.writes:
            target = _workspace_path(workspace, item.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(item.content, encoding="utf-8")
        for relative in fixture.deletes:
            target = _workspace_path(workspace, relative)
            if target.is_file():
                target.unlink()
        return BenchmarkExecution(
            status="completed",
            response=fixture.response,
            input_tokens=fixture.input_tokens,
            output_tokens=fixture.output_tokens,
            tool_calls=len(fixture.writes) + len(fixture.deletes),
            provider_calls=0,
            cost_usd=0.0,
            synthetic_usage=True,
            internal_status="synthetic",
        )


class MaoLiveBenchmarkStrategy:
    """Run one MAO strategy through the shared harness after explicit authorization."""

    data_kind: BenchmarkDataKind = "live_provider"

    def __init__(
        self,
        strategy_id: str,
        *,
        profile: BenchmarkStrategyProfile,
        config_dir: str | Path,
        state_root: str | Path,
        main_model: str,
        spend_guard: LiveBenchmarkSpendGuard,
    ):
        if not _TASK_ID.fullmatch(strategy_id):
            raise ValueError("benchmark strategy id 格式无效")
        if profile.comparison_strategy == "contract-only":
            raise ValueError("live benchmark 必须声明对比策略")
        configured = set(profile.configured_models)
        allowed = set(spend_guard.authorization.allowed_models)
        if configured and not configured.issubset(allowed):
            raise ValueError("live benchmark profile 包含未授权模型")
        if main_model not in allowed:
            raise ValueError("live benchmark main_model 未授权")
        self.strategy_id = strategy_id
        self.profile = profile
        self.config_dir = Path(config_dir).expanduser().resolve()
        self.state_root = Path(state_root).expanduser().resolve()
        self.main_model = main_model
        self.spend_guard = spend_guard

    def execute(self, task: BenchmarkTask, workspace: Path) -> BenchmarkExecution:
        self.spend_guard.ensure_can_start()
        from src.core.engineering.benchmark_agent import (
            run_headless_benchmark_agent_sync,
        )

        result = run_headless_benchmark_agent_sync(
            task.request,
            project_root=workspace,
            config_dir=self.config_dir,
            state_dir=self.state_root / self.strategy_id / task.id,
            strategy=self.profile.comparison_strategy,
            execution_depth=self.profile.execution_depth,
            main_model=self.main_model,
            allowed_models=self.spend_guard.authorization.allowed_models,
            provider_attempt_guard=self.spend_guard.reserve_provider_attempt,
        )
        budget_issues = self.spend_guard.record(
            provider_calls=result.provider_calls,
            provider_attempts=result.provider_attempts,
            cost_usd=result.cost_usd,
            attempts_reserved=True,
        )
        strategy_issues: list[str] = []
        if (
            self.profile.comparison_strategy == "multi-model"
            and task.category in {"small_change", "build", "migration"}
            and len(result.actual_models) < 2
        ):
            strategy_issues.append(
                "multi-model 工程策略未实际调用至少两个模型"
            )
        execution_issues = [result.error, *budget_issues, *strategy_issues]
        return BenchmarkExecution(
            status=(
                "failed"
                if result.status == "failed" or budget_issues or strategy_issues
                else "completed"
            ),
            response=result.response,
            error="；".join(execution_issues).strip("；"),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=result.cost_usd,
            tool_calls=result.tool_calls,
            provider_calls=result.provider_calls,
            provider_attempts=result.provider_attempts,
            synthetic_usage=False,
            actual_models=result.actual_models,
            upstream_model_ids=result.upstream_model_ids,
            internal_status=result.status,
            trajectory=result.trajectory,
        )


class BenchmarkCheckResult(BaseModel):
    name: str
    passed: bool
    actual: str = ""


class BenchmarkRunResult(BaseModel):
    task_id: str
    category: BenchmarkCategory
    strategy_id: str
    data_kind: BenchmarkDataKind
    strategy_profile: BenchmarkStrategyProfile = Field(
        default_factory=BenchmarkStrategyProfile
    )
    trial: int = Field(..., ge=1)
    status: BenchmarkExecutionStatus
    passed: bool
    issues: list[str] = Field(default_factory=list)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    tool_calls: int = Field(default=0, ge=0)
    provider_calls: int = Field(default=0, ge=0)
    provider_attempts: int = Field(default=0, ge=0)
    actual_models: list[str] = Field(default_factory=list)
    upstream_model_ids: list[str] = Field(default_factory=list)
    internal_status: str = ""
    trajectory: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: float = Field(default=0.0, ge=0.0)
    mutations: list[str] = Field(default_factory=list)
    unauthorized_mutations: list[str] = Field(default_factory=list)
    checks: list[BenchmarkCheckResult] = Field(default_factory=list)
    verification_pass_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    deterministic_signature: str


class BenchmarkAggregate(BaseModel):
    strategy_id: str
    data_kind: BenchmarkDataKind
    strategy_profile: BenchmarkStrategyProfile = Field(
        default_factory=BenchmarkStrategyProfile
    )
    run_count: int = Field(default=0, ge=0)
    completion_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    verification_pass_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    mis_modification_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    tool_calls: int = Field(default=0, ge=0)
    provider_calls: int = Field(default=0, ge=0)
    provider_attempts: int = Field(default=0, ge=0)
    actual_models: list[str] = Field(default_factory=list)
    upstream_model_ids: list[str] = Field(default_factory=list)
    elapsed_ms: float = Field(default=0.0, ge=0.0)


class BenchmarkStability(BaseModel):
    strategy_id: str
    task_id: str
    trials: int = Field(..., ge=1)
    unique_signatures: int = Field(..., ge=1)
    stable: bool


class BenchmarkReport(BaseModel):
    schema_version: Literal[1] = 1
    run_id: str
    suite_id: str
    selected_task_ids: list[str] = Field(default_factory=list)
    created_at: str
    repeats: int = Field(..., ge=1)
    passed: bool
    require_zero_provider_calls: bool
    require_stable_results: bool
    provider_calls: int = Field(default=0, ge=0)
    provider_attempts: int = Field(default=0, ge=0)
    issues: list[str] = Field(default_factory=list)
    strategy_profiles: dict[str, BenchmarkStrategyProfile] = Field(default_factory=dict)
    results: list[BenchmarkRunResult] = Field(default_factory=list)
    aggregates: list[BenchmarkAggregate] = Field(default_factory=list)
    stability: list[BenchmarkStability] = Field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            f"# Benchmark Report: {self.suite_id}",
            "",
            f"- Run: `{self.run_id}`",
            f"- Tasks: {', '.join(self.selected_task_ids)}",
            f"- Repeats: {self.repeats}",
            f"- Passed: {'yes' if self.passed else 'no'}",
            f"- Provider calls: {self.provider_calls}",
            f"- Stable results required: {'yes' if self.require_stable_results else 'no'}",
            "",
            "## Strategy Metrics",
            "",
            "| Strategy | Data | Comparison | Routing | Collaboration | Depth | Actual models | Runs | Completion | Verification | Mis-modification | Tokens in/out | Cost | Tools |",
            "|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for item in self.aggregates:
            lines.append(
                "| "
                f"{item.strategy_id} | {item.data_kind} | "
                f"{item.strategy_profile.comparison_strategy} | "
                f"{item.strategy_profile.routing_mode} | "
                f"{item.strategy_profile.collaboration_mode} | "
                f"{item.strategy_profile.execution_depth} | "
                f"{', '.join(item.actual_models) or '-'} | {item.run_count} | "
                f"{item.completion_rate:.1%} | {item.verification_pass_rate:.1%} | "
                f"{item.mis_modification_rate:.1%} | "
                f"{item.input_tokens}/{item.output_tokens} | "
                f"${item.cost_usd:.6f} | {item.tool_calls} |"
            )
        lines.extend(["", "## Stability", ""])
        for item in self.stability:
            marker = "PASS" if item.stable else "FAIL"
            lines.append(
                f"- {marker} `{item.strategy_id}/{item.task_id}`: "
                f"{item.unique_signatures} signature(s) across {item.trials} trials"
            )
        if self.issues:
            lines.extend(["", "## Issues", ""])
            lines.extend(f"- {issue}" for issue in self.issues)
        return "\n".join(lines) + "\n"


def load_benchmark_suite(path: str | Path) -> BenchmarkSuite:
    suite_path = Path(path).expanduser().resolve()
    data = yaml.safe_load(suite_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("benchmark suite 必须是 YAML mapping")
    return BenchmarkSuite(**data)


class EngineeringBenchmarkHarness:
    """Run all strategies through identical isolated tasks and acceptance checks."""

    def __init__(
        self,
        suite_path: str | Path,
        output_root: str | Path,
        strategies: list[BenchmarkStrategy],
    ):
        self.suite_path = Path(suite_path).expanduser().resolve()
        self.suite_root = self.suite_path.parent
        self.output_root = Path(output_root).expanduser().resolve()
        self.suite = load_benchmark_suite(self.suite_path)
        if not strategies:
            raise ValueError("benchmark 至少需要一个 strategy")
        ids = [strategy.strategy_id for strategy in strategies]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark strategy id 必须唯一")
        if any(not _TASK_ID.fullmatch(item) for item in ids):
            raise ValueError("benchmark strategy id 格式无效")
        if any(
            strategy.data_kind not in {"synthetic_contract", "live_provider"}
            for strategy in strategies
        ):
            raise ValueError("benchmark strategy data_kind 格式无效")
        self.strategies = strategies
        self.strategy_profiles = {
            strategy.strategy_id: getattr(
                strategy, "profile", BenchmarkStrategyProfile()
            )
            for strategy in strategies
        }
        self._validate_projects()

    def run(
        self,
        *,
        repeats: int = 3,
        require_zero_provider_calls: bool = True,
        require_stable_results: bool = True,
        task_ids: list[str] | None = None,
        fail_fast: bool = False,
    ) -> BenchmarkReport:
        if repeats < 1 or repeats > 20:
            raise ValueError("benchmark repeats 必须在 1 到 20 之间")
        run_id = f"bench-{uuid.uuid4().hex[:12]}"
        run_root = self.output_root / run_id
        run_root.mkdir(parents=True, exist_ok=False)
        selected_ids = list(dict.fromkeys(task_ids or []))
        available_ids = {task.id for task in self.suite.tasks}
        unknown_ids = [task_id for task_id in selected_ids if task_id not in available_ids]
        if unknown_ids:
            raise ValueError(f"benchmark task_ids 不存在：{unknown_ids}")
        selected_tasks = (
            [task for task in self.suite.tasks if task.id in selected_ids]
            if selected_ids
            else self.suite.tasks
        )
        results: list[BenchmarkRunResult] = []
        stop_requested = False
        for strategy in self.strategies:
            if stop_requested:
                break
            for trial in range(1, repeats + 1):
                if stop_requested:
                    break
                for task in selected_tasks:
                    result = self._run_one(run_root, strategy, task, trial)
                    results.append(result)
                    if fail_fast and not result.passed:
                        stop_requested = True
                        break

        stability = self._build_stability(results)
        aggregates = self._build_aggregates(results)
        provider_calls = sum(item.provider_calls for item in results)
        provider_attempts = sum(item.provider_attempts for item in results)
        issues: list[str] = []
        if any(not item.passed for item in results):
            issues.append("至少一个 benchmark task 未通过确定性验收")
        if require_stable_results and any(not item.stable for item in stability):
            issues.append("至少一个 strategy/task 在重复运行中结果不稳定")
        if require_zero_provider_calls and provider_calls:
            issues.append(f"离线 benchmark 发生 {provider_calls} 次 Provider 调用")
        return BenchmarkReport(
            run_id=run_id,
            suite_id=self.suite.id,
            selected_task_ids=[task.id for task in selected_tasks],
            created_at=utc_now(),
            repeats=repeats,
            passed=not issues,
            require_zero_provider_calls=require_zero_provider_calls,
            require_stable_results=require_stable_results,
            provider_calls=provider_calls,
            provider_attempts=provider_attempts,
            issues=issues,
            strategy_profiles=self.strategy_profiles,
            results=results,
            aggregates=aggregates,
            stability=stability,
        )

    def _validate_projects(self) -> None:
        for task in self.suite.tasks:
            project = (self.suite_root / task.project_dir).resolve()
            if not project.is_relative_to(self.suite_root) or not project.is_dir():
                raise ValueError(f"benchmark project_dir 不存在或越界：{task.project_dir}")
            if any(path.is_symlink() for path in project.rglob("*")):
                raise ValueError(f"benchmark project_dir 禁止符号链接：{task.project_dir}")
            if self.output_root.is_relative_to(project):
                raise ValueError("benchmark output_root 不能位于任务项目目录内")

    def _run_one(
        self,
        run_root: Path,
        strategy: BenchmarkStrategy,
        task: BenchmarkTask,
        trial: int,
    ) -> BenchmarkRunResult:
        started = time.perf_counter()
        source = (self.suite_root / task.project_dir).resolve()
        workspace = run_root / strategy.strategy_id / f"trial-{trial}" / task.id
        workspace.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, workspace)
        before = _snapshot(workspace)
        try:
            execution = strategy.execute(task, workspace)
        except Exception as exc:
            execution = BenchmarkExecution(
                status="failed",
                error=f"{type(exc).__name__}: {str(exc)[:500]}",
            )
        after = _snapshot(workspace)
        mutations = _mutations(before, after)
        unauthorized = [
            path for path in mutations if not _matches_any(path, task.allowed_mutations)
        ]
        checks = self._verify(task, workspace, execution)
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        issues: list[str] = []
        if execution.status != "completed":
            issues.append(execution.error or f"strategy status: {execution.status}")
        if not execution.response.strip():
            issues.append("strategy 返回空响应")
        if unauthorized:
            issues.append(f"发生越界修改：{', '.join(unauthorized)}")
        issues.extend(item.actual for item in checks if not item.passed)
        passed_checks = sum(item.passed for item in checks)
        verification_rate = passed_checks / len(checks) if checks else 0.0
        signature_payload = {
            "status": execution.status,
            "passed": not issues,
            "issues": issues,
            "input_tokens": execution.input_tokens,
            "output_tokens": execution.output_tokens,
            "cost_usd": round(execution.cost_usd, 9),
            "tool_calls": execution.tool_calls,
            "provider_calls": execution.provider_calls,
            "provider_attempts": execution.provider_attempts,
            "actual_models": execution.actual_models,
            "upstream_model_ids": execution.upstream_model_ids,
            "internal_status": execution.internal_status,
            "mutations": mutations,
            "unauthorized_mutations": unauthorized,
            "checks": [item.model_dump() for item in checks],
        }
        signature = hashlib.sha256(
            json.dumps(
                signature_payload, ensure_ascii=False, sort_keys=True
            ).encode("utf-8")
        ).hexdigest()
        return BenchmarkRunResult(
            task_id=task.id,
            category=task.category,
            strategy_id=strategy.strategy_id,
            data_kind=strategy.data_kind,
            strategy_profile=self.strategy_profiles[strategy.strategy_id],
            trial=trial,
            status=execution.status,
            passed=not issues,
            issues=issues,
            input_tokens=execution.input_tokens,
            output_tokens=execution.output_tokens,
            cost_usd=round(execution.cost_usd, 9),
            tool_calls=execution.tool_calls,
            provider_calls=execution.provider_calls,
            provider_attempts=execution.provider_attempts,
            actual_models=execution.actual_models,
            upstream_model_ids=execution.upstream_model_ids,
            internal_status=execution.internal_status,
            trajectory=execution.trajectory,
            duration_ms=duration_ms,
            mutations=mutations,
            unauthorized_mutations=unauthorized,
            checks=checks,
            verification_pass_rate=verification_rate,
            deterministic_signature=signature,
        )

    @staticmethod
    def _verify(
        task: BenchmarkTask,
        workspace: Path,
        execution: BenchmarkExecution,
    ) -> list[BenchmarkCheckResult]:
        checks: list[BenchmarkCheckResult] = []
        folded = execution.response.casefold()
        for expected in task.verification.response_contains:
            passed = expected.casefold() in folded
            checks.append(BenchmarkCheckResult(
                name=f"response_contains:{expected}",
                passed=passed,
                actual=("响应包含预期文本" if passed else f"响应缺少：{expected}"),
            ))
        for expected in task.verification.files:
            target = _workspace_path(workspace, expected.path)
            exists = target.is_file()
            passed = exists == expected.exists
            actual = (
                f"{expected.path} 存在状态符合预期"
                if passed else f"{expected.path} exists={exists}，预期 {expected.exists}"
            )
            if passed and exists and (expected.equals is not None or expected.contains is not None):
                try:
                    content = target.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as exc:
                    passed = False
                    actual = f"{expected.path} 无法按 UTF-8 读取：{type(exc).__name__}"
                else:
                    if expected.equals is not None and content != expected.equals:
                        passed = False
                        actual = f"{expected.path} 内容不等于合同值"
                    if expected.contains is not None and expected.contains not in content:
                        passed = False
                        actual = f"{expected.path} 缺少合同文本"
            checks.append(BenchmarkCheckResult(
                name=f"file:{expected.path}", passed=passed, actual=actual
            ))
        for command in task.verification.commands:
            result = run_command(command, cwd=str(workspace), timeout=15)
            checks.append(BenchmarkCheckResult(
                name=f"command:{command}",
                passed=result.success,
                actual=(
                    result.output[:500]
                    if result.success
                    else (result.error or "验证命令失败")[:500]
                ),
            ))
        return checks

    @staticmethod
    def _build_stability(
        results: list[BenchmarkRunResult],
    ) -> list[BenchmarkStability]:
        grouped: dict[tuple[str, str], list[BenchmarkRunResult]] = {}
        for item in results:
            grouped.setdefault((item.strategy_id, item.task_id), []).append(item)
        return [
            BenchmarkStability(
                strategy_id=strategy_id,
                task_id=task_id,
                trials=len(items),
                unique_signatures=len({item.deterministic_signature for item in items}),
                stable=len({item.deterministic_signature for item in items}) == 1,
            )
            for (strategy_id, task_id), items in sorted(grouped.items())
        ]

    @staticmethod
    def _build_aggregates(
        results: list[BenchmarkRunResult],
    ) -> list[BenchmarkAggregate]:
        grouped: dict[str, list[BenchmarkRunResult]] = {}
        for item in results:
            grouped.setdefault(item.strategy_id, []).append(item)
        aggregates: list[BenchmarkAggregate] = []
        for strategy_id, items in sorted(grouped.items()):
            checks = [check for item in items for check in item.checks]
            mutations = sum(len(item.mutations) for item in items)
            unauthorized = sum(len(item.unauthorized_mutations) for item in items)
            aggregates.append(BenchmarkAggregate(
                strategy_id=strategy_id,
                data_kind=items[0].data_kind,
                strategy_profile=items[0].strategy_profile,
                run_count=len(items),
                completion_rate=sum(item.passed for item in items) / len(items),
                verification_pass_rate=(
                    sum(check.passed for check in checks) / len(checks)
                    if checks else 0.0
                ),
                mis_modification_rate=(unauthorized / mutations if mutations else 0.0),
                input_tokens=sum(item.input_tokens for item in items),
                output_tokens=sum(item.output_tokens for item in items),
                cost_usd=round(sum(item.cost_usd for item in items), 9),
                tool_calls=sum(item.tool_calls for item in items),
                provider_calls=sum(item.provider_calls for item in items),
                provider_attempts=sum(item.provider_attempts for item in items),
                actual_models=list(dict.fromkeys(
                    model
                    for item in items
                    for model in item.actual_models
                )),
                upstream_model_ids=list(dict.fromkeys(
                    model
                    for item in items
                    for model in item.upstream_model_ids
                )),
                elapsed_ms=round(sum(item.duration_ms for item in items), 3),
            ))
        return aggregates


def write_benchmark_report(
    report: BenchmarkReport,
    *,
    json_path: str | Path | None = None,
    markdown_path: str | Path | None = None,
) -> None:
    if json_path is not None:
        target = Path(json_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(report.model_dump(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if markdown_path is not None:
        target = Path(markdown_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(report.to_markdown(), encoding="utf-8")


def _workspace_path(workspace: Path, relative: str) -> Path:
    root = workspace.resolve()
    target = (root / _relative_path(relative)).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"benchmark workspace 路径越界：{relative}")
    return target


def _snapshot(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def _mutations(before: dict[str, str], after: dict[str, str]) -> list[str]:
    paths = set(before).union(after)
    return sorted(path for path in paths if before.get(path) != after.get(path))

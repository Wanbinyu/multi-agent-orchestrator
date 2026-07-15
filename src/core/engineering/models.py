"""Phase 7 工程运行状态数据模型。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


TaskKind = Literal[
    "unclassified",
    "answer",
    "explain",
    "diagnose",
    "change",
    "build",
    "review",
    "plan",
    "monitor",
]
RiskLevel = Literal["unassessed", "low", "medium", "high", "external"]
VerificationDepth = Literal["none", "targeted", "standard", "deep", "continuous"]
ClassificationSource = Literal["rules", "inherited", "fallback"]
PlanStatus = Literal["pending", "in_progress", "completed", "failed", "blocked"]
RunStatus = Literal["running", "completed", "failed", "blocked"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskExecutionPolicy(BaseModel):
    """任务类型对应的执行边界。"""

    allow_project_writes: bool = False
    requires_plan: bool = False
    verification_depth: VerificationDepth = "targeted"
    collaboration_allowed: bool = False


class TaskIntent(BaseModel):
    """任务类型、作用域和授权边界。"""

    kind: TaskKind = "unclassified"
    scope: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = "unassessed"
    write_authorized: bool = False
    deliverables: list[str] = Field(default_factory=list)
    policy: TaskExecutionPolicy = Field(default_factory=TaskExecutionPolicy)
    classification_source: ClassificationSource = "fallback"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    classification_note: str = ""


class WorkPlanStep(BaseModel):
    """一个可追踪的工程计划步骤。"""

    id: str = Field(default_factory=lambda: f"step-{uuid.uuid4().hex[:8]}")
    title: str = Field(..., min_length=1)
    status: PlanStatus = "pending"
    evidence_ids: list[str] = Field(default_factory=list)
    note: str = ""


class WorkPlan(BaseModel):
    """带状态约束和验收标准的工作计划。"""

    objective: str = Field(..., min_length=1)
    steps: list[WorkPlanStep] = Field(default_factory=list)
    status: PlanStatus = "pending"
    acceptance_criteria: list[str] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_active_step(self) -> "WorkPlan":
        active = sum(step.status == "in_progress" for step in self.steps)
        if active > 1:
            raise ValueError("工作计划同时最多一个步骤处于 in_progress")
        return self

    def transition_step(
        self,
        step_id: str,
        status: PlanStatus,
        *,
        note: str | None = None,
        evidence_ids: list[str] | None = None,
    ) -> WorkPlanStep:
        """按固定状态机更新步骤，并同步计划总体状态。"""
        step = next((item for item in self.steps if item.id == step_id), None)
        if step is None:
            raise KeyError(f"计划步骤不存在：{step_id}")
        allowed: dict[PlanStatus, set[PlanStatus]] = {
            "pending": {"in_progress", "blocked"},
            "in_progress": {"completed", "failed", "blocked"},
            "completed": set(),
            "failed": set(),
            "blocked": set(),
        }
        if status not in allowed[step.status]:
            raise ValueError(f"非法计划状态迁移：{step.status} -> {status}")
        if status == "in_progress" and any(
            item.id != step_id and item.status == "in_progress" for item in self.steps
        ):
            raise ValueError("工作计划同时最多一个步骤处于 in_progress")

        step.status = status
        if note is not None:
            step.note = note
        if evidence_ids:
            step.evidence_ids = list(dict.fromkeys([*step.evidence_ids, *evidence_ids]))
        self.updated_at = utc_now()
        self._refresh_status()
        return step

    def _refresh_status(self) -> None:
        statuses = [step.status for step in self.steps]
        if statuses and all(status == "completed" for status in statuses):
            self.status = "completed"
        elif "failed" in statuses:
            self.status = "failed"
        elif "blocked" in statuses and "in_progress" not in statuses:
            self.status = "blocked"
        elif "in_progress" in statuses:
            self.status = "in_progress"
        else:
            self.status = "pending"


class Evidence(BaseModel):
    """可追溯到工具、文件或测试的工程证据。"""

    id: str = Field(default_factory=lambda: f"ev-{uuid.uuid4().hex[:8]}")
    source: str = Field(..., min_length=1)
    claim: str = Field(..., min_length=1)
    excerpt: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: str = Field(default_factory=utc_now)


class VerificationGate(BaseModel):
    """一个需求或检查项的预期与实际结果。"""

    id: str = Field(default_factory=lambda: f"gate-{uuid.uuid4().hex[:8]}")
    requirement: str = Field(..., min_length=1)
    command_or_check: str = ""
    expected: str = ""
    actual: str = ""
    passed: bool | None = None


class RunJournal(BaseModel):
    """单轮工程运行的可持久化记录。"""

    version: int = 1
    run_id: str
    session_id: str
    objective: str = Field(..., min_length=1)
    status: RunStatus = "running"
    started_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    completed_at: str | None = None
    intent: TaskIntent = Field(default_factory=TaskIntent)
    plan: WorkPlan | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    verification: list[VerificationGate] = Field(default_factory=list)
    residual_risks: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)

    def finish(
        self,
        status: Literal["completed", "failed", "blocked"],
        *,
        files_changed: list[str] | None = None,
        metrics: dict[str, Any] | None = None,
        residual_risks: list[str] | None = None,
    ) -> None:
        now = utc_now()
        self.status = status
        self.updated_at = now
        self.completed_at = now
        if files_changed:
            self.files_changed = list(dict.fromkeys([*self.files_changed, *files_changed]))
        if metrics:
            self.metrics.update(metrics)
        if residual_risks:
            self.residual_risks = list(
                dict.fromkeys([*self.residual_risks, *residual_risks])
            )

    def event_payload(self) -> dict[str, Any]:
        """返回适合 CLI/Web 事件展示的精简摘要。"""
        return {
            "run_id": self.run_id,
            "status": self.status,
            "objective": self.objective,
            "intent": self.intent.model_dump(),
            "plan": self.plan.model_dump() if self.plan else None,
            "evidence_count": len(self.evidence),
            "verification_count": len(self.verification),
            "files_changed": self.files_changed,
            "residual_risks": self.residual_risks,
            "metrics": self.metrics,
        }

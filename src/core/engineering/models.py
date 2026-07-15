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
EvidenceKind = Literal[
    "structure",
    "git",
    "file",
    "search",
    "test",
    "change",
    "external",
    "runtime",
]
HypothesisStatus = Literal["untested", "supported", "refuted", "inconclusive"]
ReconStatus = Literal["not_started", "in_progress", "partial", "completed"]
VerificationCheck = Literal[
    "targeted",
    "adjacent",
    "integration",
    "full",
    "smoke",
    "external_mock",
    "external_live",
]
RequirementStatus = Literal["unverified", "satisfied", "failed", "waived"]
AuditStatus = Literal["not_required", "passed", "blocked", "failed"]
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
    kind: EvidenceKind = "runtime"
    tool_name: str = ""
    path: str = ""
    command: str = ""
    success: bool = True
    cached: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


class Hypothesis(BaseModel):
    """可由直接证据支持或反证的工程假设。"""

    id: str = Field(default_factory=lambda: f"hyp-{uuid.uuid4().hex[:8]}")
    statement: str = Field(..., min_length=1)
    status: HypothesisStatus = "untested"
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    note: str = ""
    updated_at: str = Field(default_factory=utc_now)


class ProjectReconnaissance(BaseModel):
    """陌生项目侦察覆盖状态。"""

    root: str = ""
    status: ReconStatus = "not_started"
    observed_categories: list[str] = Field(default_factory=list)
    files_sampled: list[str] = Field(default_factory=list)
    tool_calls: int = 0
    skipped_areas: list[str] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now)

    def observe(self, category: str, *, path: str = "") -> None:
        if category and category != "file" and category not in self.observed_categories:
            self.observed_categories.append(category)
        if path and category == "file" and path not in self.files_sampled:
            self.files_sampled.append(path)
        self.updated_at = utc_now()
        self._refresh_status()

    def mark_skipped(self, area: str) -> None:
        if area and area not in self.skipped_areas:
            self.skipped_areas.append(area)
        self.updated_at = utc_now()
        self._refresh_status()

    def mark_tool_call(self) -> None:
        self.tool_calls += 1
        self.updated_at = utc_now()
        if self.status == "not_started":
            self.status = "in_progress"

    def finalize(self) -> None:
        self._refresh_status(final=True)

    def missing_categories(self) -> list[str]:
        expected = ("structure", "git", "docs", "dependencies", "entrypoints", "tests")
        return [item for item in expected if item not in self.observed_categories]

    def _refresh_status(self, *, final: bool = False) -> None:
        observed = set(self.observed_categories)
        expected = {"structure", "git", "docs", "dependencies", "entrypoints", "tests"}
        complete = expected.issubset(observed)
        if complete:
            self.status = "completed"
        elif observed or self.tool_calls:
            self.status = "partial" if final else "in_progress"
        elif final and self.root:
            self.status = "partial"


class VerificationGate(BaseModel):
    """一个需求或检查项的预期与实际结果。"""

    id: str = Field(default_factory=lambda: f"gate-{uuid.uuid4().hex[:8]}")
    requirement: str = Field(..., min_length=1)
    command_or_check: str = ""
    expected: str = ""
    actual: str = ""
    passed: bool | None = None
    check_type: VerificationCheck = "targeted"
    evidence_ids: list[str] = Field(default_factory=list)
    required: bool = True
    created_at: str = Field(default_factory=utc_now)


class RequirementCheck(BaseModel):
    """用户要求、实现证据和验证证据之间的可审计映射。"""

    id: str = Field(default_factory=lambda: f"req-{uuid.uuid4().hex[:8]}")
    requirement: str = Field(..., min_length=1)
    implementation_evidence_ids: list[str] = Field(default_factory=list)
    verification_gate_ids: list[str] = Field(default_factory=list)
    status: RequirementStatus = "unverified"
    note: str = ""


class CompletionAudit(BaseModel):
    """完成前的确定性审计结果。"""

    status: AuditStatus = "not_required"
    requested_status: RunStatus = "running"
    can_complete: bool = True
    required_checks: list[VerificationCheck] = Field(default_factory=list)
    satisfied_checks: list[VerificationCheck] = Field(default_factory=list)
    missing_checks: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    summary: str = ""
    audited_at: str = Field(default_factory=utc_now)


class RunJournal(BaseModel):
    """单轮工程运行的可持久化记录。"""

    version: int = 2
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
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    reconnaissance: ProjectReconnaissance = Field(default_factory=ProjectReconnaissance)
    decisions: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    verification: list[VerificationGate] = Field(default_factory=list)
    requirements: list[RequirementCheck] = Field(default_factory=list)
    audit: CompletionAudit | None = None
    residual_risks: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)

    def add_evidence(self, evidence: Evidence) -> tuple[Evidence, bool]:
        """按稳定指纹去重，返回证据和是否新增。"""
        fingerprint = (
            evidence.kind,
            evidence.source,
            evidence.claim,
            evidence.path,
            evidence.command,
            evidence.excerpt,
            evidence.success,
        )
        for existing in self.evidence:
            existing_fingerprint = (
                existing.kind,
                existing.source,
                existing.claim,
                existing.path,
                existing.command,
                existing.excerpt,
                existing.success,
            )
            if existing_fingerprint == fingerprint:
                return existing, False
        self.evidence.append(evidence)
        self.updated_at = utc_now()
        return evidence, True

    def add_hypothesis(self, statement: str) -> Hypothesis:
        normalized = statement.strip()
        existing = next(
            (item for item in self.hypotheses if item.statement == normalized),
            None,
        )
        if existing is not None:
            return existing
        hypothesis = Hypothesis(statement=normalized)
        self.hypotheses.append(hypothesis)
        self.updated_at = utc_now()
        return hypothesis

    def add_verification(self, gate: VerificationGate) -> tuple[VerificationGate, bool]:
        """按检查类型、命令和实际结果去重验证门。"""
        fingerprint = (
            gate.check_type,
            gate.command_or_check,
            gate.actual,
            gate.passed,
            tuple(gate.evidence_ids),
        )
        for existing in self.verification:
            existing_fingerprint = (
                existing.check_type,
                existing.command_or_check,
                existing.actual,
                existing.passed,
                tuple(existing.evidence_ids),
            )
            if existing_fingerprint == fingerprint:
                return existing, False
        self.verification.append(gate)
        self.updated_at = utc_now()
        return gate, True

    def evaluate_hypothesis(
        self,
        hypothesis_id: str,
        status: HypothesisStatus,
        *,
        evidence_ids: list[str] | None = None,
        note: str = "",
    ) -> Hypothesis:
        hypothesis = next(
            (item for item in self.hypotheses if item.id == hypothesis_id),
            None,
        )
        if hypothesis is None:
            raise KeyError(f"工程假设不存在：{hypothesis_id}")
        ids = list(dict.fromkeys(evidence_ids or []))
        known_ids = {item.id for item in self.evidence}
        unknown = [item for item in ids if item not in known_ids]
        if unknown:
            raise ValueError(f"假设引用了未知证据：{', '.join(unknown)}")
        if status in {"supported", "refuted"} and not ids:
            raise ValueError(f"假设状态 {status} 必须引用直接证据")
        if status == "supported":
            hypothesis.supporting_evidence_ids = ids
        elif status == "refuted":
            hypothesis.contradicting_evidence_ids = ids
        hypothesis.status = status
        hypothesis.note = note
        hypothesis.updated_at = utc_now()
        self.updated_at = hypothesis.updated_at
        return hypothesis

    def finish(
        self,
        status: Literal["completed", "failed", "blocked"],
        *,
        files_changed: list[str] | None = None,
        metrics: dict[str, Any] | None = None,
        residual_risks: list[str] | None = None,
    ) -> None:
        self.reconnaissance.finalize()
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
            "evidence_preview": [
                {
                    "id": item.id,
                    "kind": item.kind,
                    "claim": item.claim,
                    "source": item.source,
                    "path": item.path,
                    "success": item.success,
                }
                for item in self.evidence[-3:]
            ],
            "hypothesis_counts": {
                status: sum(item.status == status for item in self.hypotheses)
                for status in ("untested", "supported", "refuted", "inconclusive")
            },
            "reconnaissance": self.reconnaissance.model_dump(),
            "verification_count": len(self.verification),
            "verification_summary": {
                "passed": sum(item.passed is True for item in self.verification),
                "failed": sum(item.passed is False for item in self.verification),
                "pending": sum(item.passed is None for item in self.verification),
            },
            "requirement_counts": {
                status: sum(item.status == status for item in self.requirements)
                for status in ("unverified", "satisfied", "failed", "waived")
            },
            "audit": self.audit.model_dump() if self.audit else None,
            "files_changed": self.files_changed,
            "residual_risks": self.residual_risks,
            "metrics": self.metrics,
        }

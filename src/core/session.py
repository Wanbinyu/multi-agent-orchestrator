"""会话存储"""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from src.models.schemas import (
    ApprovalMode,
    CollaborationMode,
    ChatMessage,
    ExecutionDepthPreference,
    MessageContentBlock,
    ModelRoutingMode,
)


PlanModeState = Literal["inactive", "pending", "active", "awaiting_approval"]
PlanArtifactStatus = Literal["draft", "awaiting_approval", "approved", "cancelled"]
RecoveryAction = Literal["continue", "abandon"]


class SessionPlanArtifact(BaseModel):
    objective: str = ""
    content: str = ""
    feedback: str = ""
    status: PlanArtifactStatus = "draft"
    revision: int = 0
    council: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SessionRecoveryDecision(BaseModel):
    """One explicit owner decision for an interrupted engineering run."""

    run_id: str
    action: RecoveryAction
    status_before: str
    unfinished_step_ids: list[str] = Field(default_factory=list)
    unfinished_step_titles: list[str] = Field(default_factory=list)
    completed_step_ids: list[str] = Field(default_factory=list)
    completed_step_titles: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    decided_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    consumed_by_run_id: str | None = None


class Session(BaseModel):
    """一个多轮对话会话"""

    id: str
    title: str = ""
    created_at: str
    updated_at: str
    messages: list[ChatMessage] = Field(default_factory=list)
    output_dir: str
    config_dir: str = "config"
    approval_mode: ApprovalMode = "auto"
    execution_depth: ExecutionDepthPreference = "auto"
    model_routing_mode: ModelRoutingMode = "auto"
    model_routing_allowed_models: list[str] = Field(default_factory=list)
    collaboration_mode: CollaborationMode = "auto"
    adversarial_testing: bool = False
    plan_mode: PlanModeState = "inactive"
    plan_artifact: SessionPlanArtifact | None = None
    compaction_events: list[dict[str, Any]] = Field(default_factory=list)
    usage_observations: list[dict[str, Any]] = Field(default_factory=list)
    recovery_decisions: list[SessionRecoveryDecision] = Field(default_factory=list)

    def add_message(
        self,
        role: str,
        content: str,
        content_blocks: list[MessageContentBlock] | None = None,
        provider_payload: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        """添加一条消息并更新时间戳"""
        msg = ChatMessage(
            role=role,
            content=content,
            content_blocks=content_blocks or [],
            provider_payload=provider_payload or [],
        )
        self.messages.append(msg)
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return msg

    def record_compaction_event(self, event: dict[str, Any]) -> None:
        """记录一次上下文压缩事件，最多保留最近 20 条。"""
        self.compaction_events.append(event)
        del self.compaction_events[:-20]
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def record_usage_observation(self, observation: dict[str, Any]) -> None:
        """记录一次本地估算与 Provider 实际 usage 的对比，最多保留最近 20 条。"""
        self.usage_observations.append(observation)
        del self.usage_observations[:-20]
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def record_recovery_decision(self, decision: SessionRecoveryDecision) -> None:
        """Persist a bounded recovery history without adding chat messages."""
        self.recovery_decisions = [
            item for item in self.recovery_decisions if item.run_id != decision.run_id
        ]
        self.recovery_decisions.append(decision)
        del self.recovery_decisions[:-20]
        self.updated_at = decision.decided_at

    def enter_plan_mode(self, objective: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.plan_artifact = SessionPlanArtifact(
            objective=objective.strip(),
            status="draft",
            created_at=now,
            updated_at=now,
        )
        self.plan_mode = "pending"
        self.updated_at = now

    def activate_plan_mode(self) -> None:
        if self.plan_mode not in ("pending", "active"):
            raise ValueError(f"当前 Plan 状态不能进入规划：{self.plan_mode}")
        self.plan_mode = "active"
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def save_plan_artifact(self, content: str, *, council: dict[str, Any] | None = None) -> None:
        if self.plan_mode not in ("pending", "active"):
            raise ValueError(f"当前 Plan 状态不能保存方案：{self.plan_mode}")
        if self.plan_artifact is None:
            self.plan_artifact = SessionPlanArtifact()
        self.plan_artifact.content = content.strip()
        self.plan_artifact.status = "awaiting_approval"
        self.plan_artifact.revision += 1
        if council is not None:
            self.plan_artifact.council = council
        self.plan_artifact.updated_at = datetime.now(timezone.utc).isoformat()
        self.plan_mode = "awaiting_approval"
        self.updated_at = self.plan_artifact.updated_at

    def request_plan_revision(self, feedback: str) -> None:
        if self.plan_mode != "awaiting_approval" or self.plan_artifact is None:
            raise ValueError("当前没有等待审阅的方案")
        self.plan_artifact.feedback = feedback.strip()
        self.plan_artifact.status = "draft"
        self.plan_artifact.updated_at = datetime.now(timezone.utc).isoformat()
        self.plan_mode = "active"
        self.updated_at = self.plan_artifact.updated_at

    def approve_plan(self) -> str:
        if self.plan_mode != "awaiting_approval" or self.plan_artifact is None:
            raise ValueError("当前没有等待批准的方案")
        self.plan_artifact.status = "approved"
        self.plan_artifact.updated_at = datetime.now(timezone.utc).isoformat()
        self.plan_mode = "inactive"
        self.updated_at = self.plan_artifact.updated_at
        return self.plan_artifact.content

    def cancel_plan_mode(self) -> None:
        if self.plan_artifact is not None:
            self.plan_artifact.status = "cancelled"
            self.plan_artifact.updated_at = datetime.now(timezone.utc).isoformat()
        self.plan_mode = "inactive"
        self.updated_at = datetime.now(timezone.utc).isoformat()


class SessionStore:
    """基于 YAML 文件的会话持久化"""

    def __init__(self, base_dir: str = "sessions"):
        self.base_dir = Path(base_dir)

    def create(self, title: str = "") -> Session:
        """创建新会话并持久化"""
        session_id = (
            datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
            + "-"
            + uuid.uuid4().hex[:6]
        )
        output_dir = str(self.base_dir / session_id / "output")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()
        session = Session(
            id=session_id,
            title=title or session_id,
            created_at=now,
            updated_at=now,
            output_dir=output_dir,
            approval_mode="approve",
        )
        self.save(session)
        return session

    def _path(self, session_id: str) -> Path:
        return self.base_dir / f"{session_id}.yaml"

    def save(self, session: Session) -> None:
        """保存会话到 YAML"""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        with open(self._path(session.id), "w", encoding="utf-8") as f:
            yaml.dump(
                session.model_dump(),
                f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )

    def load(self, session_id: str) -> Session:
        """从 YAML 加载会话"""
        path = self._path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"会话不存在: {session_id}")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return Session(**data)

    def list(self) -> list[Session]:
        """列出所有会话，按更新时间倒序（同秒时用 id 保证稳定）"""
        if not self.base_dir.exists():
            return []
        sessions: list[Session] = []
        for path in self.base_dir.glob("*.yaml"):
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            sessions.append(Session(**data))
        sessions.sort(key=lambda s: (s.updated_at, s.id), reverse=True)
        return sessions

    def delete(self, session_id: str) -> None:
        """删除会话及其输出目录"""
        self._path(session_id).unlink(missing_ok=True)
        shutil.rmtree(self.base_dir / session_id, ignore_errors=True)

    def exists(self, session_id: str) -> bool:
        return self._path(session_id).exists()

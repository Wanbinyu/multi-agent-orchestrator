"""Deterministic rules for when a turn may enter multi-model collaboration."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from src.core.config_paths import resolve_workers_config_path
from src.core.engineering.models import ExecutionDepthDecision, TaskIntent
from src.models.schemas import ApprovalMode, CollaborationMode

CollaborationTriggerReason = Literal[
    "session_readonly",
    "plan_readonly",
    "policy_disallowed",
    "workers_disabled",
    "user_single",
    "user_explicit",
    "config_force",
    "deep_change_or_build",
    "default_single",
]

_COLLABORATIVE_KINDS = frozenset({"change", "build"})

# Project-scale only. Classifier `build` also covers "写文件" / "帮我创建好".
_PROJECT_SCALE_PATTERNS = (
    r"开发.{0,20}(功能|系统|应用|网站|页面|接口|项目|前后端|登录)",
    r"实现.{0,24}(功能|系统|应用|网站|页面|接口|项目|完整|health)",
    r"做(一个|一套).{0,20}(项目|系统|应用|网站|前后端|全栈|完整)",
    r"前后端(交互|项目|应用)",
    r"全栈项目",
    r"综合(起来|做一个)",
    r"多步骤实现",
    r"多页面",
    r"立项",
    r"完整(登录|网站|系统|应用|项目)",
)


class CollaborationDecision(BaseModel):
    """Why a turn did or did not start Orchestrator/Worker collaboration."""

    triggered: bool
    reason: CollaborationTriggerReason
    detail: str = ""
    session_mode: CollaborationMode = "auto"
    task_kind: str = "unclassified"
    execution_depth: str = ""
    config_force: bool = False

    def journal_line(self) -> str:
        verb = "进入" if self.triggered else "不进入"
        extra = f"：{self.detail}" if self.detail else ""
        return f"[collaboration] {verb}多模型协作（{self.reason}）{extra}"


def load_collaboration_force(config_dir: str | Path = "config") -> bool:
    """Read optional workers.yaml collaboration.force. Missing/invalid is false."""
    path = resolve_workers_config_path(Path(config_dir) / "workers.yaml")
    if not path.exists():
        return False
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return False
    section = data.get("collaboration")
    if not isinstance(section, dict):
        return False
    return bool(section.get("force"))


def is_project_scale_request(user_input: str) -> bool:
    """True for multi-component builds, not single-file create/edit."""
    text = user_input.strip()
    if not text:
        return False
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in _PROJECT_SCALE_PATTERNS)


def decide_collaboration(
    *,
    session_mode: CollaborationMode,
    intent: TaskIntent,
    execution_depth: ExecutionDepthDecision | None,
    approval_mode: ApprovalMode = "auto",
    plan_read_only: bool = False,
    config_force: bool = False,
    user_input: str = "",
) -> CollaborationDecision:
    """Decide collaboration without an extra model call.

    Auto path: project-scale ``build``, or ``change`` that is actually
    ``deep`` because the user or safety floor asked for it. ``/collab multi``
    or ``collaboration.force`` can opt in when the task policy already allows
    collaboration. Readonly, Plan, and ``collaboration_allowed=false`` always win.
    """
    actual_depth = execution_depth.actual if execution_depth is not None else ""
    worker_policy = (
        execution_depth.budget.worker_policy if execution_depth is not None else "disabled"
    )
    base = {
        "session_mode": session_mode,
        "task_kind": intent.kind,
        "execution_depth": actual_depth,
        "config_force": config_force,
    }

    if approval_mode == "readonly":
        return CollaborationDecision(
            triggered=False,
            reason="session_readonly",
            detail="只读会话不派发 Worker",
            **base,
        )
    if plan_read_only:
        return CollaborationDecision(
            triggered=False,
            reason="plan_readonly",
            detail="Plan 未批准前整条链只读",
            **base,
        )
    if not intent.policy.collaboration_allowed:
        return CollaborationDecision(
            triggered=False,
            reason="policy_disallowed",
            detail=f"{intent.kind} 任务不允许协作，避免扩大权限",
            **base,
        )
    if worker_policy == "disabled":
        return CollaborationDecision(
            triggered=False,
            reason="workers_disabled",
            detail="当前执行深度禁用 Worker",
            **base,
        )
    if session_mode == "single":
        return CollaborationDecision(
            triggered=False,
            reason="user_single",
            detail="会话强制单 Agent",
            **base,
        )
    if session_mode == "multi":
        return CollaborationDecision(
            triggered=True,
            reason="user_explicit",
            detail="用户显式 /collab multi",
            **base,
        )
    if config_force:
        return CollaborationDecision(
            triggered=True,
            reason="config_force",
            detail="workers.yaml collaboration.force",
            **base,
        )
    if actual_depth == "deep" and intent.kind in _COLLABORATIVE_KINDS:
        requested = execution_depth.requested if execution_depth is not None else "auto"
        source = execution_depth.source if execution_depth is not None else "automatic"
        user_or_safety_deep = requested == "deep" or source in {
            "user",
            "safety_override",
        }
        if intent.kind == "change" and user_or_safety_deep:
            return CollaborationDecision(
                triggered=True,
                reason="deep_change_or_build",
                detail=f"{intent.kind}/{actual_depth} 由用户或安全下限加深",
                **base,
            )
        if intent.kind == "build" and is_project_scale_request(user_input):
            return CollaborationDecision(
                triggered=True,
                reason="deep_change_or_build",
                detail="项目级构建允许有边界协作",
                **base,
            )
    return CollaborationDecision(
        triggered=False,
        reason="default_single",
        detail="问答/小改/单文件创建默认单 Agent",
        **base,
    )

"""Bounded verify-then-fix protocol for the single-Agent edit loop."""
from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.core.engineering.evidence import is_test_command

FixStatus = Literal[
    "idle",
    "needs_verification",
    "fixing",
    "passed",
    "blocked",
    "cancelled",
]

DEFAULT_MAX_FIX_ROUNDS = 3
_FAILURE_SUMMARY_LIMIT = 800
_MUTATION_TOOLS = frozenset({"write_file", "edit_file"})
_VERIFY_TOOLS = frozenset({"run_command", "frontend_smoke"})


def default_max_fix_rounds() -> int:
    raw = os.environ.get("MAO_MAX_FIX_ROUNDS", str(DEFAULT_MAX_FIX_ROUNDS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_FIX_ROUNDS
    return max(1, min(value, 8))


class BoundedFixState(BaseModel):
    """Deterministic repair budget after a real verification failure."""

    status: FixStatus = "idle"
    fix_round: int = Field(default=0, ge=0)
    max_rounds: int = Field(default=DEFAULT_MAX_FIX_ROUNDS, ge=1, le=8)
    last_failure_summary: str = ""
    last_command: str = ""
    last_mutated_paths: list[str] = Field(default_factory=list)
    reason: str = ""

    def prompt_constraint(self) -> str:
        if self.status == "needs_verification":
            paths = "、".join(self.last_mutated_paths[-6:]) or "已修改文件"
            return (
                "【有界修复协议】已写入 "
                f"{paths}。必须先 discover_project_commands，再用 run_command "
                "运行针对性测试；不得只声称已修复。"
            )
        if self.status == "fixing":
            return (
                f"【有界修复协议】第 {self.fix_round}/{self.max_rounds} 轮。"
                f"上一次验证失败：{self.last_failure_summary or '见工具输出'}。"
                "只做最小补丁修复该失败，禁止改无关文件；修完立即再跑同一验证。"
            )
        if self.status == "blocked":
            return (
                f"【有界修复协议】已达 {self.max_rounds} 轮上限。"
                "停止继续修改。说明失败原因、已改文件和剩余风险；"
                "不要再调用写入或命令工具，不得宣称已完成。"
            )
        if self.status == "cancelled":
            return "【有界修复协议】用户已取消本轮修复。不要再调用写入或命令工具。"
        return ""


def _failure_summary(result: Any) -> str:
    output = str(getattr(result, "output", "") or "").strip()
    error = str(getattr(result, "error", "") or "").strip()
    text = "\n".join(part for part in (output, error) if part)
    if len(text) <= _FAILURE_SUMMARY_LIMIT:
        return text
    return text[:_FAILURE_SUMMARY_LIMIT] + "...（失败摘要已截断）"


def _is_verification_attempt(tool_name: str, params: dict[str, Any]) -> bool:
    if tool_name == "frontend_smoke":
        return True
    if tool_name != "run_command":
        return False
    return is_test_command(str(params.get("command", "")))


def _is_preflight_failure(result: Any) -> bool:
    metadata = getattr(result, "metadata", None) or {}
    if not isinstance(metadata, dict):
        return False
    return bool(metadata.get("error_code")) and metadata.get("exit_code") is None


def observe_bounded_fix(
    state: BoundedFixState,
    tool_name: str,
    params: dict[str, Any],
    result: Any,
    *,
    cancelled: bool = False,
    skipped: bool = False,
) -> BoundedFixState:
    """Advance the protocol from a real tool result. Never reads model prose."""
    next_state = state.model_copy(deep=True)
    if next_state.status in {"blocked", "cancelled"}:
        return next_state
    if cancelled:
        next_state.status = "cancelled"
        next_state.reason = "用户取消有界修复"
        return next_state
    if skipped:
        return next_state

    success = bool(getattr(result, "success", False))
    if tool_name in _MUTATION_TOOLS and success:
        path = str(params.get("path", "")).strip()
        if path and path not in next_state.last_mutated_paths:
            next_state.last_mutated_paths.append(path)
            del next_state.last_mutated_paths[:-12]
        if next_state.status != "fixing":
            next_state.status = "needs_verification"
            next_state.reason = "已写入，等待真实验证"
        return next_state

    if not _is_verification_attempt(tool_name, params):
        return next_state
    if _is_preflight_failure(result):
        return next_state

    command = (
        "frontend_smoke"
        if tool_name == "frontend_smoke"
        else str(params.get("command", "")).strip()
    )
    if success:
        if next_state.status in {"needs_verification", "fixing"}:
            next_state.status = "passed"
            next_state.reason = "真实验证通过"
            next_state.last_command = command
        return next_state

    if next_state.status == "idle" and not next_state.last_mutated_paths:
        return next_state

    next_state.last_command = command
    next_state.last_failure_summary = _failure_summary(result)
    if next_state.fix_round >= next_state.max_rounds:
        next_state.status = "blocked"
        next_state.reason = f"验证失败修复已达 {next_state.max_rounds} 轮上限"
        return next_state

    next_state.fix_round += 1
    if next_state.fix_round >= next_state.max_rounds:
        next_state.status = "blocked"
        next_state.reason = f"验证失败修复已达 {next_state.max_rounds} 轮上限"
    else:
        next_state.status = "fixing"
        next_state.reason = f"验证失败，进入第 {next_state.fix_round} 轮定向修复"
    return next_state

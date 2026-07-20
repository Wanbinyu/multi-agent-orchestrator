"""Deterministic fast/standard/deep execution-depth contract."""
from __future__ import annotations

from src.core.engineering.models import (
    ExecutionBudget,
    ExecutionDepthDecision,
    TaskIntent,
)
from src.models.schemas import ExecutionDepth, ExecutionDepthPreference


_DEPTH_RANK: dict[ExecutionDepth, int] = {
    "fast": 0,
    "standard": 1,
    "deep": 2,
}

_PROFILES: dict[ExecutionDepth, ExecutionBudget] = {
    "fast": ExecutionBudget(
        max_tool_iterations=3,
        context_budget_ratio=0.50,
        worker_policy="disabled",
        max_workers=0,
        worker_tool_iterations=0,
        reviewer_policy="disabled",
        mutation_verification_floor="targeted",
    ),
    "standard": ExecutionBudget(
        max_tool_iterations=6,
        context_budget_ratio=0.75,
        worker_policy="eligible",
        max_workers=2,
        worker_tool_iterations=3,
        reviewer_policy="required_after_collaboration",
        mutation_verification_floor="standard",
    ),
    "deep": ExecutionBudget(
        max_tool_iterations=8,
        context_budget_ratio=1.0,
        worker_policy="eligible",
        max_workers=4,
        worker_tool_iterations=5,
        reviewer_policy="required_after_collaboration",
        mutation_verification_floor="deep",
    ),
}


class ExecutionDepthResolver:
    """Resolve user preference without allowing it to weaken safety verification."""

    def resolve(
        self,
        intent: TaskIntent,
        requested: ExecutionDepthPreference = "auto",
        *,
        observed: bool = False,
    ) -> ExecutionDepthDecision:
        recommended = self._recommended(intent)
        minimum = self._safety_minimum(intent)

        if requested == "auto":
            actual = self._max_depth(recommended, minimum)
            source = "observed" if observed else "automatic"
            reason = self._automatic_reason(intent, actual, observed=observed)
        else:
            actual = self._max_depth(requested, minimum)
            if actual != requested:
                source = "safety_override"
                reason = (
                    f"用户选择 {requested}，但 {intent.kind}/{intent.risk_level}/"
                    f"{intent.policy.verification_depth} 的安全下限为 {minimum}；"
                    f"实际使用 {actual}，权限边界不变。"
                )
            else:
                source = "user"
                reason = (
                    f"采用用户显式选择 {requested}；自动建议为 {recommended}，"
                    "权限和确定性验证下限仍不可放宽。"
                )

        return ExecutionDepthDecision(
            requested=requested,
            recommended=recommended,
            actual=actual,
            source=source,
            reason=reason,
            budget=_PROFILES[actual].model_copy(deep=True),
        )

    @staticmethod
    def profile(depth: ExecutionDepth) -> ExecutionBudget:
        return _PROFILES[depth].model_copy(deep=True)

    @staticmethod
    def _recommended(intent: TaskIntent) -> ExecutionDepth:
        if intent.kind == "build" or intent.risk_level == "high":
            return "deep"
        if intent.kind in {"diagnose", "change", "review", "monitor", "unclassified"}:
            return "standard"
        return "fast"

    @staticmethod
    def _safety_minimum(intent: TaskIntent) -> ExecutionDepth:
        if intent.risk_level == "high" or intent.policy.verification_depth == "deep":
            return "deep"
        if (
            intent.risk_level == "external"
            or intent.policy.verification_depth == "continuous"
        ):
            return "standard"
        return "fast"

    @staticmethod
    def _max_depth(left: ExecutionDepth, right: ExecutionDepth) -> ExecutionDepth:
        return left if _DEPTH_RANK[left] >= _DEPTH_RANK[right] else right

    @staticmethod
    def _automatic_reason(
        intent: TaskIntent, actual: ExecutionDepth, *, observed: bool
    ) -> str:
        prefix = "真实写入触发重新评估" if observed else "按任务分类自动选择"
        return (
            f"{prefix} {actual}：{intent.kind}/{intent.risk_level}/"
            f"{intent.policy.verification_depth}；权限边界不变。"
        )

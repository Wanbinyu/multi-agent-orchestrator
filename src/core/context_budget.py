"""Deterministic context budgets shared by every model request path."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from src.core.token_counter import count_messages_tokens, count_tokens
from src.models.schemas import ChatMessage, ModelConfig


# 未知/未验证模型的本地默认安全预算。
# 2026 主流模型常见 128K–200K；本地默认抬到 200K，避免无谓拦截长对话。
# 这是 MAO 的本地保护值，不代表上游物理上限；上游更小时仍可能被 Provider 拒绝。
DEFAULT_SAFE_CONTEXT_TOKENS = 200_000
DEFAULT_OUTPUT_RESERVE_TOKENS = 4_096
DEFAULT_PROTOCOL_OVERHEAD_TOKENS = 512


class ContextBudgetExceeded(ValueError):
    """Raised before an upstream request that cannot fit its declared budget."""


@dataclass(frozen=True)
class ContextBudget:
    model_alias: str
    model_id: str
    context_window_tokens: int
    context_window_source: str
    context_window_verified_at: str
    dynamic_model_alias: bool
    safety_ratio: float
    safe_context_tokens: int
    output_reserve_tokens: int
    protocol_overhead_tokens: int
    tool_schema_tokens: int
    input_budget_tokens: int
    current_input_tokens: int
    remaining_input_tokens: int
    compaction_threshold: float
    compaction_trigger_tokens: int
    within_budget: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["warnings"] = list(self.warnings)
        return data


class ContextBudgetManager:
    """Resolve configured/legacy budgets and reject oversized requests locally."""

    def __init__(self, default_safe_context_tokens: int = DEFAULT_SAFE_CONTEXT_TOKENS):
        self.default_safe_context_tokens = default_safe_context_tokens

    def calculate(
        self,
        model_alias: str,
        config: ModelConfig,
        messages: Iterable[ChatMessage],
        *,
        requested_output_tokens: int = DEFAULT_OUTPUT_RESERVE_TOKENS,
        tools: Any = None,
        protocol_overhead_tokens: int = DEFAULT_PROTOCOL_OVERHEAD_TOKENS,
    ) -> ContextBudget:
        warnings: list[str] = []
        requested_output = max(1, int(requested_output_tokens or DEFAULT_OUTPUT_RESERVE_TOKENS))
        # 过小的「硬窗口」几乎都是误填，按未知窗口处理，避免输入预算被算成 0
        declared_window = int(config.context_window_tokens or 0)
        if 0 < declared_window < 16_000:
            warnings.append(
                f"配置的上游窗口 {declared_window} 过小，已忽略并使用 "
                f"{self.default_safe_context_tokens // 1000}K 默认安全预算"
            )
            declared_window = 0

        if declared_window > 0:
            safe_context = int(declared_window * (1 - config.context_safety_ratio))
            source = config.context_window_source or "user_config"
            if source in {"unknown", "unverified", "user_config"}:
                warnings.append("上游窗口未由 MAO 验证")
        elif config.max_context_tokens > 0:
            safe_context = config.max_context_tokens
            source = "legacy_max_context_tokens"
            warnings.append("使用旧版安全预算；未声明上游硬窗口")
        else:
            safe_context = self.default_safe_context_tokens
            source = "unverified_default"
            warnings.append(
                f"未知模型窗口；使用 {self.default_safe_context_tokens // 1000}K "
                f"默认安全预算（本地值，非上游保证）"
            )

        if config.dynamic_model_alias:
            warnings.append("动态模型别名；实际模型版本和硬窗口可能变化")

        # 配置的 max_output 过小会把默认 4096 输出预留卡死；抬升到至少能容纳本次请求
        effective_max_output = int(config.max_output_tokens or 0)
        if effective_max_output > 0 and effective_max_output < requested_output:
            warnings.append(
                f"配置最大输出 {effective_max_output} 低于本次请求 {requested_output}，"
                f"已按请求输出预留（避免误填阻断对话）"
            )
            effective_max_output = requested_output

        # 若硬窗口扣掉输出后几乎没有输入空间，回退默认安全预算
        min_input_room = 4_096
        trial_budget = safe_context - requested_output - protocol_overhead_tokens
        if declared_window > 0 and trial_budget < min_input_room:
            warnings.append(
                f"配置窗口在扣除输出预留后输入空间不足，已回退 "
                f"{self.default_safe_context_tokens // 1000}K 默认安全预算"
            )
            safe_context = self.default_safe_context_tokens
            source = "unverified_default_fallback"
            declared_window = 0

        tool_tokens = count_tokens(
            json.dumps(tools, ensure_ascii=False, sort_keys=True, default=str)
        ) if tools else 0
        current_tokens = count_messages_tokens(messages)
        input_budget = max(
            0,
            safe_context - requested_output - protocol_overhead_tokens - tool_tokens,
        )
        remaining = input_budget - current_tokens
        trigger = int(input_budget * config.compaction_threshold)
        output_allowed = effective_max_output <= 0 or requested_output <= effective_max_output

        return ContextBudget(
            model_alias=model_alias,
            model_id=config.model_id,
            context_window_tokens=declared_window,
            context_window_source=source,
            context_window_verified_at=config.context_window_verified_at,
            dynamic_model_alias=config.dynamic_model_alias,
            safety_ratio=config.context_safety_ratio,
            safe_context_tokens=safe_context,
            output_reserve_tokens=requested_output,
            protocol_overhead_tokens=protocol_overhead_tokens,
            tool_schema_tokens=tool_tokens,
            input_budget_tokens=input_budget,
            current_input_tokens=current_tokens,
            remaining_input_tokens=remaining,
            compaction_threshold=config.compaction_threshold,
            compaction_trigger_tokens=trigger,
            within_budget=remaining >= 0 and output_allowed,
            warnings=tuple(warnings),
        )

    def ensure_fits(self, budget: ContextBudget) -> None:
        if budget.within_budget:
            return
        details = "; ".join(budget.warnings) or "输入超过安全预算"
        raise ContextBudgetExceeded(
            "上下文预算不足，已在发送前阻止请求："
            f"输入估算 {budget.current_input_tokens}，"
            f"安全输入预算 {budget.input_budget_tokens}，"
            f"剩余 {budget.remaining_input_tokens} tokens；{details}"
        )

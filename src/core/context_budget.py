"""Deterministic context budgets shared by every model request path."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from src.core.token_counter import count_messages_tokens, count_tokens
from src.models.schemas import ChatMessage, ModelConfig


DEFAULT_SAFE_CONTEXT_TOKENS = 32_000
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

        if config.context_window_tokens > 0:
            safe_context = int(config.context_window_tokens * (1 - config.context_safety_ratio))
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
            warnings.append("未知模型窗口；使用 32K 保守安全预算")

        if config.dynamic_model_alias:
            warnings.append("动态模型别名；实际模型版本和硬窗口可能变化")

        if config.max_output_tokens > 0 and requested_output > config.max_output_tokens:
            warnings.append(
                f"请求输出 {requested_output} 超过配置最大输出 {config.max_output_tokens}"
            )

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
        output_allowed = config.max_output_tokens <= 0 or requested_output <= config.max_output_tokens

        return ContextBudget(
            model_alias=model_alias,
            model_id=config.model_id,
            context_window_tokens=config.context_window_tokens,
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

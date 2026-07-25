"""Unified context budget calculations and release-gate behavior."""
from __future__ import annotations

import pytest

from src.core.context_budget import ContextBudgetExceeded, ContextBudgetManager
from src.models.schemas import ChatMessage, ModelConfig


def test_unknown_model_uses_conservative_explainable_budget():
    manager = ContextBudgetManager()
    config = ModelConfig(provider="p", model_id="dynamic", dynamic_model_alias=True)
    report = manager.calculate(
        "alias",
        config,
        [ChatMessage(role="user", content="hello")],
        requested_output_tokens=4096,
    )

    assert report.context_window_tokens == 0
    assert report.safe_context_tokens == 200_000
    assert report.input_budget_tokens == 200_000 - 4096 - 512
    assert report.context_window_source == "unverified_default"
    assert any("动态模型别名" in warning for warning in report.warnings)


def test_verified_window_applies_safety_output_protocol_and_tools():
    manager = ContextBudgetManager()
    config = ModelConfig(
        provider="p",
        model_id="fixed",
        context_window_tokens=100_000,
        max_output_tokens=8_000,
        context_safety_ratio=0.1,
        compaction_threshold=0.8,
        context_window_source="provider_docs",
        context_window_verified_at="2026-07-15",
    )
    report = manager.calculate(
        "fixed",
        config,
        [ChatMessage(role="system", content="rules")],
        requested_output_tokens=8_000,
        tools=[{"name": "read_file", "description": "read"}],
    )

    assert report.safe_context_tokens == 90_000
    assert report.tool_schema_tokens > 0
    assert report.input_budget_tokens < 82_000
    assert report.compaction_trigger_tokens == int(report.input_budget_tokens * 0.8)
    assert report.within_budget is True


def test_output_above_configured_max_is_clamped_not_blocking():
    """误填过小的 max_output 不应阻断对话；抬升预留并告警。"""
    manager = ContextBudgetManager()
    config = ModelConfig(provider="p", model_id="m", max_output_tokens=1024)
    report = manager.calculate("m", config, [], requested_output_tokens=2048)

    assert report.within_budget is True
    assert report.output_reserve_tokens == 2048
    assert any("低于本次请求" in w for w in report.warnings)
    manager.ensure_fits(report)  # 不应再因 max_output 误填而抛错


def test_tiny_declared_window_falls_back_to_default_200k():
    manager = ContextBudgetManager()
    config = ModelConfig(
        provider="p",
        model_id="m",
        context_window_tokens=3072,
        max_output_tokens=3841,
    )
    report = manager.calculate(
        "m",
        config,
        [ChatMessage(role="user", content="hello")],
        requested_output_tokens=4096,
    )
    assert report.within_budget is True
    assert report.safe_context_tokens == 200_000
    assert report.input_budget_tokens > 0
    assert any("过小" in w for w in report.warnings)


def test_legacy_max_context_is_safe_budget_not_claimed_hard_window():
    report = ContextBudgetManager().calculate(
        "legacy",
        ModelConfig(provider="p", model_id="m", max_context_tokens=64_000),
        [],
    )
    assert report.context_window_tokens == 0
    assert report.safe_context_tokens == 64_000
    assert report.context_window_source == "legacy_max_context_tokens"

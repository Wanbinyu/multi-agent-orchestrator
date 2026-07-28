"""Agent turn wall-clock timeout integration (mocked gateway)."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from src.core.agent import Agent
from src.core.engineering import RunJournalStore, TaskIntent
from src.core.session import SessionStore
from src.core.turn_timeout import TurnDeadline, TurnTimeoutError
from src.models.schemas import ChatResponse, ModelConfig


def _agent(tmp_path):
    gateway = MagicMock()
    gateway.main_model = "m"
    gateway.models = {
        "m": ModelConfig(
            provider="p",
            model_id="m",
            context_window_tokens=200_000,
            max_output_tokens=4096,
        )
    }
    gateway.providers = {"p": MagicMock(name="p")}
    gateway.billing = MagicMock()
    gateway.billing.summary.return_value = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": 0.0,
    }
    gateway.last_attempt_trace = []
    gateway.last_failover = None
    gateway.chat.return_value = ChatResponse(
        content="hello",
        model="m",
        provider="p",
        input_tokens=1,
        output_tokens=1,
        cost_usd=0.0,
    )
    gateway.resolve_model.return_value = "m"
    gateway.prepare_messages = lambda _model, messages: messages

    store = SessionStore(base_dir=str(tmp_path / "sessions"))
    session = store.create(title="timeout-test")
    session.approval_mode = "readonly"
    store.save(session)
    return Agent(gateway, session, approval_mode="readonly", max_tool_iterations=1)


def test_run_turn_impl_raises_when_deadline_already_expired(tmp_path):
    agent = _agent(tmp_path)
    journal = RunJournalStore.from_output_dir(agent.session.output_dir).create(
        agent.session.id,
        "ping",
        "readonly",
        intent=TaskIntent(),
    )
    deadline = TurnDeadline(
        limit_seconds=0.01,
        started_at=time.monotonic() - 1.0,
    )
    with pytest.raises(TurnTimeoutError):
        agent._run_turn_impl("ping", journal, deadline=deadline)

"""B4.2 压缩事件与上下文透明度测试"""
from __future__ import annotations

from unittest.mock import MagicMock

from src.core.agent import Agent
from src.core.session import Session
from src.models.schemas import ChatMessage, StreamChunk


def _make_session() -> Session:
    return Session(
        id="test-session",
        title="test",
        created_at="2026-07-17T00:00:00+00:00",
        updated_at="2026-07-17T00:00:00+00:00",
        output_dir="output",
    )


def _make_agent(session: Session) -> Agent:
    gateway = MagicMock()
    gateway.main_model = "test-model"
    gateway.get_model_config.side_effect = Exception("unknown model")
    response = MagicMock()
    response.content = "压缩后的摘要"
    gateway.chat_with_main_model.return_value = response
    return Agent(gateway, session)


def test_session_compaction_events_are_bounded():
    session = _make_session()
    for i in range(25):
        session.record_compaction_event({"at": f"t{i}", "dropped_messages": i})
    assert len(session.compaction_events) == 20
    assert session.compaction_events[0]["dropped_messages"] == 5
    assert session.compaction_events[-1]["dropped_messages"] == 24


def test_session_usage_observations_are_bounded():
    session = _make_session()
    for i in range(25):
        session.record_usage_observation({"estimated_input": i, "actual_input": 100})
    assert len(session.usage_observations) == 20
    assert session.usage_observations[0]["estimated_input"] == 5


def test_old_session_yaml_without_observability_fields():
    session = Session(
        id="old",
        created_at="2026-07-01T00:00:00+00:00",
        updated_at="2026-07-01T00:00:00+00:00",
        output_dir="output",
    )
    assert session.compaction_events == []
    assert session.usage_observations == []


def test_agent_records_compaction_event():
    session = _make_session()
    session.messages = [ChatMessage(role="system", content="system")] + [
        ChatMessage(role="user" if i % 2 == 0 else "assistant", content="x" * 100 + str(i))
        for i in range(20)
    ]
    agent = _make_agent(session)
    agent._get_effective_max_context = lambda: 500
    agent.get_context_status = lambda: {"compaction_threshold": 0.5}

    assert agent._maybe_compact_context() is True
    assert len(session.compaction_events) == 1
    event = session.compaction_events[0]
    assert event["dropped_messages"] > 0
    assert event["before_tokens"] > event["after_tokens"] > 0
    assert event["layer"] == "L1/L2"
    assert event["layers"] == ["L1", "L2"]
    assert event["fallback_used"] is True
    assert event["quality_passed"] is True
    assert event["at"]


def test_agent_records_usage_observation_only_with_real_usage():
    session = _make_session()
    session.messages = [ChatMessage(role="user", content="你好")]
    agent = _make_agent(session)

    agent._record_usage_observation(0)
    assert session.usage_observations == []

    agent._record_usage_observation(1000)
    assert len(session.usage_observations) == 1
    obs = session.usage_observations[0]
    assert obs["actual_input"] == 1000
    assert obs["estimated_input"] > 0
    assert obs["at"]


def test_stream_chunk_usage_estimated_defaults_false():
    chunk = StreamChunk(type="usage", input_tokens=10, output_tokens=5)
    assert chunk.usage_estimated is False


def test_get_context_status_exposes_compaction_and_estimates():
    session = _make_session()
    session.record_compaction_event(
        {
            "at": "2026-07-17T01:00:00+00:00",
            "before_tokens": 900,
            "after_tokens": 300,
            "dropped_messages": 8,
            "layer": "summary",
        }
    )
    session.record_usage_observation({"estimated_input": 800, "actual_input": 1000, "at": "t"})
    agent = _make_agent(session)

    status = agent.get_context_status()

    assert status["compaction_count"] == 1
    assert status["recent_compactions"][0]["layer"] == "summary"
    assert status["usage_observations"][0]["error_pct"] == 20.0


def test_context_status_quiet_without_compaction():
    session = _make_session()
    agent = _make_agent(session)
    status = agent.get_context_status()
    assert status["compaction_count"] == 0
    assert status["recent_compactions"] == []
    assert status["usage_observations"] == []

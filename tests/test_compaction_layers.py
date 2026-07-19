"""B4.4 L0/L1/L2 compaction, quality gates and checkpoint retention."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.core.compactor import ContextCompactor
from src.core.agent import Agent
from src.core.engineering import RunJournalStore, WorkPlan, WorkPlanStep
from src.core.session import SessionStore
from src.models.schemas import ChatMessage, ToolResultContentBlock, ToolUseContentBlock


RUN_ID = "20260718-120000-123456-abcdef"
CRITICAL = "KEEP:requirement=finish-B4-without-replay"
FILE_PATH = "src/core/compactor.py"


class _StructuredGateway:
    main_model = "offline-structured"

    def chat_with_main_model(self, messages=None, **_kwargs):
        return SimpleNamespace(content=json.dumps({
            "schema_version": 1,
            "requirements": [],
            "decisions": [],
            "evidence": [],
            "files_changed": [],
            "todos": [],
            "risks": [],
            "run_refs": [],
            "output_files": [],
        }))


def _noise(round_id: int, count: int = 16) -> list[ChatMessage]:
    return [
        ChatMessage(
            role="user" if index % 2 == 0 else "assistant",
            content=f"round-{round_id}-noise-{index}:" + "x" * 220,
        )
        for index in range(count)
    ]


def test_three_compactions_preserve_entities_checkpoint_and_layer_bounds(tmp_path):
    messages = [
        ChatMessage(role="system", content="system"),
        ChatMessage(role="user", content=f"{CRITICAL} file={FILE_PATH} run={RUN_ID}"),
        ChatMessage(role="assistant", content="ack"),
        ChatMessage(role="user", content="[MAO_TASK_CHECKPOINT] B4.4 remains active"),
        *_noise(0),
    ]
    compactor = ContextCompactor(
        _StructuredGateway(),
        max_context_tokens=400,
        threshold=0.5,
        keep_recent=4,
        min_messages_to_compact=8,
        artifact_dir=tmp_path / "context",
    )

    for round_id in range(3):
        compacted = compactor.maybe_compact(messages)
        assert compactor.last_metadata.applied is True
        assert compactor.last_metadata.schema_valid is True
        assert compactor.last_metadata.entity_retention == 1.0
        assert compactor.last_metadata.quality_passed is True
        assert compactor.last_metadata.checkpoint_count == 1
        messages = compacted
        if round_id < 2:
            messages = [*messages, *_noise(round_id + 1)]

    rendered = "\n".join(message.content for message in messages)
    assert rendered.count("[MAO_CONTEXT_LAYER:L0]") == 1
    assert rendered.count("[MAO_CONTEXT_LAYER:L1]") == 1
    assert rendered.count("[MAO_TASK_CHECKPOINT]") == 1
    assert CRITICAL in rendered
    assert FILE_PATH in rendered
    assert RUN_ID in rendered
    artifacts = list((tmp_path / "context").glob("compaction-*.json"))
    assert 2 <= len(artifacts) <= 3  # identical L1 content reuses its digest artifact


def test_invalid_summary_schema_uses_plain_text_fallback_and_records_quality(tmp_path):
    gateway = _StructuredGateway()
    gateway.chat_with_main_model = lambda *_args, **_kwargs: SimpleNamespace(
        content="legacy summary"
    )
    compactor = ContextCompactor(
        gateway, max_context_tokens=100, threshold=0.5,
        keep_recent=2, min_messages_to_compact=4,
        artifact_dir=tmp_path / "context",
    )
    messages = [
        ChatMessage(role="system", content="system"),
        ChatMessage(role="user", content=f"{CRITICAL} {FILE_PATH}"),
        *_noise(0, 10),
    ]

    result = compactor.maybe_compact(messages)

    assert result is not messages
    assert compactor.last_metadata.schema_valid is False
    assert compactor.last_metadata.fallback_used is True
    assert compactor.last_metadata.fallback_reason == "invalid_summary_schema"
    assert compactor.last_metadata.entity_retention == 1.0
    assert CRITICAL in result[1].content
    assert FILE_PATH in result[1].content
    assert Path(compactor.last_metadata.artifact_path).suffix == ".txt"


def test_native_tool_blocks_contribute_entities_to_compaction():
    native_path = "src/native/important.py"
    messages = [
        ChatMessage(role="system", content="system"),
        ChatMessage(
            role="assistant",
            content="",
            content_blocks=[ToolUseContentBlock(
                id="tool-1", name="write_file",
                input={"path": native_path, "content": "VALUE = 1"},
            )],
        ),
        ChatMessage(
            role="user",
            content="",
            content_blocks=[ToolResultContentBlock(
                tool_use_id="tool-1", content="write completed",
            )],
        ),
        *_noise(0, 10),
    ]
    compactor = ContextCompactor(
        _StructuredGateway(), max_context_tokens=100, threshold=0.5,
        keep_recent=2, min_messages_to_compact=4,
    )

    result = compactor.maybe_compact(messages)

    assert native_path in "\n".join(message.content for message in result)
    assert native_path in compactor.last_metadata.required_entities


def test_duplicate_plain_messages_are_removed_before_summary_but_reported():
    compactor = ContextCompactor(
        _StructuredGateway(), max_context_tokens=100, threshold=0.5,
        keep_recent=2, min_messages_to_compact=4,
    )
    duplicate = ChatMessage(role="user", content="same file read result")
    messages = [
        ChatMessage(role="system", content="system"),
        duplicate,
        duplicate.model_copy(deep=True),
        *_noise(0, 10),
    ]

    compactor.maybe_compact(messages)

    assert compactor.last_metadata.deduplicated_messages == 1


def test_summary_call_failure_keeps_original_history_and_records_reason():
    gateway = _StructuredGateway()
    gateway.chat_with_main_model = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("offline")
    )
    compactor = ContextCompactor(
        gateway, max_context_tokens=100, threshold=0.5,
        keep_recent=2, min_messages_to_compact=4,
    )
    messages = [ChatMessage(role="system", content="system"), *_noise(0, 10)]

    result = compactor.maybe_compact(messages)

    assert result is messages
    assert compactor.last_metadata.fallback_reason == "summary_call_failed_or_empty"


def test_agent_generates_fixed_checkpoint_from_active_run(tmp_path):
    sessions = SessionStore(tmp_path / "sessions")
    session = sessions.create("checkpoint")
    runs = RunJournalStore.from_output_dir(session.output_dir)
    journal = runs.create(session.id, "finish B4.4", "auto")
    journal.plan = WorkPlan(
        objective="finish B4.4",
        status="in_progress",
        steps=[WorkPlanStep(id="pending", title="run benchmark", status="in_progress")],
    )
    journal.files_changed = [FILE_PATH]
    runs.save(journal)
    session.messages = [ChatMessage(role="system", content="system"), *_noise(0, 20)]
    agent = Agent(_StructuredGateway(), session, journal_store=runs)
    agent._active_run_journal = journal
    agent._get_effective_max_context = lambda: 400
    agent.get_context_status = lambda: {"compaction_threshold": 0.5}

    assert agent._maybe_compact_context() is True

    checkpoint = next(
        message.content for message in session.messages
        if "[MAO_TASK_CHECKPOINT]" in message.content
    )
    assert journal.run_id in checkpoint
    assert "run benchmark" in checkpoint
    assert FILE_PATH in checkpoint
    assert session.compaction_events[0]["checkpoint_count"] == 1
    assert Path(session.compaction_events[0]["artifact_path"]).is_file()

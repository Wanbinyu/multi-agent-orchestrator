"""P0-5/P0-6 workset packing and repo navigation."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.core.agent import Agent
from src.core.compactor import ContextCompactor
from src.core.engineering import Evidence, RunJournalStore, VerificationGate
from src.core.memory import MemoryStore, ProjectIndexer
from src.core.repo_nav import rank_repo_files, render_repo_map
from src.core.session import Session
from src.core.workset import build_turn_workset
from src.models.schemas import ChatMessage
from src.tools.memory_tools import repo_map


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


def test_error_stack_lands_in_workset():
    stack = (
        'Traceback (most recent call last):\n'
        '  File "src/ledger.py", line 12, in balance\n'
        "    raise ValueError('boom')\n"
        "ValueError: boom"
    )
    workset = build_turn_workset(
        "为什么报错",
        evidence=[
            Evidence(
                source="tool:run_command",
                claim="测试失败",
                excerpt=stack,
                kind="test",
                tool_name="run_command",
                command="python -m unittest test_ledger.py",
                success=False,
            )
        ],
        verification=[
            VerificationGate(
                requirement="针对性验证",
                command_or_check="python -m unittest test_ledger.py",
                expected="退出码 0",
                actual=stack,
                passed=False,
                check_type="targeted",
            )
        ],
    )
    paths = " ".join(workset.paths)
    assert "src/ledger.py" in paths
    assert any(item.source == "error_stack" for item in workset.items)
    assert "须再 read_file" in workset.prompt()


def test_compaction_drops_chitchat_before_failure_log():
    failure = ChatMessage(
        role="user",
        content=(
            'Traceback (most recent call last):\n'
            '  File "src/ledger.py", line 3\n'
            "AssertionError: expected 3"
        ),
    )
    noise = [
        ChatMessage(
            role="user" if index % 2 == 0 else "assistant",
            content=f"small-talk-{index}:" + "x" * 180,
        )
        for index in range(16)
    ]
    messages = [
        ChatMessage(role="system", content="system"),
        failure,
        *noise,
    ]
    compactor = ContextCompactor(
        _StructuredGateway(),
        max_context_tokens=400,
        threshold=0.5,
        keep_recent=4,
        min_messages_to_compact=8,
        protect_paths=["src/ledger.py"],
    )
    compacted = compactor.maybe_compact(messages)
    rendered = "\n".join(message.content for message in compacted)
    assert "src/ledger.py" in rendered
    assert "AssertionError" in rendered
    assert compactor.last_metadata.applied is True
    assert compactor.last_metadata.dropped_chitchat >= 1
    assert compactor.last_metadata.protected_kept >= 1


def _indexed_project(tmp_path: Path) -> tuple[MemoryStore, Path]:
    root = tmp_path / "project"
    src = root / "src"
    src.mkdir(parents=True)
    for index in range(52):
        (src / f"mod_{index:02d}.py").write_text(
            f"def helper_{index}():\n    return {index}\n",
            encoding="utf-8",
        )
    (src / "widget_router.py").write_text(
        "class WidgetRouter:\n    def dispatch(self):\n        return 'ok'\n",
        encoding="utf-8",
    )
    config = tmp_path / "config" / "memory.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        f"enabled: true\nstorage_path: {tmp_path / 'cache'}\n",
        encoding="utf-8",
    )
    store = MemoryStore(str(config))
    stats = ProjectIndexer(store).index_project(root)
    assert stats["total"] >= 50
    return store, root


def test_repo_map_top10_hits_symbol_file(tmp_path):
    store, root = _indexed_project(tmp_path)
    ranked = rank_repo_files(
        "WidgetRouter is not defined",
        store.get_file_index().files,
        top_k=10,
    )
    paths = [item.path for item in ranked]
    assert any(path.endswith("widget_router.py") for path in paths)
    result = repo_map(
        'File "src/widget_router.py", line 4, in dispatch\nNameError: WidgetRouter',
        path=str(root),
        base_dir=str(root),
        memory_store=store,
        top_k=10,
    )
    assert result.success is True
    assert "须再 read" in result.output
    assert "widget_router.py" in result.output
    assert result.metadata["navigation_only"] is True
    rendered = render_repo_map(ranked, query="WidgetRouter")
    assert "无 LSP" in rendered


def test_agent_records_workset_from_user_stack(tmp_path):
    session = Session(
        id="workset-session",
        title="t",
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
    )
    agent = Agent(MagicMock(), session, journal_store=RunJournalStore(tmp_path / "runs"))
    journal = agent._start_engineering_run(
        '定位这个报错：File "src/billing.py", line 9\nTraceback'
    )
    paths = (journal.metrics.get("workset") or {}).get("paths") or []
    assert any("billing.py" in str(path) for path in paths)
    prompt = agent._workset_prompt()
    assert "billing.py" in prompt
    assert "须再 read_file" in prompt
    agent.gateway.chat_with_main_model.assert_not_called()

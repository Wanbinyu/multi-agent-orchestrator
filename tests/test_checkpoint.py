"""P0-7 workspace checkpoints stay off the user Git history."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from unittest.mock import MagicMock

from src.cli.chat_command import COMMANDS
from src.cli.chat_command import _cmd_checkpoint
from src.core.agent import Agent
from src.core.checkpoint import (
    WorkspaceCheckpointStore,
    git_dirty_paths,
    maybe_snapshot_before_write,
    session_checkpoint_dir,
)
from src.core.engineering import RunJournalStore
from src.core.session import Session


pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git 不可用")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "mao@example.com")
    _git(root, "config", "user.name", "MAO Test")
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    _git(root, "add", "app.py")
    _git(root, "commit", "-m", "init")
    return root


def test_create_preview_restore_roundtrip(tmp_path):
    root = _repo(tmp_path)
    store = WorkspaceCheckpointStore(tmp_path / "snaps", root)
    created = store.create()
    (root / "app.py").write_text("value = 2\n", encoding="utf-8")

    preview = store.preview(created.id)
    kinds = {item.path: item.kind for item in preview.diffs}
    assert kinds["app.py"] == "modified"
    denied = store.restore(created.id, confirm=False)
    assert denied.restored is False
    assert (root / "app.py").read_text(encoding="utf-8") == "value = 2\n"

    restored = store.restore(created.id, confirm=True, overwrite_dirty=True)
    assert restored.restored is True
    assert (root / "app.py").read_text(encoding="utf-8") == "value = 1\n"
    assert not (tmp_path / "workspace" / ".git" / "mao-shadow").exists()
    log = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "init" in log.stdout
    assert log.stdout.count("\n") == 1


def test_restore_refuses_dirty_user_edits(tmp_path):
    root = _repo(tmp_path)
    store = WorkspaceCheckpointStore(tmp_path / "snaps", root)
    created = store.create()
    (root / "app.py").write_text("user edit\n", encoding="utf-8")
    assert "app.py" in git_dirty_paths(root)

    blocked = store.restore(created.id, confirm=True, overwrite_dirty=False)
    assert blocked.restored is False
    assert "app.py" in blocked.dirty_conflicts
    assert (root / "app.py").read_text(encoding="utf-8") == "user edit\n"

    forced = store.restore(created.id, confirm=True, overwrite_dirty=True)
    assert forced.restored is True
    assert (root / "app.py").read_text(encoding="utf-8") == "value = 1\n"


def test_checkpoint_skips_secrets_and_does_not_copy_git(tmp_path):
    root = _repo(tmp_path)
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (root / "notes.md").write_text("ok\n", encoding="utf-8")
    store = WorkspaceCheckpointStore(tmp_path / "snaps", root)
    created = store.create()
    paths = {item.path for item in created.files}
    assert "notes.md" in paths
    assert ".env" not in paths
    assert created.skipped_sensitive >= 1
    snap_git = tmp_path / "snaps" / created.id / "files" / ".git"
    assert not snap_git.exists()


def test_help_mentions_checkpoint():
    assert "/checkpoint" in COMMANDS
    assert "auto" in COMMANDS
    assert "prune" in COMMANDS
    session = Session(
        id="ck",
        title="t",
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
        output_dir=str(Path("sessions") / "ck" / "output"),
    )
    assert session.auto_checkpoint is True


def test_prune_keeps_newest_and_respects_size_cap(tmp_path):
    root = _repo(tmp_path)
    store = WorkspaceCheckpointStore(tmp_path / "snaps", root)
    created = [store.create(max_keep=20) for _ in range(4)]
    assert len(store.list()) == 4
    deleted = store.prune(keep=2)
    remaining = {item.id for item in store.list()}
    assert len(remaining) == 2
    assert created[-1].id in remaining
    assert created[-2].id in remaining
    assert created[0].id in deleted

    bloated = root / "blob.bin"
    bloated.write_bytes(b"x" * 4096)
    store.create(max_keep=20)
    deleted_by_size = store.prune(keep=20, max_bytes=3000)
    assert deleted_by_size
    assert store.usage()["count"] >= 1


def test_create_skips_nested_git_and_caps_file_count(tmp_path):
    root = _repo(tmp_path)
    nested = root / "vendor" / "lib"
    nested.mkdir(parents=True)
    _git(nested, "init")
    (nested / "secret.py").write_text("nested = 1\n", encoding="utf-8")
    (root / "keep.py").write_text("keep = 1\n", encoding="utf-8")
    store = WorkspaceCheckpointStore(tmp_path / "snaps", root)
    created = store.create(max_files=1)
    paths = {item.path for item in created.files}
    assert "keep.py" in paths or created.file_count == 1
    assert not any(path.startswith("vendor/") for path in paths)
    assert created.skipped_capped >= 0


def test_auto_snapshot_once_per_run_and_can_be_disabled(tmp_path):
    root = _repo(tmp_path)
    store = WorkspaceCheckpointStore(tmp_path / "snaps", root)
    first = maybe_snapshot_before_write(
        store, enabled=True, tool_name="write_file", run_id="run-1"
    )
    assert first.created is True
    second = maybe_snapshot_before_write(
        store,
        enabled=True,
        already_id=first.checkpoint_id,
        tool_name="edit_file",
        run_id="run-1",
    )
    assert second.skipped is True
    assert second.reason == "already"
    ignored = maybe_snapshot_before_write(
        store, enabled=True, tool_name="read_file", run_id="run-2"
    )
    assert ignored.reason == "not_mutation"
    disabled = maybe_snapshot_before_write(
        store, enabled=False, tool_name="write_file", run_id="run-2"
    )
    assert disabled.reason == "disabled"
    assert len(store.list()) == 1


def test_checkpoint_auto_command_persists_session_flag(tmp_path, capsys):
    session = Session(
        id="ck-auto",
        title="t",
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
    )
    assert session.auto_checkpoint is True
    changed = _cmd_checkpoint(session, "auto off")
    assert changed is True
    assert session.auto_checkpoint is False
    assert "off" in capsys.readouterr().out
    assert _cmd_checkpoint(session, "auto") is False
    assert "off" in capsys.readouterr().out


def test_agent_first_write_creates_auto_checkpoint(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    session = Session(
        id="ck-run",
        title="t",
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
        output_dir=str(tmp_path / "sess" / "output"),
    )
    Path(session.output_dir).mkdir(parents=True, exist_ok=True)
    gateway = MagicMock()
    gateway.main_model = None
    agent = Agent(gateway, session, journal_store=RunJournalStore(tmp_path / "runs"))
    journal = agent.journal_store.create(session.id, "改文件", "auto")
    content = '```tool:write_file\n{"path": "note.txt", "content": "x"}\n```'
    agent._execute_tool_calls(content, run_journal=journal)
    metrics = journal.metrics.get("workspace_checkpoint") or {}
    assert metrics.get("id")
    assert metrics.get("source") == "auto"
    store = WorkspaceCheckpointStore(session_checkpoint_dir(session.output_dir), root)
    loaded = store.load(metrics["id"])
    assert loaded.source == "auto"
    assert any("自动快照" in item for item in journal.decisions)

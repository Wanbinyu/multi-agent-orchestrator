"""P0-3 Git inspection and constrained commit."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.core.engineering import ToolEvidenceRecorder
from src.core.engineering.journal import RunJournalStore
from src.core.permission_rules import PermissionRuleEngine
from src.tools.git_tools import git_commit, git_diff, git_log
from src.tools.registry import tool_registry
from src.tools.worker_tools import run_command

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git 不可用")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "mao@example.com")
    _git(root, "config", "user.name", "MAO Test")
    (root / "readme.txt").write_text("hello\n", encoding="utf-8")
    _git(root, "add", "readme.txt")
    _git(root, "commit", "-m", "init")
    return root


def test_git_diff_and_log_are_readonly(tmp_path):
    root = _repo(tmp_path)
    (root / "readme.txt").write_text("hello world\n", encoding="utf-8")

    diff = git_diff(".", base_dir=str(root))
    log = git_log(".", max_count=5, base_dir=str(root))

    assert diff.success is True
    assert "readme.txt" in diff.output
    assert log.success is True
    assert "init" in log.output
    assert "hello world" in (root / "readme.txt").read_text(encoding="utf-8")


def test_git_commit_requires_paths_or_staged(tmp_path):
    root = _repo(tmp_path)
    result = git_commit(path=".", message="no files", base_dir=str(root))
    assert result.success is False
    assert result.metadata["error_code"] == "commit_paths_required"


def test_git_commit_records_message_and_files(tmp_path):
    root = _repo(tmp_path)
    (root / "app.py").write_text("print(1)\n", encoding="utf-8")
    result = git_commit(
        path=".",
        message="add app",
        files=["app.py"],
        base_dir=str(root),
    )
    assert result.success is True
    assert result.metadata["message"] == "add app"
    assert result.metadata["files"] == ["app.py"]
    assert result.metadata["pushed"] is False
    assert result.metadata["commit_sha"]

    journal = RunJournalStore(tmp_path / "runs").create("s", "提交", "auto")
    ToolEvidenceRecorder().record(journal, "git_commit", {"path": "."}, result)
    evidence = journal.evidence[-1]
    assert evidence.kind == "change"
    assert "add app" in evidence.claim
    assert evidence.metadata["files"] == ["app.py"]


def test_git_commit_rejects_sensitive_env(tmp_path):
    root = _repo(tmp_path)
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    result = git_commit(
        path=".",
        message="leak",
        files=[".env"],
        base_dir=str(root),
    )
    assert result.success is False
    assert result.metadata.get("error_code") == "sensitive_path"


def test_readonly_session_denies_git_commit():
    decision = PermissionRuleEngine().decide(
        "git_commit",
        {"message": "x", "files": ["a.py"]},
        category="write",
        approval_mode="readonly",
    )
    assert decision.action == "deny"


def test_run_command_has_no_git_push_entry(tmp_path):
    result = run_command("git push origin main", str(tmp_path))
    assert result.success is False
    assert result.metadata["error_code"] == "git_mutation_denied"


def test_registry_exposes_git_tools():
    import src.tools.worker_tools  # noqa: F401

    names = tool_registry.list_tools()
    for expected in ("git_status", "git_diff", "git_log", "git_commit"):
        assert expected in names
    assert "git_push" not in names

"""Workspace file checkpoints that never write the user's Git history."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.tools.safety_guards import is_sensitive_path

CheckpointKind = Literal["added", "modified", "deleted", "unchanged"]
CheckpointSource = Literal["manual", "auto"]
MUTATION_TOOLS = frozenset({"write_file", "edit_file"})
_DEFAULT_MAX_BYTES = 1_000_000
DEFAULT_MAX_KEEP = 8
DEFAULT_MAX_STORE_BYTES = 200 * 1024 * 1024
DEFAULT_MAX_FILES = 2500
DEFAULT_AUTO_MAX_FILES = 80
_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".mao",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "sessions",
    "output",
}


class CheckpointFile(BaseModel):
    path: str
    sha256: str
    size: int


class CheckpointManifest(BaseModel):
    id: str
    created_at: str
    root: str
    file_count: int
    skipped_sensitive: int = 0
    skipped_large: int = 0
    skipped_capped: int = 0
    source: CheckpointSource = "manual"
    run_id: str = ""
    pruned: list[str] = Field(default_factory=list)
    files: list[CheckpointFile] = Field(default_factory=list)


class SnapshotAction(BaseModel):
    created: bool = False
    skipped: bool = False
    reason: str = ""
    checkpoint_id: str = ""
    pruned: list[str] = Field(default_factory=list)
    file_count: int = 0


class CheckpointDiff(BaseModel):
    path: str
    kind: CheckpointKind
    snapshot_sha256: str = ""
    current_sha256: str = ""


class RestorePreview(BaseModel):
    checkpoint_id: str
    diffs: list[CheckpointDiff] = Field(default_factory=list)
    dirty_conflicts: list[str] = Field(default_factory=list)

    @property
    def would_change(self) -> list[CheckpointDiff]:
        return [item for item in self.diffs if item.kind != "unchanged"]


class RestoreResult(BaseModel):
    restored: bool
    checkpoint_id: str
    restored_files: list[str] = Field(default_factory=list)
    reason: str = ""
    dirty_conflicts: list[str] = Field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel(path: Path) -> str:
    return path.as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _should_skip_dir(name: str) -> bool:
    return name.casefold() in _SKIP_DIRS or name.startswith(".")


def iter_workspace_files(
    root: Path,
    *,
    max_files: int | None = None,
) -> tuple[list[Path], int]:
    """Walk the workspace, skipping ignored and nested-git dirs.

    Returns (files, extra_seen_after_cap). The extra count is 0 or 1+: we stop
    shortly after the cap so callers can record that the snapshot was truncated.
    """
    files: list[Path] = []
    extra = 0
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        keep: list[str] = []
        for name in dirnames:
            if _should_skip_dir(name):
                continue
            child = current / name
            if child != root and (child / ".git").exists():
                continue
            keep.append(name)
        dirnames[:] = keep
        for name in filenames:
            path = current / name
            try:
                if not path.is_file() or path.is_symlink():
                    continue
            except OSError:
                continue
            if max_files is not None and len(files) >= max_files:
                extra += 1
                if extra >= 8:
                    dirnames[:] = []
                    return files, extra
                continue
            files.append(path)
    return files, extra


def git_dirty_paths(root: Path) -> set[str]:
    """Uncommitted paths in the user repo. Empty if Git is missing or not a repo."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "-uall"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=20,
            shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return set()
    if result.returncode != 0:
        return set()
    dirty: set[str] = set()
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        rest = line[3:].strip().strip('"')
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        rest = rest.replace("\\", "/")
        if rest:
            dirty.add(rest)
    return dirty


class WorkspaceCheckpointStore:
    """Copy-based snapshots stored beside the session, never in user `.git`."""

    def __init__(self, store_dir: str | Path, workspace: str | Path):
        self.store_dir = Path(store_dir).expanduser().resolve()
        self.workspace = Path(workspace).expanduser().resolve()
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        max_bytes: int = _DEFAULT_MAX_BYTES,
        source: CheckpointSource = "manual",
        run_id: str = "",
        max_keep: int = DEFAULT_MAX_KEEP,
        max_store_bytes: int = DEFAULT_MAX_STORE_BYTES,
        max_files: int = DEFAULT_MAX_FILES,
    ) -> CheckpointManifest:
        checkpoint_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + hashlib.sha256(
            _utc_now().encode("utf-8")
        ).hexdigest()[:8]
        snap_root = self.store_dir / checkpoint_id / "files"
        snap_root.mkdir(parents=True, exist_ok=True)
        records: list[CheckpointFile] = []
        skipped_sensitive = 0
        skipped_large = 0
        candidates, skipped_capped = iter_workspace_files(
            self.workspace, max_files=max_files
        )
        for path in candidates:
            relative = path.relative_to(self.workspace).as_posix()
            if is_sensitive_path(path):
                skipped_sensitive += 1
                continue
            size = path.stat().st_size
            if size > max_bytes:
                skipped_large += 1
                continue
            target = snap_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            records.append(CheckpointFile(path=relative, sha256=_sha256(path), size=size))
        manifest = CheckpointManifest(
            id=checkpoint_id,
            created_at=_utc_now(),
            root=str(self.workspace),
            file_count=len(records),
            skipped_sensitive=skipped_sensitive,
            skipped_large=skipped_large,
            skipped_capped=skipped_capped,
            source=source,
            run_id=run_id,
            files=records,
        )
        self._write_manifest(manifest)
        pruned = self.prune(
            keep=max_keep,
            max_bytes=max_store_bytes,
            protect={checkpoint_id},
        )
        if pruned:
            manifest.pruned = pruned
            self._write_manifest(manifest)
        return manifest

    def usage(self) -> dict[str, int]:
        return {"count": len(self.list()), "bytes": self._store_bytes()}

    def prune(
        self,
        *,
        keep: int = DEFAULT_MAX_KEEP,
        max_bytes: int = DEFAULT_MAX_STORE_BYTES,
        protect: set[str] | None = None,
    ) -> list[str]:
        """Drop oldest snapshots until count and size stay under the caps."""
        protect = set(protect or ())
        keep = max(1, int(keep))
        deleted: list[str] = []
        items = self.list()
        for manifest in items[keep:]:
            if manifest.id in protect:
                continue
            self._delete(manifest.id)
            deleted.append(manifest.id)
        remaining = [item for item in self.list() if item.id not in deleted]
        while len(remaining) > 1 and self._store_bytes() > max_bytes:
            victim = next(
                (item for item in reversed(remaining) if item.id not in protect),
                None,
            )
            if victim is None:
                break
            self._delete(victim.id)
            deleted.append(victim.id)
            remaining = [item for item in remaining if item.id != victim.id]
        return deleted

    def _delete(self, checkpoint_id: str) -> None:
        shutil.rmtree(self.store_dir / checkpoint_id, ignore_errors=True)

    def _store_bytes(self) -> int:
        total = 0
        if not self.store_dir.is_dir():
            return 0
        for path in self.store_dir.rglob("*"):
            if not path.is_file():
                continue
            try:
                total += path.stat().st_size
            except OSError:
                continue
        return total

    def list(self) -> list[CheckpointManifest]:
        items = [self.load(path.parent.name) for path in self.store_dir.glob("*/manifest.json")]
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def load(self, checkpoint_id: str) -> CheckpointManifest:
        path = self.store_dir / checkpoint_id / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(f"检查点不存在：{checkpoint_id}")
        return CheckpointManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def preview(self, checkpoint_id: str) -> RestorePreview:
        manifest = self.load(checkpoint_id)
        snap = {item.path: item for item in manifest.files}
        current: dict[str, str] = {}
        candidates, _extra = iter_workspace_files(self.workspace)
        for path in candidates:
            relative = path.relative_to(self.workspace).as_posix()
            if is_sensitive_path(path):
                continue
            current[relative] = _sha256(path)
        diffs: list[CheckpointDiff] = []
        for relative, record in snap.items():
            now = current.get(relative)
            if now is None:
                diffs.append(CheckpointDiff(
                    path=relative, kind="deleted", snapshot_sha256=record.sha256
                ))
            elif now != record.sha256:
                diffs.append(CheckpointDiff(
                    path=relative,
                    kind="modified",
                    snapshot_sha256=record.sha256,
                    current_sha256=now,
                ))
            else:
                diffs.append(CheckpointDiff(
                    path=relative,
                    kind="unchanged",
                    snapshot_sha256=record.sha256,
                    current_sha256=now,
                ))
        changing = {item.path for item in diffs if item.kind != "unchanged"}
        dirty = git_dirty_paths(self.workspace)
        conflicts = sorted(changing.intersection(dirty))
        return RestorePreview(
            checkpoint_id=checkpoint_id,
            diffs=diffs,
            dirty_conflicts=conflicts,
        )

    def restore(
        self,
        checkpoint_id: str,
        *,
        confirm: bool = False,
        overwrite_dirty: bool = False,
    ) -> RestoreResult:
        if not confirm:
            return RestoreResult(
                restored=False,
                checkpoint_id=checkpoint_id,
                reason="恢复需要显式确认；先 /checkpoint preview，再 restore confirm。",
            )
        preview = self.preview(checkpoint_id)
        if preview.dirty_conflicts and not overwrite_dirty:
            return RestoreResult(
                restored=False,
                checkpoint_id=checkpoint_id,
                reason=(
                    "恢复会覆盖未提交改动。确认预览后使用 "
                    "restore <id> confirm overwrite-dirty。"
                ),
                dirty_conflicts=preview.dirty_conflicts,
            )
        snap_root = self.store_dir / checkpoint_id / "files"
        restored: list[str] = []
        for diff in preview.would_change:
            source = snap_root / diff.path
            target = self.workspace / diff.path
            if not source.is_file():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            restored.append(diff.path)
        return RestoreResult(
            restored=True,
            checkpoint_id=checkpoint_id,
            restored_files=restored,
        )

    def _write_manifest(self, manifest: CheckpointManifest) -> None:
        path = self.store_dir / manifest.id / "manifest.json"
        path.write_text(
            json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def session_checkpoint_dir(output_dir: str | Path) -> Path:
    return Path(output_dir).expanduser().resolve().parent / "checkpoints"


def maybe_snapshot_before_write(
    store: WorkspaceCheckpointStore,
    *,
    enabled: bool,
    already_id: str = "",
    tool_name: str,
    run_id: str = "",
    max_keep: int = DEFAULT_MAX_KEEP,
    max_store_bytes: int = DEFAULT_MAX_STORE_BYTES,
) -> SnapshotAction:
    """Create at most one auto snapshot before the first workspace mutation."""
    if tool_name not in MUTATION_TOOLS:
        return SnapshotAction(skipped=True, reason="not_mutation", checkpoint_id=already_id)
    if not enabled:
        return SnapshotAction(skipped=True, reason="disabled", checkpoint_id=already_id)
    if already_id:
        return SnapshotAction(skipped=True, reason="already", checkpoint_id=already_id)
    try:
        manifest = store.create(
            source="auto",
            run_id=run_id,
            max_keep=max_keep,
            max_store_bytes=max_store_bytes,
            max_files=DEFAULT_AUTO_MAX_FILES,
        )
    except OSError as exc:
        return SnapshotAction(skipped=True, reason=f"create_failed:{exc}")
    return SnapshotAction(
        created=True,
        checkpoint_id=manifest.id,
        pruned=list(manifest.pruned),
        file_count=manifest.file_count,
    )

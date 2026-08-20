"""Task-oriented working set for the current engineering turn."""
from __future__ import annotations

from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field

from src.core.repo_nav import extract_stack_paths

WorksetSource = Literal["error_stack", "recent_read", "grep", "user", "nav", "mutation"]


class WorksetItem(BaseModel):
    path: str
    source: WorksetSource
    score: float = 0.0


class TurnWorkset(BaseModel):
    query: str = ""
    items: list[WorksetItem] = Field(default_factory=list)

    @property
    def paths(self) -> list[str]:
        return [item.path for item in self.items]

    def prompt(self) -> str:
        if not self.items:
            return ""
        lines = [
            "【本轮工作集】仅导航证据，必须再 read_file 后才能当作源码事实。",
        ]
        for item in self.items[:12]:
            lines.append(f"- {item.path}（{item.source}）")
        return "\n".join(lines)


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip().strip("\"'`")


def _add(
    bucket: dict[str, WorksetItem],
    path: str,
    source: WorksetSource,
    score: float,
) -> None:
    cleaned = _normalize_path(path)
    if not cleaned or cleaned in {".", ".."}:
        return
    existing = bucket.get(cleaned)
    if existing is None or score > existing.score:
        bucket[cleaned] = WorksetItem(path=cleaned, source=source, score=score)


def build_turn_workset(
    user_input: str,
    *,
    evidence: Iterable[Any] = (),
    verification: Iterable[Any] = (),
    nav_paths: Iterable[str] = (),
) -> TurnWorkset:
    """Collect a small set of task-relevant paths from real artifacts."""
    bucket: dict[str, WorksetItem] = {}
    looks_like_stack = any(
        marker in (user_input or "")
        for marker in ("Traceback", 'File "', "Error:", "Exception")
    )
    for path in extract_stack_paths(user_input):
        if looks_like_stack:
            _add(bucket, path, "error_stack", 10)
        else:
            _add(bucket, path, "user", 6)

    for item in evidence:
        path = _normalize_path(str(getattr(item, "path", "") or ""))
        tool = str(getattr(item, "tool_name", "") or "")
        excerpt = str(getattr(item, "excerpt", "") or "")
        command = str(getattr(item, "command", "") or "")
        if tool == "read_file" and path:
            _add(bucket, path, "recent_read", 7)
        if tool == "grep_content" and path:
            _add(bucket, path, "grep", 6)
        if tool in {"write_file", "edit_file"} and path:
            _add(bucket, path, "mutation", 8)
        for found in extract_stack_paths("\n".join(part for part in (excerpt, command) if part)):
            _add(bucket, found, "error_stack", 12)

    for gate in verification:
        actual = str(getattr(gate, "actual", "") or "")
        command = str(getattr(gate, "command_or_check", "") or "")
        passed = getattr(gate, "passed", None)
        for found in extract_stack_paths(f"{command}\n{actual}"):
            _add(bucket, found, "error_stack", 13 if passed is False else 8)

    for path in nav_paths:
        _add(bucket, path, "nav", 5)

    items = sorted(bucket.values(), key=lambda item: (-item.score, item.path))
    return TurnWorkset(query=user_input[:200], items=items[:16])

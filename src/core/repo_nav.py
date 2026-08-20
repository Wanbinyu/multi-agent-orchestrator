"""Minimal repo navigation: path heuristics and symbol ranking.

This is navigation evidence only. It does not open files and is not a
semantic search or LSP.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, Field

from src.core.memory import FileIndexEntry

_STACK_FILE_RE = re.compile(
    r'(?:File\s+"([^"]+)"|^\s*(?:[A-Za-z]:)?[\\/]?(?:[\w.-]+[\\/])+[\w.-]+\.[A-Za-z0-9]{1,12})',
    re.MULTILINE,
)
_WIN_OR_POSIX_RE = re.compile(
    r"(?<![\w])(?:[A-Za-z]:[\\/])?(?:[\w.@-]+[\\/])+[\w.@-]+\.[A-Za-z0-9]{1,12}"
)
_LINE_PATH_RE = re.compile(
    r"((?:[\w.-]+[\\/])+[\w.-]+\.[A-Za-z0-9]{1,12})(?::\d+)"
)
_IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{1,80}\b")
_NAV_DISCLAIMER = "仅导航证据，须再 read_file 后才能当作源码事实。无 LSP/AST，不能当已读。"


class RankedFile(BaseModel):
    path: str
    score: float
    reasons: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)


def extract_stack_paths(text: str) -> list[str]:
    """Pull file paths out of tracebacks and compiler-style locations."""
    if not text:
        return []
    found: list[str] = []
    for match in _STACK_FILE_RE.finditer(text):
        quoted = match.group(1)
        if quoted:
            found.append(quoted)
    found.extend(_WIN_OR_POSIX_RE.findall(text))
    found.extend(_LINE_PATH_RE.findall(text))
    normalized: list[str] = []
    for item in found:
        path = item.replace("\\", "/").strip().strip("\"'")
        if path and path not in normalized:
            normalized.append(path)
    return normalized


def extract_query_tokens(query: str) -> list[str]:
    tokens = [item for item in _IDENT_RE.findall(query or "") if len(item) > 1]
    return list(dict.fromkeys(tokens))


def score_indexed_file(
    entry: FileIndexEntry,
    *,
    tokens: Iterable[str],
    stack_paths: Iterable[str],
) -> RankedFile:
    path = entry.path.replace("\\", "/")
    lower = path.casefold()
    name = Path(path).name.casefold()
    stem = Path(path).stem.casefold()
    symbols = {item.casefold() for item in entry.symbols}
    summary = (entry.summary or "").casefold()
    snippet = (entry.snippet or "").casefold()
    score = 0.0
    reasons: list[str] = []
    token_list = [token for token in tokens if token]
    stack_list = [item.replace("\\", "/") for item in stack_paths]

    for raw in stack_list:
        stack = raw.casefold()
        if lower.endswith(stack) or stack.endswith(lower) or stack in lower:
            score += 12
            reasons.append("error_stack")
            break

    for token in token_list:
        folded = token.casefold()
        if folded in symbols:
            score += 8
            reasons.append(f"symbol:{token}")
        if stem == folded or name == folded or name.startswith(f"{folded}."):
            score += 6
            reasons.append(f"filename:{token}")
        elif folded in name:
            score += 3
            reasons.append(f"name:{token}")
        if folded in lower:
            score += 2
        if folded in summary:
            score += 2
        if folded in snippet:
            score += 1

    if "/test" in lower or name.startswith("test_"):
        if any("test" in token.casefold() for token in token_list):
            score += 1
        else:
            score -= 0.5
    return RankedFile(
        path=path,
        score=round(score, 2),
        reasons=list(dict.fromkeys(reasons)),
        symbols=list(entry.symbols[:8]),
    )


def rank_repo_files(
    query: str,
    files: dict[str, FileIndexEntry] | list[FileIndexEntry],
    *,
    top_k: int = 10,
    extra_text: str = "",
) -> list[RankedFile]:
    """Rank indexed files for a query. Empty query returns no hits."""
    blob = f"{query}\n{extra_text}"
    tokens = extract_query_tokens(blob)
    stacks = extract_stack_paths(blob)
    if not tokens and not stacks:
        return []
    entries = files.values() if isinstance(files, dict) else files
    ranked = [
        score_indexed_file(entry, tokens=tokens, stack_paths=stacks)
        for entry in entries
    ]
    ranked = [item for item in ranked if item.score > 0]
    ranked.sort(key=lambda item: (-item.score, item.path))
    return ranked[: max(1, min(int(top_k), 30))]


def render_repo_map(ranked: list[RankedFile], *, query: str) -> str:
    lines = [
        f'【Repo 导航】查询 “{query.strip() or "（空）"}”。{_NAV_DISCLAIMER}',
        "",
    ]
    if not ranked:
        lines.append("没有足够的路径/符号命中。")
        return "\n".join(lines)
    for index, item in enumerate(ranked, 1):
        reason = "、".join(item.reasons[:3]) or "heuristic"
        symbol = f" 符号：{', '.join(item.symbols[:6])}" if item.symbols else ""
        lines.append(f"{index}. {item.path}  ({reason}{symbol})")
    lines.append("")
    lines.append("局限：只根据路径、文件名和索引里的符号/摘要排序，不会读取全文。")
    return "\n".join(lines)

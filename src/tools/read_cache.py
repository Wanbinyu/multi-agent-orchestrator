"""单轮只读工具缓存键与失效规则。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CACHEABLE_READ_TOOLS = frozenset({
    "list_dir",
    "project_tree",
    "glob_files",
    "grep_content",
    "read_file",
    "search_project_files",
    "search_memory",
})

_KNOWN_NON_MUTATING_TOOLS = frozenset({
    "web_search",
    "fetch_url",
    "word_count",
})


def build_read_cache_key(
    tool_name: str, params: dict[str, Any], base_dir: str
) -> str | None:
    if tool_name not in CACHEABLE_READ_TOOLS:
        return None
    normalized_params = json.dumps(
        params,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"{tool_name}|{Path(base_dir).resolve()}|{normalized_params}"


def should_invalidate_read_cache(tool_name: str) -> bool:
    """未知或可能改变本地状态的工具执行后清空缓存。"""
    return (
        tool_name not in CACHEABLE_READ_TOOLS
        and tool_name not in _KNOWN_NON_MUTATING_TOOLS
    )

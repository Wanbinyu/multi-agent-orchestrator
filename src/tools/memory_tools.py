"""记忆相关工具实现"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.memory import MemoryStore, ProjectIndexer
from src.core.repo_nav import rank_repo_files, render_repo_map
from src.tools.paths import resolve_path
from src.tools.registry import tool_registry
from src.tools.tool_result import ToolResult


@tool_registry.register(
    name="search_project_files",
    description="基于增量项目索引搜索相关源码文件；path 可指定相对或绝对项目根",
    params={
        "query": {"type": "string", "description": "搜索关键词"},
        "path": {"type": "string", "description": "项目根目录", "default": "."},
        "top_k": {"type": "integer", "description": "返回结果数量", "default": 5},
    },
    category="read",
)
def search_project_files(
    query: str,
    path: str = ".",
    base_dir: str = ".",
    top_k: int = 5,
    memory_store: MemoryStore | None = None,
) -> ToolResult:
    """基于本地项目文件索引搜索相关文件

    若索引不存在，会自动触发一次索引构建。
    """
    if not query.strip():
        return ToolResult(success=False, error="查询词不能为空")

    try:
        store = memory_store or MemoryStore()
        indexer = ProjectIndexer(store)
        project_root = resolve_path(path, base_dir)
        stats = indexer.index_project(root_dir=project_root)

        ranked = rank_repo_files(query, store.get_file_index().files, top_k=top_k)
        if not ranked:
            return ToolResult(
                success=True,
                output=(
                    f"未找到与 '{query}' 相关的项目文件。"
                    "（仅导航证据，须再 read_file）"
                ),
                metadata={"project_index": stats, "cached": stats["read"] == 0},
            )

        files = store.get_file_index().files
        lines = [
            f'搜索 "{query}" 的结果（top {len(ranked)}）。仅导航证据，须再 read_file。',
            "",
        ]
        for i, hit in enumerate(ranked, 1):
            entry = files.get(hit.path)
            lines.append(f"{i}. {hit.path}")
            if hit.reasons:
                lines.append(f"   原因：{'、'.join(hit.reasons[:4])}")
            if entry and entry.symbols:
                lines.append(f"   符号：{', '.join(entry.symbols[:10])}")
            if entry and entry.summary:
                lines.append(f"   摘要：{entry.summary}")
            if entry and entry.snippet:
                snippet = entry.snippet.replace("\n", " ")[:200]
                lines.append(f"   片段：{snippet}...")
            lines.append("")

        return ToolResult(
            success=True,
            output="\n".join(lines),
            metadata={
                "project_index": stats,
                "cached": stats["read"] == 0,
                "paths": [item.path for item in ranked],
                "navigation_only": True,
            },
        )
    except Exception as e:
        return ToolResult(success=False, error=str(e))


@tool_registry.register(
    name="repo_map",
    description=(
        "按任务查询返回 Top-K 候选文件（路径启发式 + 符号名）。"
        "仅导航证据，必须再 read_file，不是语义搜索。"
    ),
    params={
        "query": {"type": "string", "description": "符号名、报错字符串或路径片段"},
        "path": {"type": "string", "description": "项目根目录", "default": "."},
        "top_k": {"type": "integer", "description": "返回数量，默认 10", "default": 10},
    },
    category="read",
)
def repo_map(
    query: str,
    path: str = ".",
    base_dir: str = ".",
    top_k: int = 10,
    memory_store: MemoryStore | None = None,
) -> ToolResult:
    if not query.strip():
        return ToolResult(success=False, error="查询词不能为空")
    try:
        store = memory_store or MemoryStore()
        indexer = ProjectIndexer(store)
        project_root = resolve_path(path, base_dir)
        stats = indexer.index_project(root_dir=project_root)
        ranked = rank_repo_files(
            query, store.get_file_index().files, top_k=top_k
        )
        return ToolResult(
            success=True,
            output=render_repo_map(ranked, query=query),
            metadata={
                "project_index": stats,
                "cached": stats["read"] == 0,
                "paths": [item.path for item in ranked],
                "navigation_only": True,
                "limitations": "no_lsp_no_ast",
            },
        )
    except Exception as exc:
        return ToolResult(success=False, error=str(exc))


@tool_registry.register(
    name="search_memory",
    description="搜索已保存的长期记忆",
    params={
        "query": {"type": "string", "description": "搜索关键词"},
        "top_k": {"type": "integer", "description": "返回结果数量", "default": 5},
    },
    category="read",
)
def search_memory(query: str, top_k: int = 5) -> ToolResult:
    """搜索长期记忆条目"""
    if not query.strip():
        return ToolResult(success=False, error="查询词不能为空")

    try:
        store = MemoryStore()
        entries = store.search(query, top_k=top_k)
        if not entries:
            return ToolResult(success=True, output=f"未找到与 '{query}' 相关的记忆。")

        lines = [f'记忆搜索结果（top {len(entries)}）：', ""]
        for entry in entries:
            lines.append(f"[{entry.category}] {entry.content}")
            lines.append(f"   来源：{entry.source} | 重要性：{entry.importance} | id：{entry.id}")
            if entry.tags:
                lines.append(f"   标签：{', '.join(entry.tags)}")
            lines.append("")

        return ToolResult(success=True, output="\n".join(lines))
    except Exception as e:
        return ToolResult(success=False, error=str(e))

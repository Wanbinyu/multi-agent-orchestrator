"""文件搜索工具：glob_files 与 grep_content

基于标准库实现，无外部依赖。
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from src.tools.paths import resolve_path as _resolve_path
from src.tools.registry import tool_registry
from src.tools.tool_result import ToolResult

# 结果数量上限，避免输出过长
_MAX_GLOB_RESULTS = 200
_MAX_GREP_RESULTS = 50
_MAX_GREP_FILE_SIZE = 500_000
_TREE_IGNORED_DIRS = {
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
    "dist",
    "build",
}


@tool_registry.register(
    name="project_tree",
    description="生成稳定、受深度和节点数限制的项目目录树；项目分析时优先使用，支持绝对路径",
    params={
        "path": {"type": "string", "description": "项目根目录，相对或绝对", "default": "."},
        "max_depth": {"type": "integer", "description": "最大展开深度", "default": 4},
        "max_entries": {"type": "integer", "description": "最大节点数量", "default": 300},
        "include_hidden": {"type": "boolean", "description": "是否显示隐藏文件", "default": False},
    },
    category="read",
)
def project_tree(
    path: str = ".",
    max_depth: int = 4,
    max_entries: int = 300,
    include_hidden: bool = False,
    base_dir: str = ".",
) -> ToolResult:
    """生成跨平台项目树，不依赖外部 tree/dir/ls 命令。"""
    if not 0 <= max_depth <= 20:
        return ToolResult(success=False, error="max_depth 必须在 0 到 20 之间")
    if not 1 <= max_entries <= 5000:
        return ToolResult(success=False, error="max_entries 必须在 1 到 5000 之间")

    try:
        root = _resolve_path(path, base_dir)
    except ValueError as exc:
        return ToolResult(success=False, error=str(exc))
    if not root.exists():
        return ToolResult(success=False, error=f"目录不存在：{path}")
    if not root.is_dir():
        return ToolResult(success=False, error=f"不是目录：{path}")

    lines = [f"项目结构：{root}"]
    entry_count = 0
    depth_truncated = 0
    entries_truncated = False

    def visible_entries(directory: Path) -> list[Path]:
        entries = []
        for entry in directory.iterdir():
            if entry.is_dir() and entry.name in _TREE_IGNORED_DIRS:
                continue
            if not include_hidden and entry.name.startswith("."):
                continue
            entries.append(entry)
        return sorted(
            entries,
            key=lambda item: (not item.is_dir(), item.name.casefold(), item.name),
        )

    def walk(directory: Path, prefix: str, depth: int) -> None:
        nonlocal entry_count, depth_truncated, entries_truncated
        if entries_truncated:
            return
        try:
            entries = visible_entries(directory)
        except OSError as exc:
            lines.append(f"{prefix}└── [无法访问：{exc}]")
            return

        for index, entry in enumerate(entries):
            if entry_count >= max_entries:
                entries_truncated = True
                return
            is_last = index == len(entries) - 1
            connector = "└── " if is_last else "├── "
            is_directory = entry.is_dir()
            suffix = "/" if is_directory else ""
            if entry.is_symlink():
                suffix += " -> symlink"
            lines.append(f"{prefix}{connector}{entry.name}{suffix}")
            entry_count += 1

            if not is_directory or entry.is_symlink():
                continue
            if depth >= max_depth:
                depth_truncated += 1
                continue
            child_prefix = prefix + ("    " if is_last else "│   ")
            walk(entry, child_prefix, depth + 1)
            if entries_truncated:
                return

    if max_depth == 0:
        depth_truncated = 1
    else:
        walk(root, "", 1)
    if entries_truncated:
        lines.append(f"...（已达到 {max_entries} 个节点上限，目录树已截断）")
    if depth_truncated:
        lines.append(
            f"...（{depth_truncated} 个目录达到最大深度 {max_depth}，未继续展开）"
        )
    lines.append(f"共显示 {entry_count} 个节点")
    return ToolResult(success=True, output="\n".join(lines))


@tool_registry.register(
    name="list_dir",
    description="列出指定目录下的文件和子目录（跨平台，支持绝对路径），用于探查目录结构",
    params={
        "path": {"type": "string", "description": "目录路径，相对或绝对", "default": "."},
    },
    category="read",
)
def list_dir(path: str = ".", base_dir: str = ".") -> ToolResult:
    try:
        target = _resolve_path(path, base_dir)
        if not target.exists():
            return ToolResult(success=False, error=f"目录不存在：{path}")
        if not target.is_dir():
            return ToolResult(success=False, error=f"不是目录：{path}")

        entries = []
        for entry in sorted(target.iterdir()):
            if entry.is_dir():
                entries.append(f"📁 {entry.name}/")
            else:
                size = entry.stat().st_size
                entries.append(f"📄 {entry.name} ({size} B)")
        if not entries:
            return ToolResult(success=True, output=f"目录为空：{path}")
        header = f"目录 {target}（{len(entries)} 项）："
        return ToolResult(success=True, output=header + "\n" + "\n".join(entries))
    except ValueError as e:
        return ToolResult(success=False, error=str(e))
    except Exception as e:
        return ToolResult(success=False, error=str(e))


@tool_registry.register(
    name="glob_files",
    description="按通配符模式列出匹配的文件路径，支持 ** 递归；path 指定搜索根目录（默认当前目录，可用绝对路径）",
    params={
        "pattern": {"type": "string", "description": "通配符模式，如 **/*.py 或 src/**/*.ts"},
        "path": {"type": "string", "description": "搜索根目录，相对或绝对", "default": "."},
    },
    category="read",
)
def glob_files(pattern: str, path: str = ".", base_dir: str = ".") -> ToolResult:
    if not pattern.strip():
        return ToolResult(success=False, error="pattern 不能为空")
    try:
        base = _resolve_path(path, base_dir)
        # Path.glob 支持 ** 递归
        matched = sorted(p for p in base.glob(pattern) if p.is_file())
        if not matched:
            return ToolResult(success=True, output=f"未找到匹配 {pattern} 的文件。")

        # 相对路径展示
        lines: list[str] = []
        for p in matched[:_MAX_GLOB_RESULTS]:
            try:
                rel = p.relative_to(base)
                lines.append(str(rel))
            except ValueError:
                lines.append(str(p))
        if len(matched) > _MAX_GLOB_RESULTS:
            lines.append(f"...（共 {len(matched)} 个文件，已截断显示前 {_MAX_GLOB_RESULTS} 个）")

        header = f"匹配 {pattern}（{len(matched)} 个文件，根目录 {base}）："
        return ToolResult(success=True, output=header + "\n" + "\n".join(lines))
    except Exception as e:
        return ToolResult(success=False, error=str(e))


@tool_registry.register(
    name="grep_content",
    description="在文件内容中搜索正则表达式，返回匹配的文件名与行",
    params={
        "pattern": {"type": "string", "description": "正则表达式"},
        "path": {"type": "string", "description": "搜索目录或文件，默认当前目录", "default": "."},
    },
    category="read",
)
def grep_content(pattern: str, path: str = ".", base_dir: str = ".") -> ToolResult:
    if not pattern.strip():
        return ToolResult(success=False, error="pattern 不能为空")
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return ToolResult(success=False, error=f"正则表达式无效：{e}")

    try:
        target = _resolve_path(path, base_dir)
    except ValueError as e:
        return ToolResult(success=False, error=str(e))

    files: list[Path] = []
    if target.is_file():
        files = [target]
    elif target.is_dir():
        for p in target.rglob("*"):
            if p.is_file():
                files.append(p)
    else:
        return ToolResult(success=False, error=f"路径不存在：{path}")

    results: list[str] = []
    total_matches = 0
    for f in files:
        try:
            if f.stat().st_size > _MAX_GREP_FILE_SIZE:
                continue
            with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                for lineno, line in enumerate(fh, 1):
                    if regex.search(line):
                        try:
                            rel = f.relative_to(_resolve_path(".", base_dir))
                        except ValueError:
                            rel = f
                        results.append(f"{rel}:{lineno}: {line.rstrip()}")
                        total_matches += 1
                        if total_matches >= _MAX_GREP_RESULTS:
                            results.append(f"...（已达 {_MAX_GREP_RESULTS} 条上限，截断）")
                            return ToolResult(success=True, output="\n".join(results))
        except (OSError, UnicodeDecodeError):
            continue

    if not results:
        return ToolResult(success=True, output=f"未找到匹配 {pattern} 的内容。")
    return ToolResult(success=True, output="\n".join(results))

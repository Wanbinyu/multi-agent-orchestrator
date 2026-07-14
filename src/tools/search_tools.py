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


@tool_registry.register(
    name="glob_files",
    description="按通配符模式列出匹配的文件路径，支持 ** 递归",
    params={
        "pattern": {"type": "string", "description": "通配符模式，如 **/*.py 或 src/**/*.ts"},
    },
    category="read",
)
def glob_files(pattern: str, base_dir: str = ".") -> ToolResult:
    if not pattern.strip():
        return ToolResult(success=False, error="pattern 不能为空")
    try:
        base = _resolve_path(".", base_dir)
        # Path.glob 支持 ** 递归
        matched = sorted(p for p in base.glob(pattern) if p.is_file())
        if not matched:
            return ToolResult(success=True, output=f"未找到匹配 {pattern} 的文件。")

        # 相对路径展示
        lines: list[str] = []
        truncated = False
        for p in matched[:_MAX_GLOB_RESULTS]:
            try:
                rel = p.relative_to(base)
                lines.append(str(rel))
            except ValueError:
                lines.append(str(p))
        if len(matched) > _MAX_GLOB_RESULTS:
            truncated = True
            lines.append(f"...（共 {len(matched)} 个文件，已截断显示前 {_MAX_GLOB_RESULTS} 个）")

        header = f"匹配 {pattern}（{len(matched)} 个文件）："
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

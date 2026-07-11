"""Worker 可用的工具实现

支持：
- read_file：读取指定文件内容
- run_command：在指定目录下执行白名单内的命令
"""
from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    output: str = ""
    error: str = ""


def _resolve_path(path: str, base_dir: str) -> Path:
    """把相对路径解析到 base_dir 下，防止目录穿越"""
    base = Path(base_dir).resolve()
    target = (base / path).resolve()
    # 确保 target 在 base 内部
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"路径越界：{path}") from exc
    return target


def read_file(path: str, base_dir: str = ".") -> ToolResult:
    """读取 base_dir 下的文件内容"""
    try:
        target = _resolve_path(path, base_dir)
        if not target.exists():
            return ToolResult(success=False, error=f"文件不存在：{path}")
        if not target.is_file():
            return ToolResult(success=False, error=f"不是文件：{path}")
        with open(target, "r", encoding="utf-8") as f:
            content = f.read()
        return ToolResult(success=True, output=content)
    except Exception as e:
        return ToolResult(success=False, error=str(e))


DEFAULT_ALLOWED_PREFIXES = [
    "pytest",
    "python -m pytest",
    "python ",
    "npm ",
    "node ",
    "npx ",
    "git status",
    "git diff",
    "git log",
]


def _is_command_allowed(command: str, allowed_prefixes: list[str] | None) -> bool:
    """检查命令是否以白名单前缀开头"""
    if allowed_prefixes is None:
        allowed_prefixes = DEFAULT_ALLOWED_PREFIXES
    stripped = command.strip()
    return any(stripped.startswith(prefix) for prefix in allowed_prefixes)


def run_command(
    command: str,
    base_dir: str = ".",
    allowed_prefixes: list[str] | None = None,
    timeout: int = 60,
) -> ToolResult:
    """在 base_dir 下执行命令，要求命令在白名单内"""
    try:
        if not _is_command_allowed(command, allowed_prefixes):
            return ToolResult(
                success=False,
                error=f"命令不在白名单内：{command}",
            )

        base = Path(base_dir).resolve()
        args = shlex.split(command)
        result = subprocess.run(
            args,
            cwd=str(base),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )

        output = result.stdout
        if result.stderr:
            output += "\n[stderr]\n" + result.stderr

        return ToolResult(
            success=result.returncode == 0,
            output=output.strip(),
            error=f"退出码：{result.returncode}" if result.returncode != 0 else "",
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, error=f"命令执行超时（{timeout} 秒）")
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def execute_tool_call(tool_name: str, params: dict, base_dir: str, allowed_prefixes: list[str] | None = None) -> ToolResult:
    """统一分发工具调用"""
    if tool_name == "read_file":
        return read_file(params.get("path", ""), base_dir)
    elif tool_name == "run_command":
        return run_command(params.get("command", ""), base_dir, allowed_prefixes)
    else:
        return ToolResult(success=False, error=f"未知工具：{tool_name}")

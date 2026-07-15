"""Worker 可用的工具实现

工具通过 src.tools.registry.tool_registry 注册，供 Agent 和协作 Worker 统一发现/执行。
"""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from src.tools.paths import resolve_path as _resolve_path
from src.tools.registry import tool_registry
from src.tools.tool_result import ToolResult


# 引入 memory_tools / web_tools / search_tools 以完成其注册
import src.tools.memory_tools  # noqa: F401
import src.tools.search_tools  # noqa: F401
import src.tools.web_tools  # noqa: F401
# 引入 contrib 示例工具（第三方工具也可在此统一 import 注册）
import src.tools.contrib.example_tools  # noqa: F401


@tool_registry.register(
    name="read_file",
    description="读取项目内文件内容，支持相对路径和绝对路径",
    params={"path": {"type": "string", "description": "相对或绝对路径"}},
    category="read",
)
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


@tool_registry.register(
    name="git_status",
    description="只读检查指定项目目录的 Git 分支和工作区状态",
    params={
        "path": {
            "type": "string",
            "description": "项目目录的相对或绝对路径，默认当前工作目录",
        }
    },
    category="read",
)
def git_status(path: str = ".", base_dir: str = ".") -> ToolResult:
    """用固定参数执行只读 Git 状态检查，不接受任意命令。"""
    try:
        target = _resolve_path(path, base_dir)
        if not target.exists():
            return ToolResult(success=False, error=f"目录不存在：{path}")
        if not target.is_dir():
            return ToolResult(success=False, error=f"不是目录：{path}")
        result = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=str(target),
            capture_output=True,
            text=True,
            timeout=15,
            shell=False,
        )
        output = result.stdout.strip()
        if result.stderr:
            output = "\n".join(part for part in (output, result.stderr.strip()) if part)
        return ToolResult(
            success=result.returncode == 0,
            output=output,
            error=f"退出码：{result.returncode}" if result.returncode != 0 else "",
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, error="Git 状态检查超时（15 秒）")
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


@tool_registry.register(
    name="run_command",
    description="在指定目录下执行白名单内的命令（如 python、pytest、npm、git status 等）",
    params={"command": {"type": "string", "description": "要执行的命令"}},
    category="execute",
)
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


@tool_registry.register(
    name="write_file",
    description="写入文件到项目目录或用户指定的绝对路径，支持自动创建父目录",
    params={
        "path": {"type": "string", "description": "相对或绝对路径"},
        "content": {"type": "string", "description": "文件内容"},
    },
    category="write",
)
def write_file(path: str, content: str, base_dir: str = ".") -> ToolResult:
    """在 base_dir 下写入文件，支持自动创建父目录"""
    try:
        target = _resolve_path(path, base_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return ToolResult(success=True, output=f"已写入文件：{path}")
    except Exception as e:
        return ToolResult(success=False, error=str(e))


@tool_registry.register(
    name="edit_file",
    description="精确替换文件中的某段文本，old_string 必须在文件中唯一存在，避免误改",
    params={
        "path": {"type": "string", "description": "相对或绝对路径"},
        "old_string": {"type": "string", "description": "要被替换的原文"},
        "new_string": {"type": "string", "description": "替换后的新文本"},
    },
    category="write",
)
def edit_file(path: str, old_string: str, new_string: str, base_dir: str = ".") -> ToolResult:
    """精确替换文件中的文本片段，要求 old_string 唯一"""
    try:
        if not old_string:
            return ToolResult(success=False, error="old_string 不能为空")
        target = _resolve_path(path, base_dir)
        if not target.exists():
            return ToolResult(success=False, error=f"文件不存在：{path}")
        if not target.is_file():
            return ToolResult(success=False, error=f"不是文件：{path}")

        with open(target, "r", encoding="utf-8") as f:
            content = f.read()

        occurrences = content.count(old_string)
        if occurrences == 0:
            return ToolResult(success=False, error=f"未在文件中找到指定文本：{path}")
        if occurrences > 1:
            return ToolResult(
                success=False,
                error=f"指定文本在文件中出现 {occurrences} 次，不唯一；请提供更长上下文以精确定位。",
            )

        new_content = content.replace(old_string, new_string)
        with open(target, "w", encoding="utf-8") as f:
            f.write(new_content)
        return ToolResult(success=True, output=f"已更新文件：{path}")
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def execute_tool_call(
    tool_name: str,
    params: dict,
    base_dir: str,
    allowed_prefixes: list[str] | None = None,
) -> ToolResult:
    """统一分发工具调用（向后兼容入口）"""
    return tool_registry.execute(tool_name, params, base_dir, allowed_prefixes)

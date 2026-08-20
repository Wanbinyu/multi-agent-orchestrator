"""Worker 可用的工具实现

工具通过 src.tools.registry.tool_registry 注册，供 Agent 和协作 Worker 统一发现/执行。
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, MutableMapping

import yaml
from pydantic import ValidationError

from src.core.config_paths import resolve_workers_config_path

from src.models.schemas import FrontendSmokeContract
from src.tools.paths import resolve_path as _resolve_path
from src.tools.registry import tool_registry
from src.tools.safety_guards import (
    has_dangerous_interpreter_invocation,
    is_sensitive_path,
    sensitive_path_error,
)
from src.tools.tool_result import ToolResult


# 引入 memory_tools / web_tools / search_tools 以完成其注册
import src.tools.git_tools  # noqa: F401
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
        if is_sensitive_path(target):
            return ToolResult(
                success=False,
                error=sensitive_path_error(path),
                metadata={"error_code": "sensitive_path", "path": str(target)},
            )
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
    "python3 ",
    "py ",
    "npm ",
    "pnpm ",
    "yarn ",
    "node ",
    "npx ",
    "git status",
    "git diff",
    "git log",
]

# Conservative extras. Still no shell, no git push/reset, no interpreter -c.
BUILTIN_EXTRA_PREFIXES = [
    "ruff ",
    "uv run ",
    "uvx ",
    "cargo test",
    "cargo check",
    "go test",
]
_DENIED_GIT_MUTATIONS = re.compile(
    r"^git\s+(push|reset|clean|checkout|rebase|filter-branch|update-ref|commit)\b",
    re.IGNORECASE,
)

# 解释器内联/预加载代码执行会绕过路径归属与 permission_rules，必须在 preflight 拒绝。
_COMMAND_PREFLIGHT_ERRORS = {
    "empty_command",
    "inline_cwd",
    "shell_syntax",
    "inline_interpreter_code",
    "command_not_allowed",
    "git_mutation_denied",
    "cwd_not_found",
    "cwd_not_directory",
    "temporary_output_unsupported",
    "permission_denied",
    "sensitive_path",
}
_INLINE_CD = re.compile(
    r"^\s*cd(?:\s+/d)?\s+(?:\"([^\"]+)\"|'([^']+)'|([^&|;\r\n]+?))\s*&&\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_PURPOSE_ORDER = ("typecheck", "lint", "test", "integration", "smoke", "build")
COMMAND_PERMISSION_GUIDANCE = (
    "请根据拒绝理由调整 command/cwd，或请求用户修改权限规则；最多修正一次，"
    "不要重复原调用。"
)


def load_command_allowlist(config_dir: str | Path = "config") -> list[str]:
    """Merge default prefixes with optional workers.yaml command_allowlist."""
    prefixes = list(dict.fromkeys([*DEFAULT_ALLOWED_PREFIXES, *BUILTIN_EXTRA_PREFIXES]))
    path = resolve_workers_config_path(Path(config_dir) / "workers.yaml")
    if not path.exists():
        return prefixes
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return prefixes
    section = data.get("command_allowlist")
    if not isinstance(section, dict):
        return prefixes
    extra = section.get("extra_prefixes") or []
    if not isinstance(extra, list):
        return prefixes
    for item in extra:
        text = str(item).strip()
        if text:
            prefixes.append(text)
    return list(dict.fromkeys(prefixes))


def _matches_discovered_command(command: str, cwd: str, base_dir: str) -> bool:
    result = discover_project_commands(cwd, base_dir)
    if not result.success:
        return False
    try:
        payload = json.loads(result.output)
    except json.JSONDecodeError:
        return False
    wanted = " ".join(command.split())
    for item in payload.get("commands") or []:
        if not isinstance(item, dict) or not item.get("available", True):
            continue
        discovered = " ".join(str(item.get("command", "")).split())
        if discovered and discovered == wanted:
            return True
    return False


def _is_command_allowed(
    command: str,
    allowed_prefixes: list[str] | None,
    *,
    cwd: str = ".",
    base_dir: str = ".",
) -> bool:
    """Prefix allowlist plus exact match against discovered project scripts."""
    stripped = command.strip()
    prefixes = (
        list(allowed_prefixes)
        if allowed_prefixes is not None
        else load_command_allowlist()
    )
    if any(stripped.startswith(prefix) for prefix in prefixes):
        return True
    return _matches_discovered_command(stripped, cwd, base_dir)


def command_correction_exhausted(state: MutableMapping[str, Any] | None) -> bool:
    return bool(state is not None and int(state.get("preflight_failures", 0)) >= 2)


def record_command_preflight_failure(
    state: MutableMapping[str, Any] | None, metadata: dict[str, Any] | None
) -> None:
    if state is None or not metadata:
        return
    if metadata.get("error_code") not in _COMMAND_PREFLIGHT_ERRORS:
        return
    state["preflight_failures"] = min(
        int(state.get("preflight_failures", 0)) + 1, 2
    )


def command_correction_limit_result(cwd: str = ".") -> ToolResult:
    return ToolResult(
        success=False,
        error="命令参数或权限纠错已失败两次，本轮不再重复执行；请检查项目脚本或请求用户调整权限。",
        metadata={
            "error_code": "correction_limit",
            "cwd": cwd,
            "exit_code": None,
            "truncated": False,
        },
    )


def _contains_shell_syntax(command: str) -> bool:
    quote = ""
    index = 0
    while index < len(command):
        char = command[index]
        if quote:
            if char == quote and (index == 0 or command[index - 1] != "\\"):
                quote = ""
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if command[index:index + 2] in {"&&", "||", "$("}:
            return True
        if char in {"|", ";", "<", ">", "`", "\n", "\r", "&"}:
            return True
        index += 1
    return False


def _has_inline_interpreter_code(command: str) -> bool:
    """检测解释器内联/预加载代码（任意代码执行风险）。

    覆盖 python -c/-ic/stdin、node -e/--eval=…/-p/--print、node -r/--import 等。
    `python -m pytest -c config` 中 -c 归属模块，不拒绝。
    """
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    return has_dangerous_interpreter_invocation(argv)


def _command_metadata(
    *,
    cwd: str,
    argv: list[str] | None = None,
    exit_code: int | None = None,
    duration_ms: int = 0,
    truncated: bool = False,
    stdout_chars: int = 0,
    stderr_chars: int = 0,
    error_code: str = "",
    **extra: Any,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "cwd": cwd,
        "argv": list(argv or []),
        "exit_code": exit_code,
        "duration_ms": max(0, duration_ms),
        "truncated": truncated,
        "stdout_chars": max(0, stdout_chars),
        "stderr_chars": max(0, stderr_chars),
    }
    if error_code:
        metadata["error_code"] = error_code
    metadata.update(extra)
    return metadata


def _truncate_output(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    suffix = f"\n...（输出已截断，原始 {len(value)} 字符）"
    keep = max(0, limit - len(suffix))
    return value[:keep] + suffix, True


def _package_manager(root: Path) -> str:
    if (root / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (root / "yarn.lock").is_file():
        return "yarn"
    return "npm"


def _script_argv(manager: str, name: str) -> list[str]:
    if manager == "npm":
        return ["npm", "test"] if name == "test" else ["npm", "run", name]
    if manager == "yarn":
        return ["yarn", name]
    return [manager, name]


def _script_purpose(name: str) -> str:
    normalized = name.casefold()
    if normalized in {"typecheck", "type-check", "check:types", "tsc"}:
        return "typecheck"
    if normalized in {"lint", "check", "quality"}:
        return "lint"
    if "e2e" in normalized or "integration" in normalized:
        return "integration"
    if "smoke" in normalized:
        return "smoke"
    if "test" in normalized:
        return "test"
    if "build" in normalized:
        return "build"
    return "other"


def _load_package_json(root: Path) -> dict[str, Any]:
    path = root / "package.json"
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    return data if isinstance(data, dict) else {}


def _package_dependencies(package: dict[str, Any]) -> dict[str, Any]:
    combined: dict[str, Any] = {}
    for field in ("dependencies", "devDependencies"):
        value = package.get(field)
        if isinstance(value, dict):
            combined.update(value)
    return combined


def _script_availability(
    root: Path, package: dict[str, Any], script: str
) -> tuple[bool, str]:
    executable = script.strip().split(maxsplit=1)[0].casefold() if script.strip() else ""
    package_by_executable = {
        "eslint": "eslint",
        "jest": "jest",
        "playwright": "@playwright/test",
        "tsc": "typescript",
        "vite": "vite",
        "vitest": "vitest",
    }
    dependency = package_by_executable.get(executable)
    if not dependency:
        return True, ""
    dependencies = _package_dependencies(package)
    local_bin = root / "node_modules" / ".bin" / executable
    if dependency in dependencies or local_bin.exists() or local_bin.with_suffix(".cmd").exists():
        return True, ""
    return False, f"脚本引用 {executable}，但 package.json 未声明 {dependency} 依赖"


def _supports_vite_temporary_output(root: Path, command: str) -> bool:
    if "build" not in command.casefold():
        return False
    try:
        package = _load_package_json(root)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    scripts = package.get("scripts") or {}
    build_script = str(scripts.get("build", "")) if isinstance(scripts, dict) else ""
    dependencies = _package_dependencies(package)
    return "vite build" in build_script.casefold() or "vite" in dependencies


@tool_registry.register(
    name="discover_project_commands",
    description="读取项目配置并返回实际存在的构建、检查和测试命令，不执行命令",
    params={
        "path": {
            "type": "string",
            "description": "项目目录的相对或绝对路径",
            "default": ".",
        }
    },
    category="read",
)
def discover_project_commands(path: str = ".", base_dir: str = ".") -> ToolResult:
    try:
        root = _resolve_path(path, base_dir)
        if not root.exists():
            return ToolResult(
                success=False,
                error=f"项目目录不存在：{path}",
                metadata={"error_code": "cwd_not_found", "cwd": str(root)},
            )
        if not root.is_dir():
            return ToolResult(
                success=False,
                error=f"不是项目目录：{path}",
                metadata={"error_code": "cwd_not_directory", "cwd": str(root)},
            )

        commands: list[dict[str, Any]] = []
        diagnostics: list[str] = []
        try:
            package = _load_package_json(root)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return ToolResult(
                success=False,
                error=f"package.json 无法解析：{type(exc).__name__}",
                metadata={"error_code": "package_json_invalid", "cwd": str(root)},
            )
        scripts = package.get("scripts") or {}
        if isinstance(scripts, dict):
            manager = _package_manager(root)
            for name, script in list(scripts.items())[:40]:
                if not isinstance(name, str) or not isinstance(script, str):
                    continue
                purpose = _script_purpose(name)
                available, availability_note = _script_availability(
                    root, package, script
                )
                argv = _script_argv(manager, name)
                command_text = " ".join(argv)
                commands.append(
                    {
                        "name": name,
                        "purpose": purpose,
                        "command": command_text,
                        "argv": argv,
                        "cwd": str(root),
                        "run": {"command": command_text, "cwd": str(root)},
                        "source": "package.json",
                        "available": available,
                        "diagnostic": availability_note,
                        "supports_temporary_output": (
                            purpose == "build" and "vite build" in script.casefold()
                        ),
                    }
                )
                if availability_note:
                    diagnostics.append(f"{name}: {availability_note}")

        pyproject_text = ""
        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            try:
                pyproject_text = pyproject.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                pass
        has_python_tests = (
            (root / "tests").is_dir()
            or (root / "pytest.ini").is_file()
            or "[tool.pytest" in pyproject_text.casefold()
        )
        if has_python_tests:
            pytest_command = "python -m pytest -q"
            commands.append(
                {
                    "name": "pytest",
                    "purpose": "test",
                    "command": pytest_command,
                    "argv": ["python", "-m", "pytest", "-q"],
                    "cwd": str(root),
                    "run": {"command": pytest_command, "cwd": str(root)},
                    "source": "python-project",
                    "available": True,
                    "diagnostic": "",
                    "supports_temporary_output": False,
                }
            )
        if not commands:
            diagnostics.append("未发现 package.json scripts 或 Python 测试入口")

        purposes = {
            item["purpose"] for item in commands if item.get("available", True)
        }
        suggested = next(
            (
                item["run"]
                for item in commands
                if item.get("available", True)
                and item.get("purpose") in {"test", "lint", "typecheck"}
                and item.get("run")
            ),
            None,
        )
        payload = {
            "project_root": str(root),
            "commands": commands,
            "recommended_order": [item for item in _PURPOSE_ORDER if item in purposes],
            "suggested_run": suggested,
            "diagnostics": diagnostics,
            "usage": (
                "把 suggested_run 或任一 commands[].run 交给 run_command；"
                "不要改用 bash -c、管道或 cd &&。"
            ),
        }
        return ToolResult(
            success=True,
            output=json.dumps(payload, ensure_ascii=False, indent=2),
            metadata={
                "cwd": str(root),
                "command_count": len(commands),
                "source_files": [
                    name
                    for name in ("package.json", "pyproject.toml", "pytest.ini")
                    if (root / name).is_file()
                ],
            },
        )
    except Exception as exc:
        return ToolResult(success=False, error=str(exc))


@tool_registry.register(
    name="run_command",
    description="使用结构化 cwd 在指定目录执行一条白名单命令；禁止 cd、管道和重定向",
    params={
        "command": {"type": "string", "description": "要执行的单条命令"},
        "cwd": {
            "type": "string",
            "description": "相对 base_dir 或绝对工作目录",
            "default": ".",
        },
        "temporary_output": {
            "type": "boolean",
            "description": "Vite build 使用自动清理的临时输出目录",
            "default": False,
        },
    },
    category="execute",
)
def run_command(
    command: str,
    base_dir: str = ".",
    allowed_prefixes: list[str] | None = None,
    timeout: int = 60,
    cwd: str = ".",
    temporary_output: bool = False,
    max_output_chars: int = 12000,
) -> ToolResult:
    """在结构化 cwd 下执行单条命令并返回可审计轨迹。"""
    started = time.perf_counter()
    try:
        command = command.strip()
        if not command:
            return ToolResult(
                success=False,
                error="命令不能为空",
                metadata=_command_metadata(cwd=cwd, error_code="empty_command"),
            )
        inline = _INLINE_CD.match(command)
        if inline:
            inline_cwd = next(
                item.strip() for item in inline.groups()[:3] if item and item.strip()
            )
            corrected = inline.group(4).strip()
            return ToolResult(
                success=False,
                error="不要使用 cd && 拼接目录；请把目录放入 run_command 的 cwd 参数后重试一次。",
                metadata=_command_metadata(
                    cwd=cwd,
                    error_code="inline_cwd",
                    suggested_params={"command": corrected, "cwd": inline_cwd},
                ),
            )
        if _DENIED_GIT_MUTATIONS.match(command):
            return ToolResult(
                success=False,
                error=(
                    "run_command 禁止 git push/reset/checkout/commit。"
                    "查看状态用 git_status/git_diff/git_log；提交用 git_commit。"
                ),
                metadata=_command_metadata(
                    cwd=cwd,
                    error_code="git_mutation_denied",
                    suggested_tool="git_commit",
                    suggested_action="使用 git_commit，且不要 push",
                ),
            )
        if _contains_shell_syntax(command):
            return ToolResult(
                success=False,
                error=(
                    "run_command 只接受单条命令，不支持管道、重定向、命令连接或后台执行。"
                    "请改 command 或 cwd 参数，不要改用 bash -c。"
                ),
                metadata=_command_metadata(
                    cwd=cwd,
                    error_code="shell_syntax",
                    suggested_action="使用结构化 cwd，并分别执行 discover_project_commands 返回的单条命令；不要发明 bash -c",
                ),
            )
        # Inline/preload interpreter checks run before the allowlist so that
        # dangerous forms get a stable error_code even when prefixes match.
        if _has_inline_interpreter_code(command):
            return ToolResult(
                success=False,
                error=(
                    "禁止解释器内联代码（python -c / node -e 等）；"
                    "请把代码写入项目内脚本后再运行，不要重复原调用。"
                ),
                metadata=_command_metadata(
                    cwd=cwd,
                    error_code="inline_interpreter_code",
                    suggested_action="先用 write_file 写入脚本文件，再 run_command 执行该脚本",
                ),
            )
        if not _is_command_allowed(
            command, allowed_prefixes, cwd=cwd, base_dir=base_dir
        ):
            preview = ", ".join(
                (allowed_prefixes or load_command_allowlist())[:8]
            )
            return ToolResult(
                success=False,
                error=(
                    f"命令不在白名单内：{command}。先调用 discover_project_commands，"
                    "使用返回的 command 与 cwd；或在 config/workers.yaml 的 "
                    "command_allowlist.extra_prefixes 追加前缀。"
                    f"当前前缀示例：{preview}。不要改用 bash -c。"
                ),
                metadata=_command_metadata(
                    cwd=cwd,
                    error_code="command_not_allowed",
                    suggested_tool="discover_project_commands",
                    suggested_params={"path": cwd},
                    suggested_action="改 command/cwd 以匹配已发现脚本，不要发明 bash -c 或管道",
                    allowed_prefix_preview=preview,
                ),
            )

        base = _resolve_path(cwd, base_dir)
        if not base.exists():
            return ToolResult(
                success=False,
                error=f"命令工作目录不存在：{cwd}",
                metadata=_command_metadata(
                    cwd=str(base),
                    error_code="cwd_not_found",
                    suggested_tool="discover_project_commands",
                    suggested_params={"path": cwd},
                ),
            )
        if not base.is_dir():
            return ToolResult(
                success=False,
                error=f"命令工作目录不是目录：{cwd}",
                metadata=_command_metadata(
                    cwd=str(base), error_code="cwd_not_directory"
                ),
            )
        args = shlex.split(command)
        temp_path = ""
        temp_cleaned = False
        if temporary_output:
            if not _supports_vite_temporary_output(base, command):
                return ToolResult(
                    success=False,
                    error="temporary_output 目前只支持 package.json 中的 Vite build。",
                    metadata=_command_metadata(
                        cwd=str(base),
                        argv=args,
                        error_code="temporary_output_unsupported",
                    ),
                )
            with tempfile.TemporaryDirectory(prefix="mao-vite-build-") as temp_dir:
                temp_path = temp_dir
                if args[0].casefold() in {"npm", "pnpm"}:
                    args = [*args, "--", "--outDir", temp_dir]
                else:
                    args = [*args, "--outDir", temp_dir]
                result, args = _run_subprocess_portable(
                    args,
                    cwd=str(base),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    shell=False,
                )
            temp_cleaned = not Path(temp_path).exists()
        else:
            result, args = _run_subprocess_portable(
                args,
                cwd=str(base),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        output = stdout
        if stderr:
            output += "\n[stderr]\n" + stderr
        output, truncated = _truncate_output(output.strip(), max(1, max_output_chars))
        duration_ms = int((time.perf_counter() - started) * 1000)

        return ToolResult(
            success=result.returncode == 0,
            output=output,
            error=f"退出码：{result.returncode}" if result.returncode != 0 else "",
            metadata=_command_metadata(
                cwd=str(base),
                argv=args,
                exit_code=result.returncode,
                duration_ms=duration_ms,
                truncated=truncated,
                stdout_chars=len(stdout),
                stderr_chars=len(stderr),
                temporary_output=temporary_output,
                temporary_output_path=temp_path,
                temporary_output_cleaned=temp_cleaned,
            ),
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            success=False,
            error=f"命令执行超时（{timeout} 秒）",
            metadata=_command_metadata(
                cwd=cwd,
                duration_ms=int((time.perf_counter() - started) * 1000),
                error_code="timeout",
                timeout_seconds=timeout,
            ),
        )
    except FileNotFoundError:
        return ToolResult(
            success=False,
            error="命令可执行文件不存在；请检查依赖是否安装，并先调用 discover_project_commands。",
            metadata=_command_metadata(
                cwd=cwd,
                error_code="executable_not_found",
                suggested_tool="discover_project_commands",
                suggested_params={"path": cwd},
            ),
        )
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def _run_subprocess_portable(
    args: list[str], **kwargs: Any
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Resolve Windows .CMD launchers only after direct argv execution fails."""
    try:
        return subprocess.run(args, **kwargs), args
    except FileNotFoundError:
        resolved = shutil.which(args[0])
        if not resolved:
            raise
        effective = [resolved, *args[1:]]
        return subprocess.run(effective, **kwargs), effective


@tool_registry.register(
    name="frontend_smoke",
    description=(
        "启动受控前端 server，并用 Playwright 检查登录、路由、数据、控制台错误及桌面/移动布局"
    ),
    params={
        "project_root": {"type": "string", "description": "前端项目根目录"},
        "contract": {"type": "object", "description": "frontend_contract.smoke 对象"},
        "artifact_dir": {
            "type": "string",
            "description": "失败截图和诊断的隔离输出目录",
            "default": "smoke-artifacts",
        },
    },
    category="execute",
)
def frontend_smoke(
    project_root: str,
    contract: dict[str, Any],
    base_dir: str = ".",
    artifact_dir: str = "smoke-artifacts",
) -> ToolResult:
    """Validate and execute one bounded frontend runtime contract."""
    # Lazy import avoids worker_tools <-> engineering package circular import.
    from src.core.engineering.frontend_smoke import (
        run_frontend_smoke as execute_frontend_smoke,
    )

    try:
        parsed = FrontendSmokeContract(**contract)
    except ValidationError as exc:
        return ToolResult(
            success=False,
            error="frontend smoke 合同无效",
            metadata={
                "check_type": "smoke",
                "error_code": "smoke_contract_invalid",
                "validation_errors": len(exc.errors()),
            },
        )
    root = _resolve_path(project_root, base_dir)
    artifacts = _resolve_path(artifact_dir, base_dir)
    return execute_frontend_smoke(root, parsed, artifacts)


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
        if is_sensitive_path(target):
            return ToolResult(
                success=False,
                error=sensitive_path_error(path),
                metadata={"error_code": "sensitive_path", "path": str(target)},
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return ToolResult(success=True, output=f"已写入文件：{path}")
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def _edit_file_match_hint(
    path: str, content: str, old_string: str, occurrences: int
) -> str:
    """Give line-level context so the model can retry edit_file without blind rewrite."""
    lines = content.splitlines()
    if occurrences == 0:
        preview = "\n".join(
            f"{index + 1}: {line}" for index, line in enumerate(lines[:8])
        ) or "(空文件)"
        return (
            f"未在文件中找到指定文本：{path}。请提供文件中真实存在的片段，"
            f"不要整文件盲写。文件开头预览：\n{preview}"
        )
    hits: list[str] = []
    cursor = 0
    while len(hits) < 5:
        index = content.find(old_string, cursor)
        if index < 0:
            break
        line_no = content.count("\n", 0, index) + 1
        before = lines[line_no - 2] if line_no >= 2 else ""
        current = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
        after = lines[line_no] if line_no < len(lines) else ""
        snippet = []
        if before:
            snippet.append(f"{line_no - 1}: {before}")
        snippet.append(f"{line_no}: {current}")
        if after:
            snippet.append(f"{line_no + 1}: {after}")
        hits.append("\n".join(snippet))
        cursor = index + max(len(old_string), 1)
    shown = "\n---\n".join(hits)
    return (
        f"指定文本在文件中出现 {occurrences} 次，不唯一；请提供更长上下文以精确定位，"
        f"不要整文件盲写。匹配位置（最多 5 处）：\n{shown}"
    )


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
        if is_sensitive_path(target):
            return ToolResult(
                success=False,
                error=sensitive_path_error(path),
                metadata={"error_code": "sensitive_path", "path": str(target)},
            )
        if not target.exists():
            return ToolResult(success=False, error=f"文件不存在：{path}")
        if not target.is_file():
            return ToolResult(success=False, error=f"不是文件：{path}")

        with open(target, "r", encoding="utf-8") as f:
            content = f.read()

        occurrences = content.count(old_string)
        if occurrences == 0:
            return ToolResult(
                success=False,
                error=_edit_file_match_hint(path, content, old_string, occurrences),
            )
        if occurrences > 1:
            return ToolResult(
                success=False,
                error=_edit_file_match_hint(path, content, old_string, occurrences),
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
    runtime_context: dict[str, Any] | None = None,
) -> ToolResult:
    """统一分发工具调用（向后兼容入口）"""
    return tool_registry.execute(
        tool_name,
        params,
        base_dir,
        allowed_prefixes,
        runtime_context,
    )

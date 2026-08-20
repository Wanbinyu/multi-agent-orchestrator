"""Read-only Git inspection plus a constrained commit helper.

These tools never push, reset, amend, or rewrite existing history.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from src.tools.paths import resolve_path as _resolve_path
from src.tools.registry import tool_registry
from src.tools.safety_guards import is_sensitive_path, sensitive_path_error
from src.tools.tool_result import ToolResult

_GIT_TIMEOUT = 20
_DIFF_LIMIT = 12000


def _run_git(args: list[str], cwd: Path, timeout: int = _GIT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )


def _repo_dir(path: str, base_dir: str) -> tuple[Path | None, ToolResult | None]:
    try:
        target = _resolve_path(path, base_dir)
    except Exception as exc:
        return None, ToolResult(success=False, error=str(exc))
    if not target.exists():
        return None, ToolResult(success=False, error=f"目录不存在：{path}")
    if not target.is_dir():
        return None, ToolResult(success=False, error=f"不是目录：{path}")
    try:
        result = _run_git(["rev-parse", "--show-toplevel"], target, timeout=10)
    except FileNotFoundError:
        return None, ToolResult(
            success=False,
            error="未找到 git 可执行文件",
            metadata={"error_code": "git_missing"},
        )
    except subprocess.TimeoutExpired:
        return None, ToolResult(success=False, error="Git 仓库探测超时")
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        return None, ToolResult(
            success=False,
            error=output or "当前目录不是 Git 仓库",
            metadata={"error_code": "not_a_git_repo", "cwd": str(target)},
        )
    root = Path(result.stdout.strip() or str(target))
    return root, None


def _combine_output(result: subprocess.CompletedProcess[str]) -> str:
    parts = [part.strip() for part in (result.stdout, result.stderr) if part and part.strip()]
    return "\n".join(parts)


def _normalize_files(files: Any) -> list[str]:
    if files is None or files == "":
        return []
    if isinstance(files, str):
        text = files.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        return [part.strip() for part in text.replace(",", " ").split() if part.strip()]
    if isinstance(files, (list, tuple)):
        return [str(item).strip() for item in files if str(item).strip()]
    return [str(files).strip()] if str(files).strip() else []


@tool_registry.register(
    name="git_diff",
    description="只读查看工作区或暂存区 diff；可限定单个文件。不提交、不推送。",
    params={
        "path": {
            "type": "string",
            "description": "仓库目录，默认当前目录",
            "default": ".",
        },
        "file": {
            "type": "string",
            "description": "可选，只看该相对路径的 diff",
            "default": "",
        },
        "staged": {
            "type": "boolean",
            "description": "为 true 时查看暂存区（git diff --cached）",
            "default": False,
        },
    },
    category="read",
)
def git_diff(
    path: str = ".",
    file: str = "",
    staged: bool = False,
    base_dir: str = ".",
) -> ToolResult:
    root, error = _repo_dir(path, base_dir)
    if error is not None or root is None:
        return error or ToolResult(success=False, error="无法定位 Git 仓库")
    args = ["diff", "--no-color"]
    if staged:
        args.append("--cached")
    target_file = str(file or "").strip()
    if target_file:
        args.extend(["--", target_file])
    try:
        stat = _run_git([*args, "--stat"], root)
        patch = _run_git(args, root)
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, error="Git diff 超时")
    except Exception as exc:
        return ToolResult(success=False, error=str(exc))
    if stat.returncode != 0:
        return ToolResult(
            success=False,
            error=_combine_output(stat) or "git diff 失败",
            metadata={"error_code": "git_diff_failed", "cwd": str(root)},
        )
    stat_text = (stat.stdout or "").strip() or "（无差异）"
    patch_text = (patch.stdout or "").strip()
    if len(patch_text) > _DIFF_LIMIT:
        patch_text = patch_text[:_DIFF_LIMIT] + f"\n...（diff 已截断，原始 {len(patch.stdout or '')} 字符）"
    output = stat_text if not patch_text else f"{stat_text}\n\n{patch_text}"
    return ToolResult(
        success=True,
        output=output,
        metadata={
            "cwd": str(root),
            "staged": bool(staged),
            "file": target_file,
            "truncated": len(patch.stdout or "") > _DIFF_LIMIT,
        },
    )


@tool_registry.register(
    name="git_log",
    description="只读查看最近提交摘要（oneline）。不改历史、不推送。",
    params={
        "path": {
            "type": "string",
            "description": "仓库目录，默认当前目录",
            "default": ".",
        },
        "max_count": {
            "type": "integer",
            "description": "最多显示多少条，默认 8，最大 20",
            "default": 8,
        },
    },
    category="read",
)
def git_log(path: str = ".", max_count: int = 8, base_dir: str = ".") -> ToolResult:
    root, error = _repo_dir(path, base_dir)
    if error is not None or root is None:
        return error or ToolResult(success=False, error="无法定位 Git 仓库")
    try:
        count = int(max_count)
    except (TypeError, ValueError):
        count = 8
    count = max(1, min(count, 20))
    try:
        result = _run_git(
            ["log", "-n", str(count), "--oneline", "--decorate"],
            root,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, error="Git log 超时")
    except Exception as exc:
        return ToolResult(success=False, error=str(exc))
    if result.returncode != 0:
        return ToolResult(
            success=False,
            error=_combine_output(result) or "git log 失败",
            metadata={"error_code": "git_log_failed", "cwd": str(root)},
        )
    output = (result.stdout or "").strip() or "（尚无提交）"
    return ToolResult(
        success=True,
        output=output,
        metadata={"cwd": str(root), "max_count": count},
    )


@tool_registry.register(
    name="git_commit",
    description=(
        "仅提交已暂存文件或明确列出的路径。必须提供 message。"
        "不会 push、reset、amend，也不会 git add -A。"
    ),
    params={
        "path": {
            "type": "string",
            "description": "仓库目录，默认当前目录",
            "default": ".",
        },
        "message": {"type": "string", "description": "提交说明，必填"},
        "files": {
            "type": "array",
            "description": "要加入本次提交的相对路径列表；与 staged_only 二选一",
            "default": [],
        },
        "staged_only": {
            "type": "boolean",
            "description": "为 true 时只提交当前暂存区，不再 git add",
            "default": False,
        },
    },
    category="write",
)
def git_commit(
    path: str = ".",
    message: str = "",
    files: Any = None,
    staged_only: bool = False,
    base_dir: str = ".",
) -> ToolResult:
    root, error = _repo_dir(path, base_dir)
    if error is not None or root is None:
        return error or ToolResult(success=False, error="无法定位 Git 仓库")
    message = str(message or "").strip()
    if not message:
        return ToolResult(
            success=False,
            error="git_commit 必须提供非空 message",
            metadata={"error_code": "empty_commit_message"},
        )
    selected = _normalize_files(files)
    if not selected and not staged_only:
        return ToolResult(
            success=False,
            error="必须提供 files 或 staged_only=true；不会执行 git add -A。",
            metadata={"error_code": "commit_paths_required"},
        )
    if selected and staged_only:
        return ToolResult(
            success=False,
            error="files 与 staged_only 不能同时使用",
            metadata={"error_code": "commit_paths_conflict"},
        )

    committed: list[str] = []
    if selected:
        for raw in selected:
            try:
                target = _resolve_path(raw, str(root))
            except Exception as exc:
                return ToolResult(success=False, error=str(exc))
            if is_sensitive_path(target):
                return ToolResult(
                    success=False,
                    error=sensitive_path_error(raw),
                    metadata={"error_code": "sensitive_path", "path": str(target)},
                )
            try:
                target.relative_to(root)
            except ValueError:
                return ToolResult(
                    success=False,
                    error=f"提交路径越出仓库：{raw}",
                    metadata={"error_code": "path_outside_repo", "path": raw},
                )
            committed.append(raw)
        add = _run_git(["add", "--", *committed], root)
        if add.returncode != 0:
            return ToolResult(
                success=False,
                error=_combine_output(add) or "git add 失败",
                metadata={"error_code": "git_add_failed", "files": committed},
            )
    else:
        staged = _run_git(["diff", "--cached", "--name-only"], root)
        if staged.returncode != 0:
            return ToolResult(
                success=False,
                error=_combine_output(staged) or "无法读取暂存区",
                metadata={"error_code": "git_staged_list_failed"},
            )
        committed = [line.strip() for line in (staged.stdout or "").splitlines() if line.strip()]
        if not committed:
            return ToolResult(
                success=False,
                error="暂存区为空，没有可提交的文件",
                metadata={"error_code": "empty_staged"},
            )

    commit_args = ["commit", "-m", message]
    if selected:
        commit_args.extend(["--", *committed])
    try:
        result = _run_git(commit_args, root)
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, error="Git commit 超时")
    except Exception as exc:
        return ToolResult(success=False, error=str(exc))
    if result.returncode != 0:
        return ToolResult(
            success=False,
            error=_combine_output(result) or "git commit 失败",
            metadata={
                "error_code": "git_commit_failed",
                "files": committed,
                "message": message,
            },
        )
    sha = ""
    try:
        rev = _run_git(["rev-parse", "--short", "HEAD"], root, timeout=10)
        if rev.returncode == 0:
            sha = (rev.stdout or "").strip()
    except Exception:
        sha = ""
    return ToolResult(
        success=True,
        output=f"已提交 {len(committed)} 个文件" + (f"（{sha}）" if sha else ""),
        metadata={
            "cwd": str(root),
            "message": message,
            "files": committed,
            "commit_sha": sha,
            "pushed": False,
        },
    )

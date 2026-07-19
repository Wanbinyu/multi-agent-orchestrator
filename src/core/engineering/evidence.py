"""把真实工具结果转换为 Evidence，并跟踪项目侦察覆盖。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.core.engineering.models import Evidence, EvidenceKind, RunJournal
from src.tools.tool_result import ToolResult


def file_mutation_metadata(
    tool_name: str, params: dict[str, Any], base_dir: str | Path
) -> dict[str, Any]:
    """在写工具执行前捕获文件与父目录状态，供动态风险判断。"""
    if tool_name not in {"write_file", "edit_file"}:
        return {}
    raw_path = str(params.get("path", "")).strip()
    if not raw_path:
        return {}
    try:
        target = Path(raw_path).expanduser()
        if not target.is_absolute():
            target = Path(base_dir) / target
        target = target.resolve(strict=False)
        resolved_base = Path(base_dir).expanduser().resolve(strict=False)
        return {
            "resolved_path": str(target),
            "file_existed_before": target.exists(),
            "parent_existed_before": target.parent.exists(),
            "created_new_directory": (
                tool_name == "write_file"
                and target.parent != resolved_base
                and not target.parent.exists()
            ),
        }
    except (OSError, RuntimeError, ValueError):
        return {}


_EXCERPT_LIMIT = 800
_DOC_NAMES = {"readme", "agents.md", "contributing.md", "architecture.md"}
_DEPENDENCY_NAMES = {
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pom.xml",
    "build.gradle",
    "go.mod",
    "cargo.toml",
}
_ENTRYPOINT_NAMES = {
    "main.py",
    "run.py",
    "app.py",
    "index.js",
    "index.ts",
    "main.js",
    "main.ts",
    "main.java",
}


def _excerpt(result: ToolResult) -> str:
    if result.success:
        text = result.output.strip()
    else:
        text = "\n".join(
            part for part in (result.output.strip(), result.error.strip()) if part
        )
    if len(text) <= _EXCERPT_LIMIT:
        return text
    return text[:_EXCERPT_LIMIT] + "...（证据摘录已截断）"


def _path(params: dict[str, Any]) -> str:
    value = (
        params.get("path")
        or params.get("root")
        or params.get("project_root")
        or ""
    )
    return str(value)


def is_test_command(command: str) -> bool:
    normalized = command.strip().lower()
    return any(
        marker in normalized
        for marker in ("pytest", "unittest", "npm test", "npm run test", "pnpm test")
    )


class ToolEvidenceRecorder:
    """只接受 ToolResult，不从模型正文构造证据。"""

    def record(
        self,
        journal: RunJournal,
        tool_name: str,
        params: dict[str, Any],
        result: ToolResult,
        *,
        cached: bool = False,
        skipped: bool = False,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        path = _path(params)
        command = str(params.get("command", ""))
        kind, claim = self._classify(tool_name, path, command, result, skipped)
        evidence = Evidence(
            source=source or f"tool:{tool_name}",
            claim=claim,
            excerpt=_excerpt(result),
            confidence=1.0,
            kind=kind,
            tool_name=tool_name,
            path=path,
            command=command,
            success=result.success,
            cached=cached,
            metadata={
                "skipped": skipped,
                **(result.metadata or {}),
                **(metadata or {}),
            },
        )
        _, added = journal.add_evidence(evidence)
        reconnaissance_changed = self._update_reconnaissance(
            journal, tool_name, path, command, result, cached=cached, skipped=skipped
        )
        return added or reconnaissance_changed

    @staticmethod
    def _classify(
        tool_name: str,
        path: str,
        command: str,
        result: ToolResult,
        skipped: bool,
    ) -> tuple[EvidenceKind, str]:
        if skipped:
            return "runtime", f"{tool_name} 因工程边界被跳过"
        if tool_name in {"project_tree", "list_dir"}:
            action = "已获取" if result.success else "获取失败"
            return "structure", f"{action}项目结构：{path or '.'}"
        if tool_name == "git_status":
            action = "已检查" if result.success else "检查失败"
            return "git", f"{action} Git 工作区状态：{path or '.'}"
        if tool_name == "read_file":
            action = "已读取" if result.success else "读取失败"
            return "file", f"{action}文件：{path}"
        if tool_name in {"glob_files", "grep_content"}:
            action = "已完成" if result.success else "执行失败"
            return "search", f"{action}代码检索：{path or '.'}"
        if (
            tool_name == "run_command"
            and result.metadata.get("error_code")
            and result.metadata.get("exit_code") is None
        ):
            return "runtime", f"命令未执行：{result.metadata['error_code']}"
        if tool_name == "run_command" and is_test_command(command):
            outcome = "通过" if result.success else "失败"
            return "test", f"测试命令执行{outcome}：{command}"
        if tool_name == "frontend_smoke":
            outcome = "通过" if result.success else "失败"
            return "test", f"前端浏览器 smoke {outcome}"
        if tool_name in {"write_file", "edit_file"}:
            action = "已修改" if result.success else "修改失败"
            return "change", f"{action}文件：{path}"
        if tool_name in {"web_search", "fetch_url"}:
            action = "已获取" if result.success else "获取失败"
            return "external", f"{action}外部信息：{tool_name}"
        outcome = "成功" if result.success else "失败"
        return "runtime", f"工具 {tool_name} 执行{outcome}"

    @staticmethod
    def _update_reconnaissance(
        journal: RunJournal,
        tool_name: str,
        path: str,
        command: str,
        result: ToolResult,
        *,
        cached: bool,
        skipped: bool,
    ) -> bool:
        recon = journal.reconnaissance
        if cached:
            return False
        if not recon.root and tool_name in {"project_tree", "list_dir", "git_status"}:
            recon.root = path or "."
        if skipped:
            recon.mark_skipped(path or tool_name)
            return True
        recon.mark_tool_call()
        if not result.success:
            return True
        if tool_name in {"project_tree", "list_dir"}:
            recon.observe("structure")
            return True
        if tool_name == "git_status":
            recon.observe("git")
            return True
        if tool_name == "run_command" and is_test_command(command):
            recon.observe("tests")
            return True
        if tool_name != "read_file":
            return True

        normalized = path.replace("\\", "/")
        name = Path(normalized).name.casefold()
        lower_path = normalized.casefold()
        recon.observe("file", path=path)
        if name in _DOC_NAMES or name.startswith("readme") or "/docs/" in lower_path:
            recon.observe("docs")
        if name in _DEPENDENCY_NAMES or name.startswith("requirements"):
            recon.observe("dependencies")
        if name in _ENTRYPOINT_NAMES or name in {"__main__.py", "manage.py"}:
            recon.observe("entrypoints")
        if "/tests/" in lower_path or name.startswith("test_") or name.endswith("_test.py"):
            recon.observe("tests")
        return True

"""工具调用钩子（Hooks）

在 ToolRegistry.execute() 前后注入钩子，用于审计日志、参数改写、结果过滤、
安全拦截等扩展，无需改动工具本身或 Agent。

钩子约定：
- pre_hook(tool_name, params) -> dict | None
    返回 dict 则替换 params；返回 None 保持原 params。
    抛 HookAbort 则阻止执行，返回错误结果；抛其他异常则记录但不中断。
- post_hook(tool_name, params, result) -> ToolResult | None
    返回 ToolResult 则替换 result；返回 None 保持原 result。
"""
from __future__ import annotations

import importlib
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml

from src.tools.tool_result import ToolResult
from src.tools.extension_diagnostics import (
    ExtensionDiagnostic,
    MAX_EXTENSION_DIAGNOSTICS,
    make_extension_diagnostic,
)


class HookAbort(Exception):
    """pre-hook 抛出以阻止工具执行"""


PreToolHook = Callable[[str, dict[str, Any]], "dict[str, Any] | None"]
PostToolHook = Callable[[str, dict[str, Any], ToolResult], "ToolResult | None"]


class HookRegistry:
    """钩子注册表"""

    def __init__(self) -> None:
        self._pre: list[PreToolHook] = []
        self._post: list[PostToolHook] = []

    def add_pre(self, fn: PreToolHook) -> None:
        self._pre.append(fn)

    def add_post(self, fn: PostToolHook) -> None:
        self._post.append(fn)

    def clear(self) -> None:
        self._pre.clear()
        self._post.clear()

    def run_pre(
        self, tool_name: str, params: dict[str, Any]
    ) -> tuple[dict[str, Any], ToolResult | None]:
        """返回 (可能修改后的 params, 拦截结果或 None)"""
        for hook in self._pre:
            try:
                ret = hook(tool_name, params)
                if isinstance(ret, dict):
                    params = ret
            except HookAbort as e:
                return params, ToolResult(
                    success=False, error=f"工具被钩子拒绝：{e}"
                )
            except Exception:
                # 钩子自身出错不中断主流程
                pass
        return params, None

    def run_post(
        self, tool_name: str, params: dict[str, Any], result: ToolResult
    ) -> ToolResult:
        for hook in self._post:
            try:
                ret = hook(tool_name, params, result)
                if isinstance(ret, ToolResult):
                    result = ret
            except Exception:
                pass
        return result


# ---------- 内置审计日志钩子 ----------


class AuditLogHook:
    """把每次工具调用追加写入日志文件"""

    def __init__(self, log_path: str = "logs/tool_audit.log") -> None:
        self.log_path = Path(log_path)
        self._lock = threading.Lock()

    def _append(self, line: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def pre(self, tool_name: str, params: dict[str, Any]) -> None:
        self._append(f"[{datetime.now().isoformat()}] CALL {tool_name} {params}")

    def post(self, tool_name: str, params: dict[str, Any], result: ToolResult) -> None:
        status = "OK" if result.success else "ERR"
        self._append(
            f"[{datetime.now().isoformat()}] {status} {tool_name} "
            f"-> {(result.output or result.error)[:200]!r}"
        )


# 模块级默认审计钩子实例，供 config/hooks.yaml 通过 dotted path 加载
_default_audit = AuditLogHook()


def audit_pre(tool_name: str, params: dict[str, Any]) -> None:
    """默认审计 pre 钩子（可经 config 加载）"""
    _default_audit.pre(tool_name, params)
    return None


def audit_post(tool_name: str, params: dict[str, Any], result: ToolResult) -> None:
    """默认审计 post 钩子（可经 config 加载）"""
    _default_audit.post(tool_name, params, result)
    return None


# ---------- 配置加载 ----------


def _import_callable(dotted: str) -> Callable[..., Any]:
    """从 'pkg.module.fn' 导入可调用对象"""
    if "." not in dotted:
        raise ValueError(f"无效的钩子路径：{dotted}")
    module_path, _, fn_name = dotted.rpartition(".")
    module = importlib.import_module(module_path)
    fn = getattr(module, fn_name)
    if not callable(fn):
        raise ValueError(f"{dotted} 不是可调用对象")
    return fn


def load_hooks_from_config(
    config_path: str | Path, registry: HookRegistry
) -> int:
    """从 config/hooks.yaml 加载钩子并注册，返回加载数量。

    配置格式：
        pre:
          - src.core.hooks:audit_pre
        post:
          - my_app.hooks:redact_post
    """
    path = Path(config_path)
    if not path.exists():
        return 0
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    count = 0
    for dotted in data.get("pre", []) or []:
        registry.add_pre(_import_callable(str(dotted)))
        count += 1
    for dotted in data.get("post", []) or []:
        registry.add_post(_import_callable(str(dotted)))
        count += 1
    return count


def load_hooks_from_config_detailed(
    config_path: str | Path, registry: HookRegistry
) -> tuple[int, list[ExtensionDiagnostic]]:
    """Load valid hooks independently and return bounded, redacted diagnostics."""
    path = Path(config_path)
    if not path.exists():
        return 0, []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:
        return 0, [
            make_extension_diagnostic(
                source="hooks",
                code="hook_config_error",
                message="Hooks 配置无法读取或解析",
                action="检查 hooks.yaml 的 YAML 格式和文件权限",
                config_path=path,
                error=exc,
            )
        ]

    if not isinstance(data, dict):
        return 0, [
            make_extension_diagnostic(
                source="hooks",
                code="hook_config_shape_error",
                message="Hooks 配置顶层必须是映射",
                action="使用 pre 和 post 列表组织 hooks.yaml",
                config_path=path,
            )
        ]

    count = 0
    diagnostics: list[ExtensionDiagnostic] = []
    for hook_type, register in (("pre", registry.add_pre), ("post", registry.add_post)):
        entries = data.get(hook_type, []) or []
        if not isinstance(entries, list):
            if len(diagnostics) < MAX_EXTENSION_DIAGNOSTICS:
                diagnostics.append(
                    make_extension_diagnostic(
                        source="hooks",
                        code="hook_list_error",
                        message=f"Hooks 的 {hook_type} 配置必须是列表",
                        action="将 Hook 路径写成 YAML 列表",
                        config_path=path,
                        entry=hook_type,
                    )
                )
            continue
        for index, dotted in enumerate(entries):
            try:
                register(_import_callable(str(dotted)))
                count += 1
            except Exception as exc:
                if len(diagnostics) < MAX_EXTENSION_DIAGNOSTICS:
                    diagnostics.append(
                        make_extension_diagnostic(
                            source="hooks",
                            code="hook_import_error",
                            message="Hook 无法导入，已跳过该条目",
                            action="检查 Hook 的模块和函数路径",
                            config_path=path,
                            entry=f"{hook_type}[{index}]",
                            error=exc,
                        )
                    )
    return count, diagnostics

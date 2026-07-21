"""统一工具注册表

提供装饰器/程序化注册、工具发现、Prompt 说明生成和统一执行入口。
支持通过 ToolSource 接入外部工具源（如 MCP），为未来扩展预留位置。
执行链路支持 Hooks（pre/post 钩子），见 src/core/hooks.py。
"""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

from src.core.hooks import HookRegistry
from src.tools.tool_result import ToolResult


@dataclass
class ToolSpec:
    """工具元数据"""

    name: str
    description: str
    params: dict[str, Any]
    callable: Callable[..., ToolResult]
    category: str = "read"  # read / write / execute / external / unsafe


@runtime_checkable
class ToolSource(Protocol):
    """外部工具源协议（MCP 等未来扩展的挂载点）。

    实现该协议的对象可通过 tool_registry.add_source() 注册，
    其工具会被纳入注册表的发现与执行链路。
    """

    def list_tools(self) -> list[ToolSpec]:
        """返回该来源提供的所有工具元数据（不含 callable 也应给出描述与参数）"""
        ...

    def execute(self, name: str, params: dict[str, Any]) -> ToolResult:
        """执行该来源的某个工具"""
        ...

    def shutdown(self) -> None:
        """Release background tasks, processes, and network connections."""
        ...


class ToolRegistry:
    """工具注册表：单例，按名称索引"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._sources: list[ToolSource] = []
        self.hooks = HookRegistry()

    def add_pre_hook(self, fn) -> None:
        """注册工具执行前钩子"""
        self.hooks.add_pre(fn)

    def add_post_hook(self, fn) -> None:
        """注册工具执行后钩子"""
        self.hooks.add_post(fn)

    def add_source(self, source: ToolSource) -> None:
        """注册一个外部工具源（如 MCP 适配器）。

        注册后，其工具会通过 list_tools() / get() / execute() 被发现与调用，
        优先级低于本地注册的同名工具。
        """
        self._sources.append(source)

    def shutdown_sources(self) -> None:
        """Best-effort cleanup for every registered external tool source."""
        sources, self._sources = self._sources, []
        for source in sources:
            shutdown = getattr(source, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception:
                    pass

    def unregister_tool(self, name: str) -> bool:
        """Remove a locally registered tool by name. Returns True if it existed.

        Used by the plugin manager to roll back a failed plugin load. Does not
        affect tools contributed by external ``ToolSource`` instances.
        """
        return self._tools.pop(name, None) is not None

    def remove_source(self, source: ToolSource) -> None:
        """Remove a specific external tool source without shutting it down.

        The caller is responsible for calling ``source.shutdown()`` if needed.
        """
        self._sources = [s for s in self._sources if s is not source]

    def register(
        self,
        name: str,
        description: str,
        params: dict[str, Any] | None = None,
        category: str = "read",
    ) -> Callable[[Callable[..., ToolResult]], Callable[..., ToolResult]]:
        """装饰器注册工具"""

        def decorator(fn: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
            self.register_function(
                fn,
                name=name,
                description=description,
                params=params or {},
                category=category,
            )
            return fn

        return decorator

    def register_function(
        self,
        fn: Callable[..., ToolResult],
        *,
        name: str,
        description: str,
        params: dict[str, Any] | None = None,
        category: str = "read",
    ) -> ToolSpec:
        """程序化注册工具"""
        spec = ToolSpec(
            name=name,
            description=description,
            params=params or {},
            callable=fn,
            category=category,
        )
        self._tools[name] = spec
        return spec

    def get(self, name: str) -> ToolSpec | None:
        if name in self._tools:
            return self._tools[name]
        for source in self._sources:
            for spec in source.list_tools():
                if spec.name == name:
                    return spec
        return None

    def list_tools(self) -> list[str]:
        names = list(self._tools.keys())
        seen = set(names)
        for source in self._sources:
            for spec in source.list_tools():
                if spec.name not in seen:
                    names.append(spec.name)
                    seen.add(spec.name)
        return names

    def build_instructions(self, tool_names: list[str] | None = None) -> str:
        """根据可用工具生成系统提示中的工具说明"""
        if tool_names is None:
            specs = list(self._tools.values())
            # 追加外部工具源的工具
            for source in self._sources:
                specs.extend(source.list_tools())
        else:
            specs = []
            for name in tool_names:
                spec = self.get(name)
                if spec:
                    specs.append(spec)

        if not specs:
            return ""

        lines = ["可用工具（必须以 Markdown 代码块形式调用，禁止调用原生 tool_use / function_call）：", ""]
        for idx, spec in enumerate(specs, start=1):
            lines.append(f"{idx}. {spec.name}：{spec.description}")
            example = self._build_example(spec.params)
            lines.append(f"```tool:{spec.name}")
            lines.append(json.dumps(example, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def build_tool_schemas(self, provider_type: str, tool_names: list[str] | None = None) -> list[dict[str, Any]]:
        """生成原生工具定义（供支持 tool_use 的模型使用）。

        - provider_type="anthropic": 返回 [{"name","description","input_schema"}]
        - provider_type="openai": 返回 [{"type":"function","function":{"name","description","parameters"}}]
        """
        if tool_names is None:
            specs = list(self._tools.values())
        else:
            specs = [self.get(n) for n in tool_names if self.get(n)]

        schemas: list[dict[str, Any]] = []
        for spec in specs:
            input_schema = self._build_input_schema(spec.params)
            if provider_type == "anthropic":
                schemas.append({
                    "name": spec.name,
                    "description": spec.description,
                    "input_schema": input_schema,
                })
            else:  # openai 兼容
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": input_schema,
                    },
                })
        return schemas

    @staticmethod
    def _build_input_schema(params: dict[str, Any]) -> dict[str, Any]:
        """把 params 字典转为 JSON Schema 的 input_schema"""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for name, schema in params.items():
            if isinstance(schema, dict):
                prop = {k: v for k, v in schema.items() if k != "default"}
                properties[name] = prop or {"type": "string"}
                if "default" not in schema:
                    required.append(name)
            else:
                properties[name] = {"type": "string"}
                required.append(name)
        result: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            result["required"] = required
        return result

    def execute(
        self,
        name: str,
        params: dict[str, Any],
        base_dir: str = ".",
        allowed_prefixes: list[str] | None = None,
        runtime_context: dict[str, Any] | None = None,
    ) -> ToolResult:
        """执行工具调用（前后注入 Hooks）"""
        # pre-hooks：可改写 params 或拦截
        params, abort = self.hooks.run_pre(name, params)
        if abort is not None:
            return abort

        result = self._execute_raw(
            name, params, base_dir, allowed_prefixes, runtime_context
        )

        # post-hooks：可改写结果
        return self.hooks.run_post(name, params, result)

    def _execute_raw(
        self,
        name: str,
        params: dict[str, Any],
        base_dir: str,
        allowed_prefixes: list[str] | None,
        runtime_context: dict[str, Any] | None,
    ) -> ToolResult:
        spec = self._tools.get(name)
        if spec is None:
            # 本地未命中，查询外部工具源
            for source in self._sources:
                if any(s.name == name for s in source.list_tools()):
                    return source.execute(name, params)
            return ToolResult(success=False, error=f"未知工具：{name}")

        sig = inspect.signature(spec.callable)
        bound = sig.bind_partial(**params)
        if "base_dir" in sig.parameters:
            bound.arguments["base_dir"] = base_dir
        if "allowed_prefixes" in sig.parameters:
            bound.arguments["allowed_prefixes"] = allowed_prefixes
        for key, value in (runtime_context or {}).items():
            if key in sig.parameters and key not in bound.arguments:
                bound.arguments[key] = value
        bound.apply_defaults()

        try:
            return spec.callable(*bound.args, **bound.kwargs)
        except Exception as exc:  # pragma: no cover - defensive
            return ToolResult(success=False, error=f"执行工具 {name} 时出错：{exc}")

    @staticmethod
    def _build_example(params: dict[str, Any]) -> dict[str, Any]:
        """为 Prompt 生成示例参数"""
        example: dict[str, Any] = {}
        for key, schema in params.items():
            if isinstance(schema, dict) and "default" in schema:
                example[key] = schema["default"]
            else:
                example[key] = _placeholder_for(key)
        return example


def _placeholder_for(key: str) -> Any:
    """根据参数名给出更贴切的示例值"""
    placeholders: dict[str, Any] = {
        "path": "relative/path",
        "content": "文件内容",
        "command": "python -m pytest",
        "query": "搜索关键词",
        "url": "https://example.com",
        "top_n": 5,
        "max_length": 8000,
    }
    return placeholders.get(key, "value")


# 全局单例
tool_registry = ToolRegistry()

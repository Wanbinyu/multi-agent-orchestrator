# MAO Tool Development Guide

> How to design and add new tools for MAO. Intended for third-party developers.
> MAO's tool system is based on a `ToolRegistry` singleton. Tools register automatically on import and become available on CLI, Web, and native tool_use without extra wiring.

---

## 1. Core Concepts

| Concept | Description |
|---|---|
| `ToolRegistry` | Global tool registry singleton `tool_registry`; manages tool metadata and execution |
| `ToolSpec` | Tool metadata: name / description / params / callable / category |
| `ToolResult` | Tool return value: `success: bool` + `output: str` + `error: str` |
| `category` | Tool category: `read` / `write` / `execute` / `external` / `unsafe` (used for permissions and display) |

There are two tool-call modes; **developers do not need to care** — the registry adapts automatically:
- **Markdown mode** (default): tools are invoked via ```` ```tool:name ```` fenced blocks; compatible with all models.
- **Native tool_use mode**: for models that declare the `tool_use` capability, native schemas are generated and passed via `tools=`.

---

## 2. Adding a Local Tool (Most Common)

### Steps

1. Create a module under `src/tools/` or `src/tools/contrib/`.
2. Decorate the function with `@tool_registry.register(...)` and return a `ToolResult`.
3. Append an `import` at the top of `src/tools/worker_tools.py` (to trigger registration).

### Full Example

```python
# src/tools/contrib/my_tools.py
from __future__ import annotations
from src.tools.registry import tool_registry
from src.tools.tool_result import ToolResult


@tool_registry.register(
    name="word_count",
    description="Count characters, words, and lines in text",
    params={
        "text": {"type": "string", "description": "Text to count"},
    },
    category="read",
)
def word_count(text: str, base_dir: str = ".") -> ToolResult:
    try:
        chars = len(text)
        words = len(text.split())
        lines = text.count("\n") + (1 if text.strip() else 0)
        return ToolResult(
            success=True,
            output=f"characters: {chars}\nwords: {words}\nlines: {lines}",
        )
    except Exception as e:
        return ToolResult(success=False, error=str(e))
```

### Register Parameters

| Parameter | Required | Description |
|---|---|---|
| `name` | ✅ | Unique tool id; the model uses it to call the tool |
| `description` | ✅ | What the tool does; goes into system prompts / native schema |
| `params` | ✅ | Parameter JSON Schema dict; each key is a param name, value is a schema fragment |
| `category` | ✅ | `read`/`write`/`execute`/`external`/`unsafe` |

### Writing `params`

```python
params={
    "path": {"type": "string", "description": "File path"},           # required
    "top_k": {"type": "integer", "description": "Count", "default": 5},  # optional (has default)
}
```
- Parameters with `default` are treated as optional and are not added to the native schema `required` list.
- `base_dir` / `allowed_prefixes` are special parameters injected by the framework (see below); **do not** put them in `params`.

### Return Value

Always return a `ToolResult`:
```python
ToolResult(success=True, output="result text")
ToolResult(success=False, error="error reason")
```
- `output` is sent back to the model as the tool result; it should be human/model-readable text.
- Never raise exceptions to the upper layer — `try/except` inside the tool and return `success=False`.

---

## 3. Special Parameters (Framework Auto-Injection)

If your tool function signature includes the following parameters, the registry injects them at execution time and the model never sees them:

| Parameter | Injected Value | Purpose |
|---|---|---|
| `base_dir: str = "."` | Current session output directory | Resolve relative paths, locate files |
| `allowed_prefixes: list[str] \| None = None` | Command allowlist | `run_command`-style tools |

Reuse `src.tools.paths.resolve_path` for path resolution; it prevents directory traversal:
```python
from src.tools.paths import resolve_path as _resolve_path

target = _resolve_path(path, base_dir)  # relative paths constrained within base_dir
```

---

## 4. Category and Permissions

| category | Meaning | readonly mode | approve mode |
|---|---|---|---|
| `read` | Read-only (read files, search) | Denied (current implementation denies all tools) | Confirm each time |
| `write` | Write/edit files | Denied | Confirm each time |
| `execute` | Run commands | Denied | Confirm each time |
| `external` | Network calls (search, fetch) | Denied | Confirm each time |
| `unsafe` | High risk (full shell, etc.) | Denied | Confirm each time; recommend opt-in only |

> Current `readonly` mode denies all tool calls (consistent with historical behavior). `category` is mainly for display and future fine-grained permissions.

---

## 5. Adding External Tool Sources (MCP, etc.)

If tools come from an external server (e.g. MCP), implement the `ToolSource` protocol and register it:

```python
from src.tools.registry import tool_registry, ToolSpec
from src.tools.tool_result import ToolResult

class MyToolSource:
    def list_tools(self) -> list[ToolSpec]:
        # Pull tool list from external server, convert to ToolSpec
        return [ToolSpec(name="ext_tool", description="...", params={...},
                         callable=lambda **_: ToolResult(success=True, output=""),
                         category="external")]
    def execute(self, name: str, params: dict) -> ToolResult:
        # Call external server to execute
        return ToolResult(success=True, output="...")

tool_registry.add_source(MyToolSource())
```

After registration, external tools are automatically included in discovery and execution; local tools with the same name take priority.

> The MCP adapter is already implemented in `src/tools/mcp_adapter.py` (stdio / SSE). `src/tools/tool_sources.py` remains a compatibility export entry.

---

## 6. After Registration, Tools Appear Automatically In

1. **Agent system prompt** (Markdown mode): listed by `tool_registry.build_instructions()`.
2. **Native tools= parameter** (native mode): schemas from `tool_registry.build_tool_schemas()`.
3. **CLI `/tools` command**: dynamically lists all registered tools.
4. **Web right sidebar (this turn)**: tool calls are shown automatically.
5. **Collaboration Workers**: grant a tool by adding its name to the `tools:` list in `config/workers.yaml`.

---

## 7. Testing Your Tool

Follow `tests/test_search_tools.py` / `tests/test_web_tools.py`:

```python
def test_word_count_basic(tmp_path):
    from src.tools.contrib.example_tools import word_count
    result = word_count("hello world\n", base_dir=str(tmp_path))
    assert result.success is True
    assert "characters" in result.output
```

Key points:
- Use `tmp_path` to isolate the filesystem;
- Assert `result.success` and `result.output` / `result.error`;
- Network tools must be mocked; do not hit the external network.

---

## 8. Checklist

Before adding a tool, confirm:
- [ ] `name` is globally unique and semantically clear
- [ ] `description` states the purpose clearly (the model decides when to call based on it)
- [ ] `params` schema is accurate; optional params have `default`
- [ ] Function uses `try/except` and returns `ToolResult` instead of raising
- [ ] `category` is correct (do not mark read-only tools as `write`)
- [ ] Path tools use `resolve_path` to prevent escapes
- [ ] Import at the top of `worker_tools.py` triggers registration
- [ ] Tests added; `python -m pytest -q` is fully green

---

## 9. Directory Layout Reference

```
src/tools/
├── registry.py            # Registry (core)
├── tool_result.py         # ToolResult
├── paths.py               # Shared path resolution
├── worker_tools.py        # Built-in tools + unified imports that trigger registration
├── memory_tools.py        # Memory search tools
├── web_tools.py           # Web tools
├── search_tools.py        # glob/grep tools
├── tool_sources.py        # MCPToolSource compatibility export
├── mcp_adapter.py         # MCP stdio / SSE adapter
└── contrib/               # Third-party / example tools
    ├── __init__.py
    └── example_tools.py   # word_count example
```

Contributions of tools to MAO are welcome!

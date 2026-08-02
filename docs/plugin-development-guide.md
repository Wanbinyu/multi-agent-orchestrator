# MAO Plugin Development Guide

This guide explains how to write a Plugin API v0 plugin for MAO. MAO discovers plugins via standard Python entry points. Plugins are disabled by default and load only after the user explicitly enables them.

A complete runnable example is at [`examples/plugins/mao_wordcount_plugin`](../examples/plugins/mao_wordcount_plugin). Compatibility rules are in [`Plugin-API-compatibility-policy.md`](Plugin-API-compatibility-policy.md).

## 1. Minimal Plugin

A plugin is a class implementing the `Plugin` protocol, plus a `create_plugin()` factory:

```python
# my_plugin/__init__.py
from src.plugins.api import (
    CAP_TOOLS, MAO_PLUGIN_API_VERSION, PERM_READ_FILES,
    Plugin, PluginContext, PluginManifest,
)
from src.tools.tool_result import ToolResult


def hello(text: str = "", base_dir: str = ".") -> ToolResult:
    return ToolResult(success=True, output=f"hello, {text or 'world'}")


class HelloPlugin:
    def __init__(self):
        self.manifest = PluginManifest(
            id="my-hello",                # unique id: lowercase letters/digits/hyphens
            name="Hello",
            version="0.1.0",
            mao_api_version=MAO_PLUGIN_API_VERSION,  # "0.1"
            description="A minimal example plugin",
            capabilities=[CAP_TOOLS],     # declare capabilities
            permissions=[PERM_READ_FILES], # declare permissions (display only, not a sandbox)
            source="my-hello-plugin",
        )

    def load(self, ctx: PluginContext) -> None:
        ctx.register_tool(
            hello, name="hello", description="Say hello",
            params={"text": {"type": "string", "description": "Name"}},
            category="read",
        )

    def shutdown(self) -> None:
        pass


def create_plugin() -> Plugin:
    return HelloPlugin()
```

## 2. Declaring the Entry Point

Declare a `mao.plugins` entry point in your package `pyproject.toml`, pointing at the factory function:

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "my-hello-plugin"
version = "0.1.0"
requires-python = ">=3.11"
license = "MIT"

[project.entry-points."mao.plugins"]
hello = "my_plugin:create_plugin"

[tool.setuptools]
packages = ["my_plugin"]
```

This plugin depends on MAO's `src` package; install it in an environment where MAO is already installed (MAO is not yet published to PyPI).

## 3. Install, Enable, Diagnose

```bash
pip install ./my_plugin
mao plugin list                 # should show my-hello
mao plugin enable my-hello      # writes config/plugins.yaml; loads on next start
mao plugin doctor               # diagnose discovery/compatibility/load health
mao                             # after start, the hello tool is available
mao plugin disable my-hello     # disable
```

## 4. PluginContext Contribution APIs

Callable from `load(ctx)` (must match manifest `capabilities`):

| Method | Capability | Description |
|---|---|---|
| `ctx.register_tool(fn, *, name, description, params, category)` | `tools` | Register a local tool; `category` is `read`/`write`/`execute`/`external`/`unsafe` |
| `ctx.add_tool_source(source)` | `tool_source` | Mount an external tool source implementing the `ToolSource` protocol (e.g. a custom MCP adapter) |
| `ctx.add_pre_hook(fn)` / `ctx.add_post_hook(fn)` | `hooks` | Pre/post tool-execution hooks |
| `ctx.register_provider_preset(key, preset)` | `provider_preset` | Contribute a WebUI Provider preset |
| `ctx.register_model_capabilities(alias, data)` | `model_capabilities` | Contribute model capability data (v0 records only; not merged into the catalog) |

`ctx` records all of a plugin's contributions; on load failure or disable, MAO calls `ctx.rollback()` to undo them — plugins do not need to unregister themselves.

## 5. Lifecycle and Isolation

- `create_plugin()` should be lightweight: only construct the object and manifest; no side effects.
- `load(ctx)` should only register; clean up heavy resources (background threads, network connections, subprocesses) in `shutdown()`.
- Exceptions from `load` are caught by MAO; `rollback` undoes partial registration and records a diagnosis; **other plugins and plugin-free startup are not blocked**.
- `shutdown` is called by MAO on process exit or disable; best-effort, should not raise.

## 6. Permissions and Security Model

- Manifest `permissions` values: `read_files`, `write_files`, `execute`, `network`.
- **Python plugins are trusted local code with the same privileges as the MAO process**. The permission list is a consent surface for users, **not a sandbox**; MAO does not technologically restrict plugin capability.
- Users explicitly consent via `mao plugin enable`; permissions are visible in `mao plugin list` and the Web "Plugins" tab.
- For external tools that need process-boundary isolation, prefer implementing an MCP tool source (`tool_source` capability) rather than running untrusted code inside the plugin process.
- Session-level `auto` / `approve` / `readonly` and `permissions.yaml` are likewise an **application-layer authorization control plane**, not an OS/container sandbox; plugin-registered tools still go through the same `permission_rules.decide`, but that does not provide process isolation.
- Full trust boundaries and Provider capabilities/error codes: [`Provider-compatibility-matrix.md`](Provider-compatibility-matrix.md) §4–§5 and root [`SECURITY.md`](../SECURITY.md).

## 7. Manifest Validation

`PluginManifest` validates on construction:

- `id` matches `^[a-z][a-z0-9-]*$`.
- `name`, `version`, and `mao_api_version` are non-empty.
- `capabilities` and `permissions` must be subsets of known constants.
- If `mao_api_version` is not in MAO `SUPPORTED_API_VERSIONS`, the plugin is refused (`plugin_api_incompatible` recorded).

## 8. Debugging

- `mao plugin doctor` dry-runs against a temporary registry and does not affect the running tool registry; it reports discovery errors, API incompatibility, and load failures.
- Exception text from plugin `load` does not enter public diagnostics (redacted), but `doctor` shows error codes and action suggestions; for local development you may temporarily `print` or log inside `load`.
- Same-id dedup: when multiple packages share an id, only the first discovered is kept.

## 9. Internal Implementation You Must Not Depend On

Plugins should contribute only through public `PluginContext` methods. Do not directly manipulate `tool_registry._tools`, `HookRegistry._pre`, `UI_PROVIDER_PRESETS`, or other internal structures — these are outside the compatibility commitment and may change at any time. See [`Plugin-API-compatibility-policy.md`](Plugin-API-compatibility-policy.md) §1.

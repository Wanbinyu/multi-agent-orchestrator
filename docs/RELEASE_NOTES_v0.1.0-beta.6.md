# MAO v0.1.0-beta.6 Release Notes

This release introduces the controlled Plugin API v0: ToolSource, MCP, Hooks and Provider presets are now unified under a diagnosable, version-constrained, explicitly-enabled extension interface.

## Highlights

- **Plugin API v0 contract**: a `PluginManifest` declares id, name, version, MAO API version, capabilities and permissions. `PluginContext` lets a plugin register tools, tool sources, hooks, provider presets and model capabilities, and tracks every contribution for clean rollback. The `Plugin` protocol defines `load`/`shutdown`. `MAO_PLUGIN_API_VERSION="0.1"`; incompatible API versions are explicitly rejected.
- **Plugin manager**: plugins are discovered via the standard Python `mao.plugins` entry-point group (no workspace scanning). They are disabled by default and only loaded after the user enables them in `config/plugins.yaml`. Each plugin's `load` runs in its own try/except; a failing plugin is rolled back and reported as a diagnostic without blocking other plugins or a pluginless startup. `shutdown` unregisters each plugin's contributions.
- **`mao plugin` CLI**: `list` shows discovered plugins with enable state, capabilities, permissions and source; `doctor` dry-runs discovery and load into throwaway registries; `enable`/`disable` write `config/plugins.yaml`. Plugin loading is wired into CLI chat and Web startup alongside the existing Hooks/MCP loader.
- **Example plugin**: `examples/plugins/mao_wordcount_plugin` is an independent installable package declaring a `mao.plugins` entry point, contributing a read-only `word_count` tool. It validates the full discover -> enable -> load -> execute -> shutdown path.
- **Web visibility**: `GET /api/plugins` and a read-only "插件" tab in the chat rightbar expose plugin list, enable state, capabilities and permissions.
- **Isolation support**: `ToolRegistry.unregister_tool/remove_source` and `HookRegistry.remove_pre/remove_post` let a failed or disabled plugin be rolled back without affecting other contributions.

## Security model

Python plugins run as trusted local code with the same privileges as the MAO process. The permission list (`read_files`/`write_files`/`execute`/`network`) is a consent surface shown to the user and gated by explicit enable, not a sandbox. External tools should still prefer MCP for a process boundary. MAO never scans arbitrary workspace code, auto-installs plugins, or downloads and executes Python from unknown URLs.

## Install

```bash
pipx install git+https://github.com/Wanbinyu/multi-agent-orchestrator.git@v0.1.0-beta.6
mao
# or
mao web
```

Python 3.11 or 3.12 is required.

## Upgrade Notes

- Plugins are disabled by default. After installing a plugin package, run `mao plugin enable <id>` and restart `mao` to load it.
- `config/plugins.yaml` holds the local enable state and is gitignored; it must not be committed.
- The `contrib/example_tools.py` auto-register-on-import pattern still works but is superseded by the manifest-driven Plugin API for anything packaged for distribution.
- `mao plugin doctor` diagnoses without affecting the running tool registry; use it to check loadability before relying on a plugin.

## Verification

- Complete local test collection: `853 passed, 1 warning`; the only warning is an upstream Starlette/httpx deprecation notice.
- `python scripts/verify_distribution.py`: builds the MAO wheel/sdist and the example plugin wheel, runs `twine check`, installs in a clean virtual environment, verifies clean CLI plus Web `/health`, and exercises the example plugin's discovery (`mao plugin list`), enable, load, execute (`word_count`) and shutdown.
- `mao plugin doctor` reports no anomalies when no plugins are enabled; an enabled incompatible plugin is rejected; a failing plugin is isolated.
- `pip-audit -r requirements.txt` reports no known vulnerabilities. The checksum-verified gitleaks 8.24.3 scan runs in CI.
- Python compileall, JavaScript syntax checks and diff hygiene pass locally.
- Real paid Provider calls were not made; beta.6 does not require real models.

## Known Limitations

- Python plugins are not sandboxed; they share the MAO process privileges.
- Plugin API v0 covers tools, tool sources, hooks, provider presets and model-capability recording. Provider runtime adapters and UI plugins are deferred until the interface stabilizes.
- There is no online plugin marketplace and no model-recommended auto-install.
- `register_model_capabilities` is recorded but not yet merged into the live model catalog.
- `pytest tests/test_registry.py` in isolation hits a pre-existing latent circular import (`replay`/`worker_tools`); the full suite and CI are unaffected.

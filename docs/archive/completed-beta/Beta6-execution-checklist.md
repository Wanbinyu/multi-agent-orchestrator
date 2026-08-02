# v0.1.0-beta.6 Execution Checklist

**Status**: beta.6 in progress; B6.1 started

**Goal**: Organize current ToolSource / MCP / Hooks / Provider presets into a diagnosable, version-constrained Plugin API v0 that must be explicitly enabled.

**Release baseline**: `v0.1.0-beta.5`

**Based on**: [`version-plan-v0.1.0-beta.3-to-beta.6.md`](version-plan-v0.1.0-beta.3-to-beta.6.md) §5, [`Claude-and-plugin-integration-decisions.md`](Claude-and-plugin-integration-decisions.md) §8.

## 0. Execution principles

- Plugins are not enabled by default; load only after the user explicitly allows them on this machine.
- Discover installed plugins via standard Python entry points; do not scan arbitrary workspace code.
- Python plugins are trusted local code with the same privileges as the MAO process; no sandbox promise; prefer MCP process boundaries for external tools.
- Load failures are isolated and reported; they must not prevent MAO starting without plugins.
- Advance only one subtask at a time; record acceptance criteria and targeted tests before changes; run targeted tests after changes before expanding regression.
- Do not call real paid Providers; Tag/Release wait for owner confirmation.

## 1. B6.1 Plugin API v0 contract

- [x] `src/plugins/api.py`: `MAO_PLUGIN_API_VERSION`, `SUPPORTED_API_VERSIONS`, `PluginManifest`, `PluginContext`, `Plugin` protocol, capability/permission constants.
- [x] Manifest validation (id/name/version/mao_api_version required; capability/permission values legal).
- [x] API version compatibility check (incompatible versions explicitly rejected).
- [x] Targeted unit tests.

### B6.1 completion gates
- [x] Manifest validation and version-compatibility tests pass.
- [x] `PluginContext` method signatures that delegate to `tool_registry`/preset registry are stable.

### B6.1 completion notes (2026-07-21)

- `src/plugins/api.py` defines the v0 stable interface: `MAO_PLUGIN_API_VERSION="0.1"`, `SUPPORTED_API_VERSIONS={"0.1"}`, `is_supported_api_version()`; `PluginManifest` (id regex `^[a-z][a-z0-9-]*$`, required fields, capability/permission whitelist validation); `PluginContext` (register_tool/add_tool_source/add_pre_hook/add_post_hook/register_provider_preset/register_model_capabilities + `rollback()` to undo all contributions + `contributed_summary()`); `Plugin` Protocol (manifest/load/shutdown).
- To support plugin isolation/rollback, add `unregister_tool()`/`remove_source()` to `ToolRegistry` and `remove_pre()`/`remove_post()` to `HookRegistry` (additive; no existing behavior change).
- Capability constants: `tools`/`tool_source`/`hooks`/`provider_preset`/`model_capabilities`; permission constants: `read_files`/`write_files`/`execute`/`network` (declaration + visibility + enable-as-consent; not a sandbox).
- `tests/test_plugin_api.py` 23 cases: manifest validation (including parameterized bad id), version compatibility, Context register/rollback (tools/tool sources/hooks/presets/model capabilities), rollback does not harm existing tools, idempotent rollback.
- Full regression `822 passed, 1 warning` (baseline 799 + 23 new), no regressions.
- Known pre-existing issue (not introduced by B6.1): running `pytest tests/test_registry.py` alone, `test_global_registry_has_builtins` hits a potential circular import between `replay`<->`worker_tools`; full suite unaffected (CI runs full suite). Can be fixed separately later.

## 2. B6.2 Plugin manager

- [x] `src/plugins/manager.py`: `PluginManager` discover (entry_points `mao.plugins`) / version reject / enable state (`config/plugins.yaml`) / isolated load / shutdown / diagnostics.
- [x] Failed plugins do not block other plugins or no-plugin startup.
- [x] Coexists with existing `load_extensions()` (independent module; zero behavior change when no plugins; startup wiring in B6.3).
- [x] Targeted tests (isolation, no plugins, repeat/idempotent).

### B6.2 completion notes (2026-07-21)

- `src/plugins/manager.py`: `PluginManager` discovers plugins via `importlib.metadata.entry_points(group="mao.plugins")` (injectable finder for tests), `ep.load()` each factory to get `Plugin`; duck-type validates manifest/load/shutdown; dedupe by id.
- Enable state: `config/plugins.yaml` (`enabled`/`disabled`, default all off); `enable/disable/is_enabled` read/write; `disabled` overrides `enabled`.
- Load: `load_enabled()` is idempotent; incompatible API version rejected with `plugin_api_incompatible` diagnostic; disabled skipped; enabled ones call `plugin.load(ctx)` one by one—on failure `ctx.rollback()` clears half-loaded state and records `plugin_load_error` without blocking other plugins or no-plugin startup.
- `shutdown()` calls each `plugin.shutdown()` + `ctx.rollback()` to unregister contributions; `list_status()` for CLI/Web shows id/name/version/api version/compatible/enabled/capabilities/permissions/source.
- Diagnostics reuse bounded redacted `extension_diagnostics` (source=`plugin`).
- `tests/test_plugin_manager.py` 15 cases: discover (compatible/incompatible/dedupe/bad entry-point isolation), enable gating, incompatible reject, failed plugin does not block others and rolls back half-load, no-plugin zero change, idempotent load, shutdown unregisters tools and closes tool sources, enable/disable round-trip, disable overrides enable, list_status.
- Full regression `837 passed, 1 warning`, no regressions.

## 3. B6.3 CLI `mao plugin`

- [x] `mao plugin list` / `doctor` / `enable <id>` / `disable <id>`.
- [x] Add `plugin` to `known_commands`; re-review command names for CLI consistency.
- [x] `config/plugins.yaml` read/write and `.gitignore`.
- [x] Targeted tests + CLI interaction.

### B6.3 completion notes (2026-07-21)

- `run.py` adds `plugin` typer sub-app: `list` (discovered plugins + enable state/capabilities/permissions/source), `doctor` (discover+compat+load health using temporary ToolRegistry/preset registry dry-run, not affecting live registries), `enable <id>`/`disable <id>` (write `config/plugins.yaml`). `"plugin"` added to `_maybe_insert_run_subcommand` `known_commands`.
- Command-name review: `list/doctor/enable/disable` match existing subcommand style (kebab-case, `--config/-c` options); no conflicts found.
- `src/plugins/runtime.py`: process-level singleton `get_plugin_manager`/`load_plugins`/`get_plugin_status`/`shutdown_plugins`/`new_plugin_manager` (CLI subcommands use independent instances). `load_plugins()` is idempotent; discovers and loads enabled plugins into the current `tool_registry`.
- Startup wiring: `chat_command.py` calls `load_plugins()` after `load_extensions()` and prints load/diagnostics; `app.py` lifespan loads plugins after extensions and `shutdown_plugins()` before `shutdown_extensions()` in `finally`.
- `.gitignore` adds `config/plugins.yaml` (like providers.yaml/workers.yaml; user local enable state not committed).
- `tests/test_plugin_cli.py` 10 cases: help lists subcommands, no-plugin list/doctor, enable writes config, enable/disable round-trip, list shows discovered plugins with enable/permissions, doctor loads enabled plugins, enable unknown id message, runtime singleton load/shutdown safety.
- Full regression `847 passed, 1 warning`, no regressions. B6.1+B6.2 remote CI `success` ([run 29837884580](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29837884580)).

## 4. B6.4 Example plugin

- [x] `examples/plugins/mao_wordcount_plugin/` standalone installable package + entry point.
- [x] Integration test: discover -> enable -> load -> execute -> shutdown (real entry point).
- [x] Incompatible API version plugins rejected (covered by B6.2 unit tests; example plugin takes the compatible path).

### B6.4 completion notes (2026-07-21)

- `examples/plugins/mao_wordcount_plugin/`: standalone installable package; `pyproject.toml` declares `[project.entry-points."mao.plugins"]` `wordcount = "mao_wordcount_plugin:create_plugin"`; `mao_wordcount_plugin/__init__.py` `WordCountPlugin` implements `Plugin` protocol (manifest id=`mao-wordcount`, API `0.1`, capabilities=`[tools]`, permissions=`[read_files]`; `load` registers read-only `word_count` tool; `shutdown` no-op), `create_plugin()` is the entry-point factory. README covers install/enable/security model.
- `tests/test_plugin_example_integration.py` 4 cases: drive the example plugin via real `importlib.metadata.entry_points(group="mao.plugins")` discovery (temp dist-info + sys.path, no pip install)—discover, enable/load/execute (`word_count` outputs chars/words/lines)/shutdown (tool unregistered), list_status (capabilities/permissions/source visible), manifest declares v0 API. Wheel-install environment acceptance left to B6.6 `verify_distribution.py`.
- Full regression `851 passed, 1 warning`, no regressions. B6.3 remote CI `success` ([run 29838695324](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29838695324)).

## 5. B6.5 Web visibility

- [x] `/api/plugins` endpoint (list + enable state + permissions).
- [x] chat.html read-only plugin/permission display; no overflow at 320/390/1280px.
- [x] Targeted tests.

### B6.5 completion notes (2026-07-21)

- `src/ui/app.py` adds `GET /api/plugins` returning `get_plugin_status()` (`statuses` list + `load` summary); like `/api/diagnostics/extensions`, does not affect `/health`.
- chat.html right bar adds “Plugins” tab + `rightbar-plugins-panel` (read-only): plugin id/name/version/enabled/compat badge/capabilities/permissions/source, load summary, and “trusted local code; permissions are consent display only” hint; `chat.js` cache version bumped to `20260721-plugins1`.
- `chat.js`: `setRightbarTab` refactored to a generic 3-tab cycle; add `loadPlugins()` (fetch `/api/plugins` -> `renderPlugins`); `tab-plugins`/`btn-refresh-plugins` click listeners.
- `style.css`: `.rightbar-tabs` grid from 2 columns to 3 (fit short “Context/Files/Plugins” labels without overflow on narrow viewports); add `.plugin-item/.plugin-badge/.plugin-meta/.plugin-hint` etc.; `plugin-item-head` uses `flex-wrap`.
- Viewports: three 2-character short labels fit the 3-column grid at 320/390/1280px (structure + CSS verified; like B5.5, did not run MAO UI Playwright).
- `tests/test_ui.py` adds 2 cases: `/api/plugins` returns `statuses` list and `load`; `/chat` page contains `tab-plugins`/`rightbar-plugins-panel`.
- Full regression `853 passed, 1 warning`, no regressions. B6.4 remote CI `success` ([run 29839280653](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29839280653)).

## 6. B6.6 Release closeout

- [x] `verify_distribution.py` includes example plugin discover/enable/execute/shutdown.
- [x] Full regression, pip-audit, compileall/JS/diff, clean install pass.
- [x] CHANGELOG, Release Notes, version `0.1.0b6`, upgrade notes complete.
- [x] Remote CI fully green including gitleaks ([run 29841673789](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29841673789)).
- [x] Tag and GitHub pre-release created after owner confirmation (`v0.1.0-beta.6` points to `6de8531`).

### B6.6 completion notes (2026-07-21)

- `scripts/verify_distribution.py` extended: build MAO wheel/sdist and example-plugin wheel (separate example-dist dir), `twine check` all three; clean venv installs MAO then example plugin; `mao plugin list` sees `mao-wordcount`, `mao plugin enable` writes `config/plugins.yaml`, then runtime singleton `load_plugins` -> execute `word_count` (`字符数：11`) -> `shutdown_plugins` (tool unregistered) end-to-end validates discover/enable/execute/shutdown.
- Version `0.1.0b5` -> `0.1.0b6` (`src/version.py`, `pyproject.toml`, `tests/test_version.py`); `python run.py --version` prints `MAO 0.1.0b6`.
- Docs: CHANGELOG adds `[0.1.0-beta.6] - 2026-07-21` and points `[Unreleased]` at `v0.2.0` entry criteria; add `docs/RELEASE_NOTES_v0.1.0-beta.6.md`; README badge and status section, `project-progress-and-key-operations.md` current status/incomplete/continue entry updated.
- Verification: full regression `853 passed, 1 warning`; `pip-audit -r requirements.txt` no known vulns; `python -m compileall`, `node --check` (app.js/chat.js), `git diff --check` pass; `verify_distribution.py` passes.
- Security scan boundary: gitleaks 8.24.3 still cannot download binary on local Windows; authoritative scan is remote CI job; [run 29841673789](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29841673789) security job (pip-audit, gitleaks) passed.
- Real Provider calls: none during unattended acceptance.
- Tag and GitHub pre-release: created after owner confirmation. `v0.1.0-beta.6` points to `6de8531`; GitHub pre-release uses in-repo `RELEASE_NOTES_v0.1.0-beta.6.md`.

## 7. Current next steps

B6.1–B6.6 complete; `v0.1.0-beta.6` published (Tag + GitHub pre-release). Core beta.3–beta.6 contracts landed. Next advance per `v0.2.0` entry criteria (external users, reproducible real benchmarks, Plugin API compatibility policy). B5.4 real multi-model evaluation remains separately paused; private smoke may continue only after the owner gives a new cumulative attempt boundary.

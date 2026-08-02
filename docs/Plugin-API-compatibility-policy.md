# Plugin API Compatibility Policy

**Status**: Compatibility commitments and evolution rules for the v0 stable interface

**Applies to**: `v0.1.0-beta.6` and later, until Plugin API v1

**Purpose**: Tell plugin authors when and how MAO will break plugin compatibility, and how to declare and maintain compatibility. This is one of the v0.2.0 entry criteria.

## 1. What is the "Plugin API"

The Plugin API is the public interface surface MAO commits to keep stable for third-party plugins. It includes only:

- **Entry point group**: `mao.plugins` (Python entry point).
- **Factory convention**: entry point points to a zero-arg factory `() -> Plugin`.
- **`Plugin` protocol** (`src/plugins/api.py`): `manifest: PluginManifest`, `load(self, ctx: PluginContext) -> None`, `shutdown(self) -> None`.
- **`PluginManifest` fields**: `id`, `name`, `version`, `mao_api_version`, `description`, `homepage`, `capabilities`, `permissions`, `source`.
- **`PluginContext` methods**: `register_tool`, `add_tool_source`, `add_pre_hook`, `add_post_hook`, `register_provider_preset`, `register_model_capabilities`, `rollback`, `contributed_summary`.
- **Capability constants**: `tools`, `tool_source`, `hooks`, `provider_preset`, `model_capabilities`.
- **Permission constants**: `read_files`, `write_files`, `execute`, `network`.
- **Enablement config format**: `enabled` / `disabled` lists in `config/plugins.yaml`.
- **CLI contract**: existence and exit-code semantics of `mao plugin list/doctor/enable/disable` (output format is not committed).

**Not in the Plugin API** (plugins must not depend on these; they may change anytime): concrete implementations of internal modules such as `src/tools/registry.py`, `src/core/hooks.py`, `src/models/catalog.py`; private attributes; undocumented tool signatures; RunJournal internal structure; Web route response body formats. Plugins should contribute only through methods exposed by `PluginContext` and must not operate internal registries directly.

## 2. Version number semantics

`MAO_PLUGIN_API_VERSION` uses `MAJOR.MINOR` (currently `0.1`).

- **MINOR upgrade (e.g. `0.1` -> `0.2`)**: Additive-only changes. New optional `PluginContext` methods, new capability/permission constants, new optional manifest fields, new CLI subcommands. **Old plugins continue to load** with no changes required.
- **MAJOR upgrade (e.g. `0.1` -> `1.0`, or a `0.x` -> `0.(x+1)` that includes breaking changes)**: Breaking changes. Including but not limited to: remove or rename `PluginContext` methods, change method signatures, remove capability/permission constants, change `Plugin` protocol methods, change entry point group name, change required manifest fields, change `config/plugins.yaml` format. **Old plugins are refused**.

In the `0.x` stage, the MAJOR vs MINOR boundary is determined by the “breaking change” list defined in this document, not by numeric magnitude; every breaking change is explicitly noted in Release Notes and this document’s revision history.

## 3. Compatibility decision

- Plugins declare the API version they target in `PluginManifest.mao_api_version` (a string).
- MAO maintains `SUPPORTED_API_VERSIONS` (currently `{"0.1"}`).
- **Load rule**: load only when `manifest.mao_api_version in SUPPORTED_API_VERSIONS`; otherwise `PluginManager` records a `plugin_api_incompatible` diagnostic and skips—no throw, no block of other plugins.
- The check finishes in the `PluginManager.discover` phase, before any `plugin.load`; incompatible plugins never run their `load`.

## 4. MAO evolution commitments

- **Additive changes**: ship directly; append new MINOR to `SUPPORTED_API_VERSIONS` while keeping old versions in the set. Example: `0.1` -> append `0.2`, set becomes `{"0.1","0.2"}`, `0.1` plugins remain usable.
- **Breaking changes**: ship a new MAJOR and, for **one release cycle**, support both old and new MAJOR (transition period). After the transition period, remove the old MAJOR from `SUPPORTED_API_VERSIONS` and refuse old plugins. Example: `0.x` -> `1.0`, transition set `{"0.x","1.0"}`, next cycle removes `0.x`.
- **Minimum transition period**: one MAO version. During transition, Release Notes and `mao plugin doctor` prompt plugin authors to upgrade.
- **Emergency security fixes**: may remove an API without a transition period, but must explicitly document a “security breaking change” at the top of Release Notes and provide a migration path.

## 5. Plugin author guide

- Always declare `mao_api_version` in the manifest as the version you developed against.
- Only use public `PluginContext` methods; do not directly import or mutate internal structures such as `tool_registry._tools` or `HookRegistry._pre`.
- Do not assume CLI output format is stable; for programmatic queries, use exit codes from `mao plugin list --config ...` or call `PluginManager` yourself.
- Pin the MAO version range your plugin depends on (document it in your package docs), because the API may still break in the `0.x` stage.
- Only register in `load`; clean heavy resources in `shutdown`. Errors thrown from `load` are rolled back and isolated and do not affect other plugins.

## 6. Current status (2026-07-21)

- `MAO_PLUGIN_API_VERSION = "0.1"`, `SUPPORTED_API_VERSIONS = {"0.1"}`.
- No breaking changes yet; no transition versions.
- In the v0 stage (`0.x`) the API may still break as MAO evolves; v1 will give a clear migration window.

## 7. Revision history

- 2026-07-21: Initial version. Defines Plugin API scope, `MAJOR.MINOR` semantics, compatibility checks, transition-period commitments, and plugin author guide.

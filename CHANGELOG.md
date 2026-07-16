# Changelog

All notable changes are documented here. MAO follows Semantic Versioning; beta releases may contain breaking changes when they are called out in upgrade notes.

## [Unreleased]

Target: `0.1.0-beta.2`

### Added

- `mao` now opens the terminal chat by default and runs first-use Provider setup when needed.
- `mao web` starts the WebUI; `mao-ui` remains available for compatibility.

### Fixed

- Installed commands now keep configuration, sessions and output in the user's current project directory.
- WebUI can start in an empty directory before Provider configuration exists.
- Installed distributions include the default Worker template required by collaboration flows.

## [0.1.0-beta.1] - 2026-07-16

### Added

- Cross-platform Windows/Ubuntu CI for Python 3.11 and 3.12.
- Installable `mao` and `mao-ui` console commands.
- Open-source governance, security guidance and issue templates.
- Provider routing, failover, streaming, native tools, hooks and MCP integration.
- CLI and Web conversation surfaces with persistent sessions and project browsing.
- Evidence-driven task classification, verification gates and completion audits.
- Bounded multi-model collaboration with ownership validation and targeted retries.
- Conservative context compaction and local context status reporting.

### Known limitations

- Tool execution is not container-isolated.
- Provider compatibility varies, especially for native tool use and dynamic model aliases.
- Advanced layered compaction and long-task benchmarking remain in progress.

### Fixed

- CI secret scan uses the free gitleaks binary so private pre-release repos are not blocked by the paid `gitleaks-action` license.
- CI steps run under bash on Windows and Ubuntu for consistent multi-line commands.

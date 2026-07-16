# Changelog

All notable changes are documented here. MAO follows Semantic Versioning; beta releases may contain breaking changes when they are called out in upgrade notes.

## [Unreleased]

### Added

- Cross-platform Windows/Ubuntu CI for Python 3.11 and 3.12.
- Installable `mao` and `mao-ui` console commands.
- Open-source governance, security guidance and issue templates.

### Fixed

- CI secret scan now uses the free gitleaks binary so private pre-release repos are not blocked by the paid `gitleaks-action` license.
- CI steps run under bash on Windows and Ubuntu for consistent multi-line commands.

## [0.1.0-beta.1] - 2026-07-16

### Added

- Provider routing, failover, streaming, native tools, hooks and MCP integration.
- CLI and Web conversation surfaces with persistent sessions and project browsing.
- Evidence-driven task classification, verification gates and completion audits.
- Bounded multi-model collaboration with ownership validation and targeted retries.
- Conservative context compaction and local context status reporting.

### Known limitations

- Tool execution is not container-isolated.
- Provider compatibility varies, especially for native tool use and dynamic model aliases.
- Advanced layered compaction and long-task benchmarking remain in progress.

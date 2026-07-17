# Changelog

All notable changes are documented here. MAO follows Semantic Versioning; beta releases may contain breaking changes when they are called out in upgrade notes.

## [Unreleased]

## [0.1.0-beta.3] - 2026-07-17

### Added

- Provider capability truth fields: `capability_status`, metadata source and verification date, context window and output limits, dynamic-alias flags. Unverified capabilities stay disabled.
- Official Anthropic preset audited against official documentation, with stable connection error codes for auth, permission, missing model, rate limit, timeout, context overflow and request errors.
- Anthropic native `tool_use` full rounds for sync and streaming: original tool IDs, ordered results, thinking kept private, compaction-safe message blocks.
- Unified `ProviderError` across CLI and Web with sanitized codes, user actions, retry and failover policy, and RunJournal provider evidence.
- Bounded, redacted diagnostics for Hooks and MCP loading; bad entries are isolated without blocking startup. CLI prints a short summary; Web exposes `GET /api/diagnostics/extensions`.
- `scripts/verify_distribution.py`: automated wheel/sdist contract, isolated install and clean first-use acceptance, now part of CI.
- Expanded model catalog covering Anthropic, OpenAI, DeepSeek, Zhipu GLM, Kimi, Alibaba Qwen, MiniMax, ByteDance Doubao and Google Gemini. `src/models/catalog.py` is the single source of truth for CLI and Web presets; unverified entries keep conservative budgets and placeholder prices.

### Fixed

- First-run setup no longer enters the interactive wizard without a real console on Windows; both stdin and stdout must be terminals.
- MCP runtime failures no longer echo raw exception text; hook/MCP loader failures are no longer silent.
- Build now requires `setuptools>=77` so PEP 639 license metadata builds on older toolchains.

### Removed

- Kimi third-party relay preset from the CLI provider presets.

## [0.1.0-beta.2] - 2026-07-16

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

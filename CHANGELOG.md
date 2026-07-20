# Changelog

All notable changes are documented here. MAO follows Semantic Versioning; beta releases may contain breaking changes when they are called out in upgrade notes.

## [Unreleased]

Next target: `v0.1.0-beta.5` (routing, execution depth, and reproducible benchmarks).

### Added

- B5.4 adds controlled `fixed-single`, `auto-route`, and `multi-model` benchmark profiles, a headless `mao benchmark-agent` entry point that uses the production Agent stream, an explicit live authorization/spend guard, and an optional Harbor `BaseInstalledAgent` adapter. The offline gate now produces 54 synthetic results across the three profiles without reading keys or calling a Provider.
- B5.3 adds a deterministic, explainable model router using task type, verified capability states, traceable prices, safe context capacity, health cooldowns, local-model status, and user constraints. Automatic routing performs at most one upgrade, unknown prices never produce savings claims, `/routing fixed` pins the configured main model, runtime failures prefer that user model before the existing failover chain, and RunJournal v5 keeps the full candidate audit while CLI/Web show a concise reason.
- B5.2 adds deterministic `fast`, `standard`, and `deep` execution budgets for main-agent/Worker tool rounds, context usage, Worker concurrency, collaboration review, and mutation verification. User preferences persist through `/depth` and the Web session API, while high-risk safety floors remain non-bypassable and every decision is journaled in RunJournal v4.
- B5.1 adds a versioned public engineering benchmark contract for question, diagnosis, small-change, build, review, and migration tasks. Single-model and MAO strategies share isolated workspaces, deterministic response/file/command checks, mutation boundaries, stability signatures, and JSON/Markdown metrics.
- The zero-Provider fixture gate runs both synthetic strategies three times in CI, rejects empty/timeout/provider-leak/unstable/unauthorized results, and labels all fixture usage as `synthetic_contract` so it cannot be mistaken for real-model evidence.

### Fixed

- Live benchmark Provider attempt ceilings are now reserved atomically before every network request across retries, streams, concurrent Workers, and Agent subcalls; reaching the limit blocks the next request instead of reporting an overrun only after the strategy returns.
- Orchestrator plans now normalize top-level task arrays, list-form acceptance text, common Worker role aliases, invalid model-role placeholders, and creative Worker drift in software tasks before execution. Alias-only corrections preserve valid configured model choices.

## [0.1.0-beta.4] - 2026-07-19

### Added

- Hierarchical project rules from `AGENTS.md`, `CLAUDE.md`, `.mao/rules`, and compatible Grok/Claude/Cursor rule directories, with bounded loading and RunJournal provenance.
- Deterministic user/project permission rules with `deny > ask > allow > session default`, canonical path matching, compound-command coverage, and shared Agent/Worker enforcement.
- Permission rules can declare human-readable justifications and load-time `match`/`not_match` examples; a rule that fails its examples is ignored with a diagnostic.
- RunJournal v3 records observed project mutations and a separate effective intent. One real project write triggers standard change verification; multiple files, dependency manifests, or new directories trigger deep build verification without widening the original tool permission boundary.
- Portable project verification now discovers real package/Python commands, executes one argument-array command with a structured `cwd`, records bounded command metadata, detects missing script dependencies, and supports cleaned temporary Vite build output.
- High-risk frontend builds use a fixed architecture/scaffold, pages, data/API and integration contract. The contract declares entrypoints, routes, dependencies, ownership, verification commands and smoke paths; integration success requires deterministic import/route closure plus real successful command evidence.
- RunJournal collaboration metrics expose planned roles and actual models for Orchestrator, Workers and Reviewer; Reviewer receives the original request, file list, acceptance evidence and command/runtime evidence.
- Controlled Playwright frontend smoke starts a structured local server on a dynamic loopback port, cleans its process tree, and verifies login, routes, console/page errors, non-empty data/canvas content, horizontal overflow and declared overlap pairs at desktop and mobile viewports. Its real tool result creates the required smoke VerificationGate.
- Deterministic session/today delivery reports aggregate every local RunJournal with run/evidence provenance, deduplicate repeated facts, separate creation/modification/verification/pending/user steps, and calculate per-role usage, success, first-pass runnable, rework, misdiagnosis and token-per-delivery metrics. CLI `/report`, Web and explicit natural-language report requests use the same zero-Provider path.
- A sanitized smart-mining stability fixture and replay gate exercise classification, multi-model frontend contracts, dependency closure, real local commands, browser smoke, completion audit, and delivery reporting in CI without Provider calls. Positive and intentionally broken variants lock completed/blocked behavior.
- Interrupted sessions now require an explicit local recovery decision when the latest run is running, blocked, or has unfinished plan steps. CLI `/resume` and the Web recovery banner prevent sync/stream execution until confirmation; continuation creates a new run with a one-time unfinished-step checkpoint and never auto-replays completed work.
- Context compaction now uses L0 artifact references, an L1 structured summary, and L2 recent full messages. It safely deduplicates plain history, preserves native tool pairs and a deterministic RunJournal checkpoint, records schema fallback/entity retention/relevance metrics, and ships a zero-Provider 32K/64K/128K/200K three-compaction benchmark.
- Project index v2 persists the normalized root, stable tree paths, file summaries, symbols and SHA-256 hashes. Incremental refresh performs zero content reads for unchanged projects, reparses only hash-changing files, recovers corrupt/cross-root caches, and backs `project_tree` plus path-aware `search_project_files` with auditable cache metadata.
- Reviewer input defaults to `restricted`: original requirements, plans, files and direct engineering evidence are available while Worker response bodies are excluded. Configurable `full` mode remains compatible, the actual mode is journaled, and neither mode can override failed Workers or deterministic completion audits.
- Persistent Plan mode across CLI and Web, including revision, approval handoff, cancellation, and a tool-free four-role multi-model planning council.

### Fixed

- Permission modes now control tool execution consistently: `auto` may execute non-read tools without a second gate, `approve` asks only for non-read tools, and `readonly` permits reads while rejecting writes and commands. Unclassified requests follow the session mode without being misreported as engineering changes, and natural follow-ups such as `帮我创建好` are recognized as build requests.
- Plan mode and explicit task read-only boundaries are enforced at tool execution, including Worker calls; project rules and `allow` rules cannot override them.
- Natural requests such as `现在给我做一个纯前端项目` and `在 G:\\path 中做一个项目` classify as high-risk builds, while instructional questions remain read-only. Session output `response.md` no longer counts as a project mutation.
- Command preflight failures no longer masquerade as failed tests. Inline `cd`, shell composition, invalid cwd, allowlist and permission failures return actionable alternatives and permit at most one correction attempt.
- Windows command execution resolves wrappers such as `npm.CMD` after a direct `shell=False` launch reports `FileNotFoundError`; first-pass runnable metrics now require every targeted, integration, full, and smoke gate to pass.
- Live permission requests are removed after resolution and unknown request IDs are rejected; Web prevents concurrent requests or deletion for one active session and persists mode changes on the live Session.
- Recovery seals contradictory completed runs with unfinished plan steps as blocked. Native tool block entities participate in compaction, and plain-text fallback artifacts no longer use a JSON extension.
- Reviewer output fields are type-checked, failed parsing still records usage, and collaboration plans are capped at 24 tasks to prevent unbounded model fan-out.
- Frontend closure and smoke gates reject malformed dependency sections, resources outside the project root, HTTP error pages, incomplete viewport results and inline interpreter server code. Offline replay cannot complete when a deterministic precondition fails.
- Distribution acceptance installs dependencies in a clean virtual environment without inherited system packages; CI verifies the official gitleaks checksum before execution.

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

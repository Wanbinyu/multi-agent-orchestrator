# v0.1.0-beta.3 Execution Checklist

**Status**: Completed; `v0.1.0-beta.3` pre-release published 2026-07-17

**Goal**: Trusted Provider/Claude integration and first-use stability

**Plan baseline commit**: `ac95647`

**B3.1 start commit**: `67ac9a9`

**Baseline tests**: `506 passed, 1 warning`

## 0. Pre-start checks

- [x] `git status --short --branch` is clean.
- [x] After `git fetch origin`, confirm `main` has no unmerged commits.
- [x] Read:
  - `docs/archive/completed-beta/version-plan-v0.1.0-beta.3-to-beta.6.md`
  - `docs/archive/completed-beta/Claude-and-plugin-integration-decisions.md`
  - `docs/project-progress-and-key-operations.md`
- [x] Do not use old keys that appeared in conversation; real keys must be rotated in the Provider console and written only to local `.env`.
- [x] Do not run real paid Claude calls without owner confirmation.

## 1. B3.1 Provider capability source of truth

### Goal

Upgrade model capabilities from scattered preset strings to sourced, verifiable, fallback-safe data.

### Main files

- `src/models/catalog.py`
- `src/models/schemas.py`
- `src/ui/presets/builtin/*.py`
- `config/providers.yaml.example`
- New or extended Provider/Model catalog tests

### Tasks

- [x] Define capability fields and status: supported / unsupported / unverified.
- [x] Add source, verification date, dynamic aliases, and max-output fields.
- [x] Unverified capabilities are not enabled automatically.
- [x] Web/CLI can distinguish logical aliases from upstream model IDs.
- [x] Fix example config and test fixtures.

### Acceptance

- [x] Old configs still load.
- [x] Unknown models fall back to conservative context and capabilities.
- [x] Capability data has unit tests; invalid fields are rejected.

### B3.1 implementation notes (2026-07-16)

- Data contract: `ModelConfig` adds `capability_status`, `metadata_source`, and `metadata_verified_at`; status accepts only `supported`, `unsupported`, `unverified`.
- Compatibility: when old configs lack `capability_status`, behavior continues to follow `capabilities`; when the new field is present, only `supported` auto-enables capabilities; explicit `native_tools` remains a user override.
- Config chain: model catalog, Web preset expansion, Web save/edit, legacy CLI preset generator, and example YAML all retain the new fields.
- Runtime chain: Agent and Worker use the same capability judgment and no longer treat explicit `unverified` `tool_use` as available.
- Verification: `python -m pytest -q` → `517 passed, 1 warning`; `compileall`, `node --check`, and `git diff --check` passed.
- Residual risk: real capabilities, model IDs, pricing, and limits for built-in Providers are not yet verified item-by-item; do not change unverified status to `supported` before B3.2.

## 2. B3.2 Official Anthropic preset and connection

### Goal

Ensure the official Claude configuration contains only sourced models and capabilities.

### Main files

- `src/ui/presets/builtin/anthropic.py`
- `src/gateway/connection_test.py`
- `src/gateway/provider.py`
- `src/models/catalog.py`
- Provider config and connection tests

### Tasks

- [x] Verify model IDs, pricing, context, and output limits from official sources.
- [x] Remove or mark model entries that cannot be confirmed.
- [x] Clarify `ANTHROPIC_API_KEY` configuration guidance.
- [x] Distinguish official Anthropic, Anthropic-compatible services, and OpenRouter Claude.
- [x] Cover 401/403, 404, 429, timeout, and context-exceeded cases.

### Acceptance

- [x] Offline mocks cover all error categories.
- [x] Errors without a key are clear and never print the key.
- [ ] With owner authorization, run one minimal real connection smoke and record cost. Currently unauthorized/not executed; does not block offline acceptance.

### B3.2 implementation notes (2026-07-16)

- Official sources: model data from [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview), auth from [Get started](https://platform.claude.com/docs/en/get-started), error classification from [Claude API errors](https://platform.claude.com/docs/en/api/errors).
- Model IDs: Fable 5, Opus 4.8, Sonnet 5 use official undated fixed IDs; Haiku 4.5 uses `claude-haiku-4-5-20251001`.
- Limits and pricing: record 1M/128K and Haiku 200K/64K context/output limits; pricing uses official standard rates; do not write Sonnet 5 limited-time discounts as long-term prices.
- Single source of truth: `src/models/catalog.py` is the official Anthropic data source; CLI and Web presets are generated from the catalog and no longer copy model metadata separately.
- Capability boundary: `tool_use` waits for full-round verification in B3.3; `vision` waits for structured image messages; both remain `unverified`.
- Connection diagnostics: add stable `error_code` covering auth, permission, model not found, rate limit, timeout, context exceeded, ordinary parameter errors, and connection failure; user messages do not concatenate raw SDK exceptions.
- Verification: `python -m pytest -q` → `526 passed, 1 warning`; `compileall`, `node --check`, and `git diff --check` passed.
- Not executed: no real Anthropic key was read or used; no paid calls.

## 3. B3.3 Claude native tool full round-trip

### Goal

Verify the full semantics of tool definitions, `tool_use`, local execution, and next-round result handoff.

### Main files

- `src/gateway/provider.py`
- `src/core/agent.py`
- `src/models/schemas.py`
- `tests/test_native_tool_use.py`

### Tasks

- [x] Establish a structured internal representation for Anthropic multi-part content / tool results.
- [x] Keep Markdown fallback for Providers that do not support native tools.
- [x] Streaming and non-streaming paths behave consistently.
- [x] Thinking content is not displayed, not logged, and does not break required state.
- [x] Vision remains unverified until structured image messages are complete.

### Acceptance

- [x] Cover at least one read-tool round and one approved write-tool round.
- [x] Tool errors can return to the model and retain Evidence.
- [x] Context compaction does not produce orphaned tool blocks.

### Completion notes (2026-07-16)

- Messages add safely persistable `text`, `tool_use`, and `tool_result` blocks; legacy string messages and old Session YAML remain compatible.
- Anthropic sync and streaming responses both preserve Provider-private state required for the next round; thinking/signature exist only in-process and are not displayed, written to Session YAML, or logged.
- Tool results use the original `tool_use_id`; result blocks precede subsequent text; failed results set `is_error: true`; when tool limits are hit, paired error results are still returned first.
- Offline contract tests cover Agent, Worker, human-approved writes, tool-failure Evidence, streaming state, and compaction boundaries; write-file intent also covers real expressions with path and content.
- Context budget estimates from actual native payloads so required private blocks are not omitted.
- Verification: `python -m pytest -q` → `536 passed, 1 warning`; `compileall`, `node --check`, and `git diff --check` passed.
- Not executed: no real Anthropic key was read or used; no paid calls; official Claude `tool_use` remains `unverified` pending owner-authorized real end-to-end smoke; `vision` waits for structured image messages.

## 4. B3.4 Provider errors and recovery

### Goal

Share stable error categories and user action guidance across all Providers.

### Main files

- `src/gateway/client.py`
- `src/gateway/connection_test.py`
- `src/gateway/provider.py`
- CLI/Web error display modules

### Tasks

- [x] Define structured ProviderError.
- [x] Auth/config errors are not retried and do not failover.
- [x] 429, timeout, connection failure, and 5xx retry per policy.
- [x] Context exceeded prioritizes local budget explanation and is not disguised as a network error.
- [x] Error messages are redacted and retain debuggable error codes.

### Acceptance

- [x] Same error has consistent semantics in CLI/Web.
- [x] Failed RunJournal is recoverable with accurate status.
- [x] Retry count and final model are written to Evidence.

### Completion notes (2026-07-16)

- Unified `ProviderError` stably covers config, auth, permission, model not found, long-term quota, short-term rate limit, timeout, connection, 5xx, context, invalid request, stream interrupt, and unknown Provider errors.
- Each error includes redacted error code, user message, action guidance, retry/switch flags, status code, attempt count, attempted models, and final model; raw SDK responses, request headers, or keys are not retained.
- Auth, permission, config, context, and invalid request do not retry or switch; short-term 429, timeout, connection, and 5xx use exponential backoff then configured failover; long-term quota enters cooldown and tries fallback models.
- After streaming has started producing output, do not auto-replay or switch to avoid duplicate content; local context budget errors retain safe token estimates and budget numbers.
- Connection test, actual chat, CLI, and Web JSON/SSE use the same error codes and guidance; Rich CLI uses structured text to avoid treating `[error_code]` as style marks.
- Gateway records redacted attempt traces; on retry, failure, or switch, Agent writes attempt count, error code, attempted models, and final model to RunJournal Evidence. Failed Runs can be loaded; subsequent new Runs recover normally.
- Verification: `python -m pytest -q` → `547 passed, 1 warning`; `compileall`, `node --check`, and `git diff --check` passed.
- Not executed: no real Provider key was read or used; no paid calls.

## 5. B3.5 Extension diagnostics and first use

### Goal

Remove silent extension failures and verify first use on a clean install.

### Main files

- `src/tools/extensions.py`
- `src/tools/mcp_adapter.py`
- `src/core/hooks.py`
- `run.py`
- `src/ui/app.py`
- `scripts/verify_distribution.py`

### Tasks

- [x] Hooks/MCP load errors form bounded diagnostic results.
- [x] Stay quiet when there is no extension config.
- [x] Bad extensions do not block core startup.
- [x] Verify `mao` first-run wizard in a clean directory.
- [x] Verify `mao web` config and `/health` in a clean directory.
- [x] Verify pipx install, upgrade, and uninstall instructions.

### Acceptance

- [x] Windows/Linux CI passes.
- [x] wheel/sdist metadata and archive contents pass.
- [x] Extension errors do not leak environment variables.

### Completion notes (2026-07-16)

- Hook/MCP config loads entry-by-entry: bad entries produce fixed error codes, action guidance, config filename, and entry index; valid entries continue to register; at most 10 diagnostics globally.
- Diagnostics do not store exception text, full config paths, MCP command/args/env, request headers, or keys—only safe exception types; MCP connect, list, and call exceptions also no longer echo raw exceptions.
- CLI shows at most 3 summary lines only when diagnostics exist; Web keeps `/health` as `ok`; detailed results come from `/api/diagnostics/extensions` separately. No extra startup noise without extension config.
- Fixed Windows console-script entering the first-run interactive wizard incorrectly without a console: Questionary starts only when both stdin and stdout are attached to a TTY; otherwise exit code 2 with a hint to use interactive `mao` or `mao web`.
- Added `scripts/verify_distribution.py`: builds and checks wheel/sdist, confirms dev tests and internal docs are not in the release package; installs the wheel in a temporary venv and verifies empty-dir `mao`, `mao --version`, help, Web config page, and `/health`.
- README documents `pipx install`, `pipx upgrade`, and `pipx uninstall`. Automated acceptance uses a temporary venv and does not change the machine’s global pipx state.
- Local verification: `python -m pytest -q` → `556 passed, 1 warning`; distribution and empty-dir first-use acceptance passed. The only warning remains the existing Starlette/httpx deprecation note.
- Commit record (2026-07-17): `2f9ee73` committed this batch; remote CI first failed on distribution acceptance because the hosted setuptools was too old to recognize PEP 639 `license = "MIT"` (local 83.0.0 did not hit this); `ebd391a` raised the build requirement to `setuptools>=77` and pinned it in the CI install step. After the fix, Windows/Ubuntu × Python 3.11/3.12 matrix plus pip-audit and gitleaks all passed.

## 6. B3.6 Release closeout

- [x] Update `CHANGELOG.md`.
- [x] Bump version to `0.1.0b3`.
- [x] Write `RELEASE_NOTES_v0.1.0-beta.3.md`.
- [x] Full tests, compileall, JavaScript syntax, and diff hygiene pass. (`558 passed, 1 warning`)
- [x] `pip-audit` passes (no known vulnerabilities); gitleaks runs in remote CI security job.
- [x] Build wheel/sdist; `twine check` passes.
- [x] Empty-dir isolated install and `mao web /health` pass (`scripts/verify_distribution.py`).
- [x] Remote Windows/Ubuntu CI passes.
- [x] Create Tag and GitHub pre-release only after separate owner confirmation. (`v0.1.0-beta.3` published with confirmation on 2026-07-17)

Closeout also removed the CLI preset `kimi` entry that pointed at a third-party aggregate relay (`api.va11.icu`); official moonshot.cn is covered by Web presets; `model_map` mechanism tests now use a neutral example address.

## 7. Recommended commit boundaries

1. `feat: add verified provider capability metadata`
2. `fix: harden official anthropic provider integration`
3. `feat: preserve native anthropic tool rounds`
4. `fix: unify provider failures and recovery`
5. `fix: expose extension diagnostics and first-run checks`
6. `docs: prepare beta.3 release`

Each commit must independently pass targeted tests; do not wait until the end to fix all regressions at once.

## 8. Current next steps

B3.5 is committed and passed Windows/Linux CI; enter **B3.6 release closeout**: per section 6, update CHANGELOG, version, and Release Notes; build and `twine check` distribution packages; empty-dir pipx install acceptance; Tag and GitHub pre-release must wait for separate owner confirmation. Do not make real paid calls without owner authorization.

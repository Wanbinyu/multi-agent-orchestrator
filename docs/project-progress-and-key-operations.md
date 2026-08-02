# MAO Project Progress and Key Operations

**Purpose**: Single status entry point when continuing development across devices and tools

**Last updated**: 2026-07-25

## 1. Current status

| Item | Status |
|---|---|
| Public version | [`v0.1.0-beta.7`](https://github.com/Wanbinyu/multi-agent-orchestrator/releases/tag/v0.1.0-beta.7) pre-release (security patch) |
| Repository | Public: <https://github.com/Wanbinyu/multi-agent-orchestrator> |
| Current branch | `main` |
| B3.1 starting commit | `67ac9a9` |
| Automated test baseline | `868 passed, 1 warning` (local related suites continue to grow) |
| CI | beta.7 commit `49267ba` passed Windows/Ubuntu × Python 3.11/3.12, pip-audit, and gitleaks ([run 29881111078](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29881111078)) |
| Current development stage | `v0.1.0-beta.7` released; O1–O3 and UX consolidation (docs, U4 schema, Provider matrix, hide budget fields on config page, default 200K context, CLI cat branding and bottom token bar) |
| Current top task | Timeout/retry/status/full logging completed (`logging_setup`, `retry_policy`, `MAO_TURN_TIMEOUT_SECONDS`, Journal checkpoint); next can follow the engineering main line or O4 external collection |

## 2. Completed highlights

- Provider configuration UI, CLI/Web chat, and streaming responses.
- Multi-model Orchestrator/Dispatcher/Worker/Reviewer collaboration.
- `auto` / `approve` / `readonly` permission modes.
- Tool registry, dual-track native tools, MCP, Hooks, and local models.
- Evidence, VerificationGate, RequirementCheck, CompletionAudit, and RunJournal.
- Dynamic context budget and minimal long-session baseline.
- `pipx` install, global `mao` and `mao web` entry points.
- U4 headless run events: `mao run --output-format plain|json|streaming-json`, covering plan, model, tool, command, file change, verification, approval, usage, error, and end status; JSON/JSONL does not include Worker body text.
- Public `v0.1.0-beta.2`; old stage docs archived.
- OpenCode reference audit and new Beta roadmap.
- Established version boundaries for `beta.3` through `beta.6`, Claude official API boundary, and Plugin API v0 timing.
- Established current-version execution checklist, cross-device recovery steps, and single documentation entry.
- B3.1 established Provider capability truth fields, conservative enable rules, and config round-trip save; old configs stay compatible.
- B3.2 corrected model truth and connection error classification per Anthropic official materials; real paid smoke not authorized, not executed.
- B3.3 completed Anthropic structured tool turns: sync/stream state, original tool IDs, result order, human-approval writes, failure Evidence, thinking private state, and compaction boundaries all passed offline acceptance.
- B3.3 did not call real paid APIs; `tool_use` and `vision` capabilities remain `unverified`, awaiting real end-to-end smoke and structured image messages respectively.
- B3.4 unified ProviderError, connection tests, sync/stream retry and failover, CLI/Web error semantics, and RunJournal Provider Evidence.
- B3.4 distinguishes short rate limits from long quotas; auth/config errors do not enter automatic failover; all error display uses redacted error codes and operational guidance.
- B3.5 implemented bounded redacted Hook/MCP diagnostics, bad-entry isolation, CLI summary, and independent Web diagnostics API; no-extension config remains quiet.
- B3.5 fixed Windows no-console first start mistakenly entering Questionary, and added automated distribution acceptance for wheel/sdist, isolated install, and empty-directory CLI/Web.
- B3.5 committed (`2f9ee73`); first remote CI failed because hosted setuptools<77 did not recognize PEP 639 license; `ebd391a` raised build requirements and the matrix went fully green.
- Preset model catalog expansion: `src/models/catalog.py` is the single source of truth for CLI and Web presets, adding GPT-5, DeepSeek V4 Pro/Flash, Kimi K2.7 series, GLM-5, Qwen3 Coder, MiniMax M2.7, Doubao Seed 2.1 Pro, and Gemini 3.x; unverified entries stay `unverified`; prices are placeholders only.
- Version plan wrote new directions for beta.4 (interference metrics, L0/L1/L2 layering, Reviewer info-limit validation) and beta.5 (preset expansion, benchmark contamination prevention, adversarial test generation, local-model cost tier) into scope and release gates.
- Usage feedback fixed dual permission-mode gating: `auto` can write/execute directly, `approve` only confirms non-read-only tools, `readonly` can read but rejects write/command; unknown tasks follow session mode without falsely triggering engineering verification; “help me create it” can enter a build task directly. Full regression `589 passed, 1 warning`.
- Absorbed Grok Build basic behavior contracts: hierarchical project rules, `deny/ask/allow` permission rules, persistent Plan state, and tool-less four-role multi-model Planning Council; main Agent/Worker share execution boundaries; CLI/Web can enter, view, revise, approve implementation, and cancel. Historical design: [`archive/completed-beta/Grok-Build-behavior-contract-integration.md`](archive/completed-beta/Grok-Build-behavior-contract-integration.md).
- Completed license and behavior-contract audits for Grok Build, Codex, OpenCode, Aider, Cline, Goose, and Qwen Code; permission rules already absorbed `justification` and load-time self-check for `match/not_match`, with failed rules auto-excluded. Full regression `621 passed, 1 warning`. Later JSONL, checkpoints, Repo Map, and OS sandbox follow stability-phase order strictly—see [`open-source-coding-agent-reference-plan.md`](open-source-coding-agent-reference-plan.md).
- Completed smart-mining real-task retrospective: generated project passed TypeScript and Vite in-memory build, but Mock request architecture caused login, data load, and page switch failures; original build request was misclassified as `unclassified`, and after 33 project files were written still `audit: not_required`. Historical stability slice: [`archive/completed-beta/real-task-stability-improvement-plan.md`](archive/completed-beta/real-task-stability-improvement-plan.md).
- B4.S1 completed: real natural-language build requests enter `build/high/deep`; RunJournal v3 adds initial/effective intent and observed mutation. Single-file writes trigger standard audit; multi-file, dependency, or new directory triggers deep audit; Session root `response.md` excluded; dynamic upgrade does not expand execution permissions. Full regression `633 passed, 1 warning`.
- B4.S2 completed: added read-only project command discovery, structured cwd, argument-array execution, command trails, output truncation, Vite temp builds, and one corrective-attempt cap; scripts referencing missing deps marked unavailable; precheck rejection no longer fabricates fake test gates. Full regression `653 passed, 1 warning`.
- B4.S3 completed: high-risk frontend builds always split architecture/scaffold, pages, data/API, integration, and Reviewer duties; structured contract covers entry, routes, dependencies, ownership, verification commands, and smoke paths. Integration Worker deterministically checks missing pages, bad imports, and dependency closure, and requires real successful command Evidence; Reviewer cannot override failures. RunJournal shows duties and actual models. Full regression `664 passed, 1 warning`.
- B4.S4 completed: added controlled Playwright smoke, dynamic local ports, and process-tree cleanup; desktop/mobile checks for login, seven main routes, Mock data, non-empty charts, console/page error, horizontal overflow, and declarative occlusion. Real positive fixture passes; broken Mock fixture stays blocked. Full regression `673 passed, 1 warning`.
- B4.S5 completed: added this-session/today real RunJournal reports distinguishing create, modify, verify, todo, user steps, and risk with provenance; CLI, Web, and explicit natural-language report requests share a zero-Provider path. Added duty-model token/cost, success rate, first-pass runnable rate, rework, misdiagnosis, and tokens-per-effective-delivery metrics. Full regression `679 passed, 1 warning`.
- B4.S6 completed: public redacted smart-mining fixture offline-chains classification, multi-model frontend contract, closure, real npm commands, Playwright, completion audit, and report; CI has zero Provider calls end-to-end; good sample completes; broken Mock and missing-route samples stay blocked. Also fixed Windows `npm.CMD` resolution and first-pass runnable metrics. Full regression `683 passed, 1 warning`.
- B4.3 completed: latest running/blocked/incomplete plan triggers local recovery confirmation; CLI `/resume` and Web banner block sync/stream messages until confirmation. Continue or abandon only records a local decision—no model call, no tool execution, no rollback; resume creates a new run carrying unfinished-step checkpoints once. Full regression `689 passed, 1 warning`; desktop/390px browser interaction passed.
- B4.4 completed: compaction upgraded to L0 artifact index, L1 structured summary, L2 recent full text; added safe dedup, JSON Schema/plain-text fallback, critical entity repair, RunJournal fixed checkpoint, entity retention rate, and related token metrics. 32K/64K/128K/200K offline compaction three times each all passed; fact retention 1.0; Provider calls 0. Full regression `695 passed, 1 warning`.
- B4.5 completed: project index v2 persists root, tree paths, file summaries, and SHA-256; unchanged projects do zero content reads on second refresh; single-file change reads only that file; same hash updates metadata only. Tree and search prefer incremental index; corrupt/cross-root safe rebuild; search can bind an absolute project path explicitly. Full regression `701 passed, 1 warning`.
- B4.6 completed: Reviewer defaults to restricted—sees only requirements, plan, files, and real tool/verification/requirement/audit Evidence, not Worker body; config can switch to full. Actual mode written to collaboration metrics; deterministic audit and failed Workers can still veto Reviewer. Full regression `703 passed, 1 warning`.
- B4.7 released: version `0.1.0b4`, full test suite `722 passed, 1 warning`; permission confirmation, recovery contradiction state, native tool compaction, Reviewer types, task fan-out, frontend false positives, report cross-session facts, and Web concurrency all hardened. Real-task redacted replay, four-tier thrice context compaction, wheel/sdist, `twine check`, clean venv install, empty-directory CLI, Web `/health`, pip-audit, and gitleaks all passed without calling paid Providers. After cross-platform fix commit `c0caecb`, remote CI five job groups all green.
- B5.1 completed locally: generic benchmark Schema and strategy protocol let single-model/MAO share isolated runner and deterministic acceptance; public six-class programmatic tasks run thrice form 36 stable results, Provider calls 0. JSON/Markdown reports record tokens, cost, tools, total time, completion rate, mis-modification rate, and verification pass rate, and mark fixture data as `synthetic_contract`. wheel/sdist, `twine check`, and public benchmark archive contracts passed; full suite `735 passed, 1 warning`; remote CI awaited post-commit.
- B5.2 completed locally: RunJournal v4 records requested/recommended/actual values, reason, and budget for `fast/standard/deep`; three tiers constrain main Agent/Worker tool rounds, context ratio, Worker concurrency, collaboration Reviewer, and change-verification floor. CLI `/depth` and Web session API can persist explicit choice; high risk and real multi-file writes cannot be bypassed by `fast`. Full regression `749 passed, 1 warning`; engineering benchmark 36/36 stable, smart-mining positive/negative replay and distribution acceptance passed, Provider calls 0.
- B5.3 completed locally: routing only reads task, verified capabilities, traceable price, context, health, and user constraints; automatic upgrade at most once; unknown capability/price do not participate in capability or savings claims; `/routing fixed` locks main model. On switchable auto-candidate failure, prefer fallback to user main model; full candidate audit written to RunJournal v5; CLI/Web show concise reasons. Full regression `763 passed, 1 warning`; engineering benchmark 36/36 stable, smart-mining positive/negative replay and distribution acceptance passed, Provider calls 0.
- B5.4 added external capability evaluation reminder: when the stage is reached, first prompt the owner to start testing and confirm model, attempts, cost, and publication scope; first target is Terminal-Bench/Harbor adapter, then evaluate SWE-bench Lite/Verified after stability; Aider only supplements code editing.
- B5.4 offline infrastructure completed: same harness uses independent profiles for `fixed-single`/`auto-route`/`multi-model`; 6 task classes thrice yield 54 stable synthetic results, Provider calls 0.
- Added non-interactive `mao benchmark-agent` entry on the production Agent chain, restricted `allowed_models`, shared attempt/cost stop gate for all strategies, and Harbor `BaseInstalledAgent` adapter. Real keys not read; real Provider calls still 0.
- B5.4 operations, key injection, reproducible install, and result interpretation: [`B5.4-real-capability-benchmark-handbook.md`](B5.4-real-capability-benchmark-handbook.md).
- B5.4 current full regression `787 passed, 1 warning`; distribution acceptance passed. Dev machine has only Python 3.11, so Harbor `0.20.x` real import/Docker smoke requiring Python 3.12 has not run.
- B5.4 private real smoke: `fixed-single/glm-ark` external verifier passed, 3 calls, `2857/431` tokens, `$0.003288`; after index redirect, `auto-route` also passed external verifier but conservatively only used `glm-ark`.
- Owner raised cumulative attempt cap from 20 to 35; cost cap stays `$0.20`. `multi-model` successively exposed top-level arrays, role aliases, list-style acceptance criteria, and software Worker semantic drift—all fixed and added to offline tests.
- Old `LiveBenchmarkSpendGuard` counted only after the full round; the last round jumped from remaining 8 to 13, producing cumulative **40/35** and cost `$0.032453`. Real calls stopped; the attempt gate is now a thread-safe hard reserve before each Provider request; mock verifies sync, stream, and 100 concurrent contentions never let attempt N+1 reach the Provider.
- Software plan normalization corrects common unregistered roles and creative-role drift; generic alias changes keep already-configured legal models; only when software tasks misuse creative roles like `writer/editor` do they switch to the software Worker default model.
- Latest `multi-model` report `bench-fb6c0b3bf4d0`: only actually used `glm-ark`; external verifier did not pass, so B5.4 multi-model real capability remains unaccepted. Do not continue real retries without new owner authorization.
- B5.5 added a default-off read-only adversarial test role: runs only after explicitly enabled `deep change/build` collaboration, all Workers succeed, and deterministic audit passes; reads only direct Evidence; cannot modify the project. `refuted` can only downgrade completion to blocked; `inconclusive` only adds residual risk; no result can bypass deterministic completion audit.
- CLI `/adversarial on|off` and Web session switch share persisted state; mid-run changes return 409. Web verified default off, refresh persistence, no overlap at 320/390/1280px, and no console errors.
- Local/Ollama zero marginal cost is only a routing score factor and cannot bypass health cooldown, verified capabilities, and context capacity; when `deep build` required reasoning is unmet, still upgrade to a qualified cloud model.
- B5.5 full regression `798 passed, 1 warning`; engineering benchmark 54/54 stable, Provider calls/attempts 0, distribution acceptance passed. Experimental switch real-model effects not yet claimed; no new real calls.
- B5.6 release consolidation completed (local): model catalog single-source audit passed and fixed a small CLI `ark` preset drift from catalog, with anti-drift regression tests; public benchmark source/generate/run/results reproducible and marked `synthetic_contract`; version raised to `0.1.0b5` (`src/version.py`, `pyproject.toml`, `tests/test_version.py` synced); CHANGELOG, Release Notes, upgrade notes done; full regression `799 passed, 1 warning`, pip-audit clean, compileall/JS syntax/diff checks passed. Review found remote CI for `cbcf056` (B5.5) had actually failed but was not previously recorded: `build/` gitignore hid benchmark `tasks/build/` fixtures so files were uncommitted—CI failed while local passed; `737ac8e` anchored `/build/` and restored fixtures, then remote CI fully green (including gitleaks 8.24.3). Commit sequence: `814bec9` catalog fix, `6a496fb` version and release docs, `737ac8e` gitignore and fixture fix, `6f95f27` record CI green. Tag `v0.1.0-beta.5` (`6f95f27`) and GitHub pre-release confirmed and created by owner.
- `v0.1.0-beta.6` Plugin API v0 completed (local): B6.1 contract (`src/plugins/api.py`: `PluginManifest`/`PluginContext`/`Plugin` protocol, `MAO_PLUGIN_API_VERSION="0.1"`, capability/permission allowlists, rollback); B6.2 manager (`src/plugins/manager.py`: entry point discovery, version rejection, enable gating, isolated load, shutdown, diagnostics); B6.3 CLI `mao plugin list/doctor/enable/disable` + startup wiring (`src/plugins/runtime.py`); B6.4 example plugin `examples/plugins/mao_wordcount_plugin` (standalone installable package + entry point); B6.5 Web `/api/plugins` + chat “Plugins” read-only tab. `ToolRegistry`/`HookRegistry` gained unregister methods for isolated rollback. Version `0.1.0b6`. Full regression `853 passed, 1 warning`, pip-audit clean, `verify_distribution.py` includes example plugin discover/enable/execute/shutdown, compileall/JS/diff passed. Tag `v0.1.0-beta.6` (`6de8531`) and GitHub pre-release confirmed and created by owner.
- v0.2.0 entry-criteria prep (post beta.6): Plugin API compatibility policy (`docs/Plugin-API-compatibility-policy.md`), plugin development guide, English quick start `docs/QUICKSTART.md`, migration guide, v0.2.0 entry-criteria tracking (criteria #4/#5 met).
- P0 audit (v0.2.0 criterion #2): found 1 P0—`run_command` allowed `python -c`/`node -e` inline code execution (prefix allowlist + no inline check; could read `.env`/write out of bounds/bypass permissions), fixed in `74e1829` (`_has_inline_interpreter_code` preflight; reject `python -c` only without `-m`, so `python -m pytest -c config` is not false-rejected). Other four categories (secrets/out-of-bounds/false completion/plugin overreach) SOUND. Full regression `856 passed, 1 warning`, CI fully green.
- `v0.1.0-beta.7` security patch: version `0.1.0b7`; contains only `run_command` P0 fix (no feature change); Release Notes, CHANGELOG, README, status docs updated. Tag `v0.1.0-beta.7` (`49267ba`) and GitHub pre-release confirmed and created by owner.
- O3 Provider compatibility matrix (2026-07-25): added [`Provider-compatibility-matrix.md`](Provider-compatibility-matrix.md); `catalog.export_compatibility_matrix()` and `tests/test_provider_matrix.py` bind catalog/routing/error codes; `SECURITY.md`, README, QUICKSTART, plugin guide, local LLM, `providers.yaml.example` unify “permissions ≠ sandbox / unverified does not participate in upgrade” wording.

## 3. Current unfinished priorities

In order:

1. **O4** External users and real-task validation: redacted feedback templates, ≥10 installs / ≥5 real projects; B5.4 resumes only after owner re-authorization.
2. `v0.2.0` entry criteria: #1 external users, #3 real benchmarks (awaiting external input/owner authorization); #2/#4/#5 already met. See [`v0.2.0-entry-criteria.md`](v0.2.0-entry-criteria.md). The O3 compatibility matrix supports the offline side of criterion #3; real comparisons still await authorization.

Detailed historical goals: [`archive/completed-beta/version-plan-v0.1.0-beta.3-to-beta.6.md`](archive/completed-beta/version-plan-v0.1.0-beta.3-to-beta.6.md). Current optimization order: [`MAO-optimization-and-follow-up-plan.md`](MAO-optimization-and-follow-up-plan.md).

## 4. New-device recovery steps

```bash
git clone https://github.com/Wanbinyu/multi-agent-orchestrator.git
cd multi-agent-orchestrator
git status --short --branch
git pull --ff-only
python -m venv .venv
```

After activating the environment:

```bash
python -m pip install -e ".[test]"
python -m pytest -q
mao --version
mao web --help
```

Do not copy the old machine’s `.env` into public locations. Reconfigure needed Provider keys locally on the new device.

## 5. Fixed steps at the start of each work session

```bash
git status --short --branch
git fetch origin
git rev-list --left-right --count HEAD...origin/main
```

Then:

1. Read this document and the current version execution checklist.
2. Confirm the origin of working-tree changes; do not roll back modifications unrelated to the current task.
3. Mark only one step as in progress.
4. Record acceptance criteria and targeted tests before changing code.
5. After changes, run targeted tests first, then expand regression by risk.

## 6. Common run commands

Install users:

```bash
pipx install git+https://github.com/Wanbinyu/multi-agent-orchestrator.git
mao
mao web
pipx upgrade multi-agent-orchestrator
pipx uninstall multi-agent-orchestrator
```

Source development:

```bash
python -m pip install -e ".[test]"
mao
mao web --no-open
```

One-shot tasks:

```bash
mao run "Check the current project and report risks"
```

## 7. Verification commands

```bash
python -m pytest -q
python scripts/verify_distribution.py
python scripts/first_run_acceptance.py
python -m pytest -q tests/test_sanitize_feedback_text.py
python -m compileall -q src tests scripts run.py
node --check src/ui/static/js/app.js
node --check src/ui/static/js/chat.js
git diff --check
python -m pip_audit
```

Build release packages:

```bash
python -m build --wheel --sdist
python -m twine check dist/*
```

Real Provider smoke is not part of automatic CI; before calling paid models, confirm key, model, expected attempts, and cost boundaries.

## 8. Documentation update rules

After each Beta subtask completes, also update:

- Current status and top task in this document.
- Checkboxes, test results, and residual risk in the corresponding version execution checklist.
- Update `MAO-architecture-overview.md` when architecture is affected.
- Update the version plan when version goals change; do not maintain the same facts across multiple old plans.
- On release, update CHANGELOG and immutable Release Notes.

Completed whole-stage plans move into `docs/archive/`, but the current execution checklist must not be archived until the version is released.

## 9. Security operations

- Keys live only in local `.env`; never write them into Markdown, Issues, logs, or command output.
- Keys that appeared in chat should be treated as leaked and rotated in the Provider console.
- Do not run install scripts or plugins from unknown repositories.
- Do not automatically change GitHub visibility, tags, or releases; those need separate owner confirmation.
- Do not reset, checkout, or overwrite-write the user’s existing Git changes.

## 10. Current continuation entry

`v0.1.0-beta.7` is released; O1–O3 are done. Currently execute **O4** (external users and real benchmarks) in [`MAO-optimization-and-follow-up-plan.md`](MAO-optimization-and-follow-up-plan.md), then advance `v0.2.0`. B5.4 real multi-model evaluation remains separately paused. See [`v0.2.0-entry-criteria.md`](v0.2.0-entry-criteria.md) and [`Provider-compatibility-matrix.md`](Provider-compatibility-matrix.md).

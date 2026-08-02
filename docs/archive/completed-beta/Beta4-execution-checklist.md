# v0.1.0-beta.4 Execution Checklist

**Status**: Completed; `v0.1.0-beta.4` pre-release published 2026-07-19

**Goal**: Engineering transparency, session recovery, and long-task context—users can understand task plans, execution evidence, verification results, block reasons, and context behavior without asking the model

**Plan baseline commit**: `cf36fad` (after `v0.1.0-beta.3` release)

**Baseline tests**: `558 passed, 1 warning`; latest full-suite results for the working tree are in the completion notes at the end of this document

## 0. Pre-start checks

- [x] `git status --short --branch` is clean.
- [x] Read: `docs/archive/completed-beta/version-plan-v0.1.0-beta.3-to-beta.6.md` (2026-07-17 revision), `docs/project-progress-and-key-operations.md`.
- [x] Confirm beta.4 new scope: interference metrics, L0/L1/L2 layering, and Reviewer information-restriction verification are written into the version plan.
- [ ] Do not run real paid model calls without owner confirmation; offline benchmarks always use fixed transcript text.

## 1. B4.1 Engineering record visualization

### Goal

CLI and Web can expand WorkPlan, Evidence, VerificationGate, RequirementCheck, CompletionAudit, and residual_risks without calling a model.

### Main files

- `src/ui/static/js/chat.js`
- `src/ui/static/css/style.css`
- `src/cli/chat_command.py`
- `tests/test_ui.py`, `tests/test_run_cli.py`

### Tasks

- [x] Web engineering-record entries add a "Details" expand: plan steps (with status), evidence list, verification gates, requirement checks, completion audit, residual risks, and metrics; data from existing `GET /api/chat/sessions/{id}/runs/{run_id}`, loaded only on click.
- [x] Default collapsed to keep the UI clean; long lists (evidence/gates) are bounded and show totals.
- [x] No horizontal overflow after expand at 390px mobile viewport (responsive CSS: `overflow-wrap: anywhere`, no fixed widths; real-device visual acceptance still needs manual smoke).
- [x] CLI adds `/runs [run_id]`: without args lists recent runs for this session; with args shows the full engineering record for that run; pure local read, no model calls.

### Acceptance

- [x] Expanded fields match RunJournal persistence; evidence counts match summary lines.
- [x] `node --check` and UI contract tests pass; CLI new command has help and completion.

### B4.1 completion notes (2026-07-17)

- Web: `chat.js` engineering-record entries add "Expand details / Collapse details"; on click, lazily loads the full record via `/api/chat/sessions/{id}/runs/{run_id}`; details render by objective, classification and bounds, work plan, evidence, verification gates, requirement checks, completion audit, decisions, modified files, residual risks, and metrics; evidence/gates/decisions show at most 50 items with totals in the title; cache invalidates when run status changes so the next expand reloads.
- CLI: add `/runs [run_id]` listing the latest 10 runs or showing one full engineering record; pure local RunJournal YAML reads, no model calls; help and completion generated uniformly by `SLASH_COMMANDS`.
- Tests: `test_chat_runs_command.py` adds 4 cases (list, full detail, missing run, empty session); `test_chat_router.py` extends detail endpoint contract locking 11 top-level fields consumed by the frontend.
- Verification: `python -m pytest -q` → `562 passed, 1 warning`; `compileall`, `node --check`, and `git diff --check` passed.
- Residual risk: 390px viewport only has responsive rules; no real mobile visual acceptance yet.

## 2. B4.2 Compaction events and context transparency

### Goal

Context usage, compaction count, budget source, estimate error, and recent compaction events are visible in CLI/Web.

### Main files

- `src/core/compactor.py`
- `src/core/agent.py` (`get_context_status`)
- `src/core/session.py`
- `tests/test_compactor*.py`, `tests/test_agent*.py`

### Tasks

- [x] Persist compaction events (time, before/after token estimates, dropped message count, layer used), bounded on the session side.
- [x] `get_context_status` exposes compaction count and recent events; when Provider returns usage, record estimate vs actual prompt token error (bounded).
- [x] CLI `/context` and Web context endpoint show the above fields.

### Acceptance

- [x] After one compaction, event records match message-count changes; events are not written into the session message stream.
- [x] No extra UI noise when there is no compaction.

### B4.2 completion notes (2026-07-17)

- `Session` adds `compaction_events` and `usage_observations` (each bounded to 20); old session YAML without these fields loads as empty defaults.
- Agent records time, before/after token estimates, merged message count, and layer (currently `summary`; extended after B4.4 layering) on each real compaction; events go only into session observation fields, not the message stream.
- `StreamChunk` adds `usage_estimated`: Anthropic/OpenAI/llama.cpp fallback estimates set True; real Provider usage stays False; 3 sync and 3 stream sites record estimate vs actual prompt tokens when real usage arrives, once per request.
- `get_context_status` exposes `compaction_count`, `recent_compactions` (latest 3), and `usage_observations` (latest 3, with `error_pct`).
- CLI `/context` appends corresponding lines only when compaction or observations exist; Web context panel adds "Compaction" and "Estimate error" rows, hidden without data (hover shows estimated/actual values).
- Tests: `test_context_observability.py` adds 8 cases (boundedness, old-session compatibility, compaction events, real usage observation, StreamChunk defaults, status exposure, no noise).
- Verification: `python -m pytest -q` → `570 passed, 1 warning`; `compileall`, `node --check`, and `git diff --check` passed.
- Residual risk: estimate error depends on Provider returning real usage; local models (llama.cpp) with input usage 0 produce no observation.

## 2.5 B4.S Real-task stability prerequisites (current)

### Goal

From the real frontend task in `sessions/20260718-070404-246880-770695`, close the loop from “generate many files” to “correct classification, multi-model execution, first-round runnable, automatic verification, and trustworthy reports.” Full evidence, operating flow, and six implementation slices are in [`real-task-stability-improvement-plan.md`](real-task-stability-improvement-plan.md).

### Current issues

- [x] “给我做一个纯前端项目” is stably classified as `build/high/deep` with Plan/collaboration eligibility.
- [x] After `unclassified` actually writes project files, effective kind and audit depth escalate dynamically; no longer `audit: not_required`.
- [x] Missing pages, wrong route targets, and relative imports are now blocked by B4.S3 deterministic closure gates; real redacted-fixture replay is left to B4.S6.
- [x] Bad Mock, login failure, empty data, console errors, and mobile layout issues are now stably blocked by B4.S4 real browser gates.
- [x] Structured cwd, cross-platform commands, closure checks, and runtime smoke are done; full real-task chain replay is left to B4.S6.
- [x] All RunJournals can now aggregate create/modify/verify/risk and real token data such as 190,289/69,121 without rebuilding from compacted messages.

### Execution order

- [x] B4.S1: Intent classification and observed-mutation dynamic risk/audit escalation.
- [x] B4.S2: Portable verification executor with cwd and script discovery.
- [x] B4.S3: Multi-model task contract and import/route closure for high-risk frontend projects.
- [x] B4.S4: Browser smoke for login, main routes, data, console, and 390px.
- [x] B4.S5: Truthful reports and token metrics from all RunJournals.
- [x] B4.S6: Smart-mining redacted-fixture replay and release gate.

### Acceptance

- [x] Real original sentences enter `build/high`; Plan/collaboration policy is visible.
- [x] Any actual project write cannot complete with `audit: not_required`; Session-root `response.md` excluded.
- [x] Fixed frontend fixtures pass first-round build, command gates, and browser smoke.
- [x] Bad Mock and missing-page/wrong-import failure variants stay blocked; missing script deps continue to be covered by S2.
- [x] Final summary fully covers create, fix, verify, fail, token/cost, and residual risks.

### B4.S6 completion notes (2026-07-18)

- `tests/fixtures/smart_mining/` is a public redacted fixed sample; `StabilityReplayRunner` offline chains classification, four-role multi-model contract, closure, real npm commands, Playwright, completion audit, and local report with Provider call count 0.
- Good sample is `completed` with all four verification gates passing; bad Mock and missing-route samples are both `blocked`, first-round runnable rate 0.
- Windows `npm.CMD` is resolved via `shutil.which` only after direct exec raises `FileNotFoundError`, still with `shell=False`.
- CI adds `python scripts/replay_smart_mining.py`. Full regression `683 passed, 1 warning`; `compileall`, JavaScript syntax, and diff hygiene passed.

## 3. B4.3 Session recovery confirmation

### Goal

When loading a session, detect `running`, `blocked`, and unfinished plans; continue only after explicit user confirmation.

### Main files

- `src/cli/chat_command.py` (`/load`)
- `src/ui/routers/chat.py` (session detail endpoint)
- `src/ui/static/js/chat.js`
- `tests/test_session_recovery.py` (new)

### Tasks

- [x] Detect interrupted sessions: latest RunJournal is `running`/`blocked`, or the plan has unfinished steps.
- [x] CLI `/load` and Web open-session show a recovery banner (status, block reason, unfinished step count).
- [x] Continue only after user confirmation; continue/abandon decisions are written to RunJournal `decisions`.
- [x] Recovery never auto-replays completed tasks or rewrites files.

### Acceptance

- [x] Under interrupted fixtures, CLI/Web both show prompts and do not continue by default.
- [x] After confirm, only a new run is created and unfinished step checkpoints are claimed; completed steps and existing files serve only as evidence that auto-replay is forbidden.

### B4.3 completion notes (2026-07-18)

- Added `SessionRecoveryManager`: checks only the latest RunJournal; `running`, `blocked`, or any unfinished plan enters pending confirmation; old Sessions without recovery fields default to empty history for compatibility.
- CLI `/load` shows status, reason, and unfinished steps; adds `/resume continue|abandon`. Web session detail returns the same recovery state; banner disables input and send until confirmed; sync/stream message endpoints hard-block with 409.
- Continue/abandon itself only writes local Session and RunJournal decision—no Provider calls, no tools. Interrupted running runs are sealed as blocked; abandon only blocks unfinished steps and does not roll back completed steps or existing files.
- After continue, the first message creates a new run and claims a one-shot recovery checkpoint listing completed/unfinished steps and existing files; system prompt forbids auto-replay; RunJournal `metrics.recovery` is auditable.
- Tests: recovery, CLI, Web, Agent, and adjacent regression `77 passed, 1 warning`; full suite `689 passed, 1 warning`. Real browser at 1280×720 and 390×844: no horizontal overflow, controls disabled before confirm and restored after, console errors 0.

## 4. B4.4 Context 3 layered compaction

### Goal

Implement layered compaction with dedup, local summary, old-turn summary, and task checkpoints; compaction quality is measurable.

### Main files

- `src/core/compactor.py`
- `src/core/summarizer.py`
- `src/core/context_budget.py`
- `tests/test_compaction_layers.py` (new), `scripts/bench_compaction.py` (new)

### Tasks

- [x] L0/L1/L2 layers: L0 index/placeholder (single-line refs), L1 structured summary, L2 recent full text; summaries retain session output files and run_id refs, expandable on demand via tools.
- [x] Pre-compaction dedup: keep only one copy of duplicate plain-text tool results and file reads; do not dangerously dedup structured tool blocks.
- [x] Summary Schema: requirements, decisions, evidence, files changed, todos, risks; parse failure falls back to existing plain-text behavior and is recorded.
- [x] Quality gate: Schema validation + key-entity retention (requirement tags, filenames, run_id); results written into compaction events.
- [x] Interference metrics: post-compaction task-relevant token share and entity coverage, supporting offline replay.
- [x] Task checkpoints stay fixed during compaction and are not absorbed by summaries.

### Acceptance

- [x] After three consecutive compactions, core requirements, file changes, and evidence refs remain (fixed-transcript offline replay).
- [x] 32K/64K/128K/200K four-window benchmarks pass agreed thresholds; interference is measurable and replayable.
- [x] Illegal summary Schema falls back safely without orphaned tool blocks.

### B4.4 completion notes (2026-07-18)

- `ContextCompactor` now stably folds history into a single L0 old-summary index, a single L1 summary, and L2 recent full text. L1 is content-hash persisted to `output/context/compaction-*.json`; L0 keeps artifact, file, and run_id refs expandable via existing read tools.
- L1 Schema covers requirements, decisions, evidence, files_changed, todos, risks, run_refs, and output_files. Illegal JSON/Schema keeps the model’s original plain text and marks fallback; if summary call fails or is empty, old messages are fully retained.
- Pre-compaction dedup only for same-role same-body messages without content blocks/provider payload. Native tool_use/tool_result continue to split on pairing boundaries; structured blocks are not deduped in ways that could break protocol.
- Extract `KEEP:` requirements, file paths, and run_id from direct history; deterministically backfill if the summary omits them. Events record Schema status, fallback reason, entity retention, relevant-token ratio, dedup count, artifact and checkpoint counts.
- Agent auto-generates bounded `[MAO_TASK_CHECKPOINT]` JSON from the current RunJournal with objective, run_id, unfinished/completed steps, evidence, files, and risks; each compaction replaces the old checkpoint and does not hand it to summary absorption.
- `scripts/bench_compaction.py` runs three compactions at each of 32K/64K/128K/200K. All Provider calls 0, key-fact retention 1.0, final layers L0/L1/L2; final task-relevant token ratios 0.002339–0.003694. Targeted regression `52 passed`, full suite `695 passed, 1 warning`.

## 5. B4.5 Project index incremental reuse

### Goal

Incrementally reuse project tree, file summaries, and content-hash index so repeated reconnaissance re-reads zero content.

### Main files

- `src/core/memory.py` (or new `src/core/project_index.py`)
- `src/tools/` (`project_tree`, `search_project_files`)
- `tests/test_project_index.py` (new)

### Tasks

- [x] Persist project tree + file summary + content-hash index to local cache.
- [x] Incremental refresh: zero content reads when fast metadata is unchanged; on metadata change use content hash to decide whether to rebuild summaries; structural changes update locally.
- [x] Reconnaissance and search prefer the index; cache reads go through existing cached rules so reconnaissance evidence is not expanded repeatedly.

### Acceptance

- [x] Unchanged project second reconnaissance has zero content reads; single-file change re-reads only that file.
- [x] On index corruption, fall back to full scan without blocking chat.

### B4.5 completion notes (2026-07-18)

- `FileIndex` upgraded to v2: records normalized project root, full directory/tree paths, per text-file mtime, size, SHA-256, symbols, summary, snippet, and last-refresh stats; old v1 indexes safely rebuild due to missing root/hash.
- Unchanged mtime+size+hash entries are reused with content reads = 0; metadata change reads only that file—if hash unchanged only metadata updates, if hash changes rebuild symbols/summary. Add, delete, root switch, and force refresh are counted separately.
- Index YAML uses atomic temp-file replace. Corrupt YAML marks `cache_recovered` and full-refreshes; single-file read failure keeps usable old entries and counts errors without blocking chat.
- `project_tree` by default incrementally refreshes and renders from cached tree; falls back to live scan when explicitly showing hidden files. `search_project_files` cheap-refreshes each time and adds `path` project-root parameter to prevent index crosstalk from session output dirs or another project.
- Tool results pass cross-turn zero-read hits into existing Agent/Worker cache-evidence rules via `metadata.cached`. Web index status adds root and last_refresh; CLI shows actual read/reuse counts.
- Acceptance covers second-pass `read=0`, single-file `read=1`, metadata update with same hash, delete, corrupt recovery, project-root switch, and tree/search cache. Targeted and adjacent regression `141 passed, 1 warning`, full suite `701 passed, 1 warning`.

## 6. B4.6 Reviewer information-restriction verification

### Goal

Reviewer independently verifies against requirements and evidence without reading Worker self-narration.

### Main files

- `src/core/reviewer.py`
- `src/core/collaboration.py`
- `tests/test_reviewer.py`

### Tasks

- [x] Add restricted verification mode: inputs are original requirements, plan, evidence, verification gates, and written-file list; exclude Worker output body text.
- [x] Verification mode is written to RunJournal; config can switch back to full mode.
- [x] Deterministic audit constraints unchanged (Reviewer output cannot override audit).

### Acceptance

- [x] Restricted-mode prompt contains no Worker body (contract test).
- [x] RunJournal records verification mode; both modes pass existing review regressions.

### B4.6 completion notes (2026-07-18)

- Reviewer adds `input_mode: restricted|full`; example config defaults to restricted; missing or illegal fields conservatively fall back to restricted for old private-config compatibility.
- restricted prompt keeps original requirements, TaskPlan/frontend contract, roles/models/status, file list, deterministic acceptance evidence, real command evidence, and RunJournal Evidence, VerificationGate, RequirementCheck, and CompletionAudit; does not concatenate `TaskResult.content` or `response.content`.
- full mode only for workflows that explicitly need Worker body integration; preserves prior behavior. Both prompts explicitly mark the actual mode.
- RunJournal `metrics.collaboration.reviewer_input_mode` and the reviewer role entry record the actual mode. Even if Reviewer returns passed, failed Workers or `audit.can_complete=false` still deterministically become not-passed.
- Sentinel contracts verify restricted prompt has no Worker body but has files, commands, and direct evidence; full prompt can see body text. Targeted and adjacent regression `88 passed`, stage full suite `703 passed, 1 warning`.

## 7. B4.7 Release closeout

- [x] Update `CHANGELOG.md`, version `0.1.0b4`, `RELEASE_NOTES_v0.1.0-beta.4.md`.
- [x] Full tests, compileall, JavaScript syntax, diff hygiene, pip-audit, gitleaks pass.
- [x] Build wheel/sdist and `twine check`; empty-dir isolated install and `/health` pass.
- [x] Remote Windows/Ubuntu CI passes.
- [x] Create Tag and GitHub pre-release after owner confirmation.

### B4.7 local completion notes (2026-07-18; pre-release re-review 2026-07-19)

- Version bumped to `0.1.0b4`; `python run.py --version` prints `MAO 0.1.0b4`.
- Full test set is `722 passed, 1 warning`; due to host single-command ~30s limit, local runs split into core `705`, real browser `12`, stability replay `4+1`; collection total and sum of three groups are both 722. Only warning is Starlette/httpx upstream deprecation; remote CI still runs single full pytest.
- `scripts/replay_smart_mining.py` passes: good fixture completed, broken Mock and missing-route fixtures blocked, Provider calls 0.
- `scripts/bench_compaction.py` passes: three compactions each at 32K/64K/128K/200K, key-fact retention all 1.0, Provider calls 0.
- `scripts/verify_distribution.py` passes: wheel/sdist content contract, `twine check`, clean venv install without inheriting system packages, empty-dir CLI and Web `/health` all pass.
- `pip-audit -r requirements.txt` found no known vulnerabilities. gitleaks 8.24.3 official SHA-256 verified; 60 historical commits, current tracked diff, and new source/scripts/tests/docs/permission examples had no leaks.
- Python compileall, JavaScript syntax, and `git diff --check` passed; final quick recheck after version/docs closeout also passed.
- First remote CI hit path-separator assertion differences on Ubuntu and system-browser cold-start timeout on Windows 3.12; `c0caecb` unified diagnostic paths, pinned Chromium install, and relaxed public-replay action timeouts.
- After fix, [CI 29672684859](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29672684859) passed on Windows/Ubuntu, Python 3.11/3.12, and the security job.

### Pre-release diff re-review fixes (2026-07-19)

- Permission confirmation only accepts the current pending request ID and clears after complete/cancel to avoid long-session leaks and unknown-ID pollution.
- Recovery manager seals contradictory records where “run completed but plan unfinished” as blocked; paths inside native tool-use blocks enter compaction entity retention; plain-text fallback uses `.txt` artifacts.
- Reviewer strictly validates JSON field types and keeps real usage on failure paths; collaboration plans cap at 24 subtasks to prevent unbounded Provider fan-out from model output.
- Frontend closure rejects illegal dependency structures and HTML assets outside the project root; smoke rejects 404 ready, missing viewport, unexplained failure, and interpreter inline server code.
- Offline replay stays blocked if any deterministic pre-gate fails; today’s report no longer applies “Provider already configured” facts across sessions.
- Web rejects concurrent messages and active delete on the same session; mode switches sync the persistent Session; failed frontend optimistic switches roll back the display.
- Distribution acceptance uses a truly clean install that does not inherit system packages; CI verifies official SHA-256 after downloading gitleaks before scanning.

## 8. Recommended commit boundaries

1. `feat: complete beta.4 engineering stability contracts` (code, config, scripts, and tests as one runnable boundary so Agent/Journal/tool contracts are not split)
2. `docs: prepare beta.4 release candidate` (README, CHANGELOG, architecture, plans, verification, and Release Notes)

Each commit must independently pass targeted tests; do not wait until the end to fix all regressions at once.

## 9. Current next steps

B4.1–B4.7, Grok Build base behavior contracts, upstream-absorption first slice, and B4.S1–B4.S6 are all completed and released. Next enter B5.1 of [`Beta5-execution-checklist.md`](Beta5-execution-checklist.md): first establish reproducible benchmark contracts and an offline harness; do not write routing policies without data validation first.

## 10. Usage-feedback fix notes (2026-07-17 to 2026-07-18)

Chained issues from real beta.3 use: relay (aggregate forwarder) returned empty responses for the new catalog model ID `kimi-k2.7-code`; empty responses were misclassified as `completed`; mid-sentence “帮我先做/把……搭建好” was classified as `unclassified` and entered read-only. Fixed:

- **Empty-response guard hole** (`fix: fail silent empty model responses`): when there is no parseable text and no tool call, any-round token use or first-round zero-token is treated as `failed` with actionable guidance (check Provider connection and model ID); zero-token empty responses after tool rounds keep prior wrap-up behavior. Empty assistant messages are no longer written to session history. Regression: `test_empty_response_guard.py` 4 cases.
- **Classifier mid-sentence forms** (`fix: recognize mid-sentence build phrasing`): `_EXPLICIT_WRITE_PATTERNS` adds “帮我……做一个/套/份” and “把……搭建好/做出来” patterns; excludes read-only forms such as “帮我看看怎么做”, “做版本对比”, “把搭建的事告诉我”. Regression: `test_task_intent_classifier.py` 8 cases.
- **Kimi K3 added to catalog** (`feat: add kimi k3 to model catalog`): model ID `kimi-k3`, 1M context; metadata from 2026-07-16 press reports, `metadata_source="unverified"`, `context_window_source="unverified_press_2026-07"`, pending official-doc item-by-item verification.
- **Permission mode decoupling**: in real use, `[auto] > 帮我创建好` had write tools hidden by a second-layer conservative `unclassified` policy. Now `auto` can directly run non-read-only tools, `approve` only asks on non-read-only tools, `readonly` auto-reads but rejects writes/commands; tasks that explicitly do not modify still stay read-only. Unknown tasks follow session permissions via `permission_follows_session` but are not treated as engineering changes that trigger wrong verification gates; “帮我创建好” is recognized as `build` directly. Sync non-streaming `approve` still safely rejects non-read-only calls (cannot wait interactively) and hints to use streaming CLI/Web.
- Leftover: whether the user’s local relay (`api.va11.icu`) supports `kimi-k3`/`kimi-k2.7-code` must be confirmed by the user with the relay provider; MAO catalog is maintained with official moonshot.cn model IDs. Full regression `589 passed, 1 warning`.

## 11. Grok Build base behavior contract prerequisites (2026-07-18)

- Project rules: hierarchical discovery of `AGENTS.md`, `CLAUDE.md`, `.mao/rules`, and Grok/Claude/Cursor-compatible dirs; caps of 20 files, 8K/file, 32K total; sources and diagnostics enter RunJournal; same rule package goes to Agent/Orchestrator/Worker/Reviewer.
- Permission rules: add `deny > ask > allow > session default` engine and `config/permissions.yaml.example`; normalize Windows paths; cover composite commands segment-by-segment; complex shell degrades to ask; Agent and Worker share the execution boundary.
- Plan mode: Session persists `inactive/pending/active/awaiting_approval` and plan artifacts; before approval forbid writes, commands, MCP write ops, write Workers, and automatic response files.
- Multi-model Council: after main Agent real read-only recon, reconnaissance/architect/critic/synthesizer four roles deliberate without tools; single-role failure keeps draft and records diagnostics.
- CLI/Web: CLI adds `/plan enter/show/revise/approve/cancel`; legacy `/plan <request>` stays compatible; Web adds Plan status strip and equivalent API/controls; after approve, hand back to the normal multi-model execution chain.
- Browser acceptance: 1280×720 and 390×844 no horizontal overflow; Plan status strip does not cover the input area; console error-free; fixed pending state showing revise/approve buttons too early.
- Verification: `python -m pytest -q` → `615 passed, 1 warning`; `compileall`, `node --check`, `git diff --check` passed; precise key-fragment scan clean; no real paid models called.
- Detailed contracts, risks not copied, and follow-on Skills/Plugins/Hooks roadmap: [`Grok-Build-behavior-contract-integration.md`](Grok-Build-behavior-contract-integration.md).

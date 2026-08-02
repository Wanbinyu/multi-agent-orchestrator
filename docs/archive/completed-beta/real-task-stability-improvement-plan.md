# MAO Real-Task Stability Improvement Plan

**Status**: B4.S1–B4.S6 completed and passed the offline release gate; next return to B4.3 session recovery confirmation

**Goal**: Raise “create a frontend project” from generating many files to a full engineering delivery that routes correctly, collaborates across models, is first-round runnable, auto-verifies, explains failures, and produces auditable results.

**Real acceptance sample**: `sessions/20260718-070404-246880-770695`, target project `G:\MAO_test`

## 1. Established standard operating methods

### 1.1 User operating flow

Prefer persistent Plan mode for complex engineering tasks:

```text
mao
/plan enter Create a project under G:\target-dir, and state tech stack, scope, and acceptance criteria
# Send full requirements; wait for read-only recon and multi-model plan
/plan show
/plan revise <revision notes>   # optional
/plan approve             # only after approve enter the implementation chain
/runs                     # view evidence, verification gates, and block reasons
/context                  # view token budget and compaction status
```

WebUI uses the top `Plan` control with the same flow as CLI: enter → generate plan → revise or approve → normal execution. Legacy `/plan <request>` remains a one-shot collaboration entry, but large projects default to recommending persistent Plan.

### 1.2 Rules and permissions

- Project rules: place `AGENTS.md`, `CLAUDE.md`, or `.mao/rules/*.md` at the target project root or subdirectories.
- User permissions: `config/permissions.yaml`; project permissions: `<project>/.mao/permissions.yaml`.
- Permission priority: hard read-only/Plan bounds → `deny` → `ask` → `allow` → session mode default.
- `auto` auto-executes allowed tools; `approve` auto-reads and asks on non-read-only tools; `readonly` rejects all non-read-only tools.
- Main Agent, Orchestrator, Worker, and Reviewer receive the same project rules; main Agent and Worker share the permission engine at the execution boundary.

### 1.3 Multi-model engineering flow

```text
Read-only recon
  → Planning Council (evidence check / architecture / critique / synthesis)
  → User approve
  → Orchestrator splits tasks and ownership
  → Worker implements and verifies
  → Reviewer reviews against requirements and evidence
  → CompletionAudit decides completed or blocked
```

No model prose can replace real tool evidence. Change tasks need at least targeted verification and adjacent regression; high-risk new projects also need integration, full, runtime smoke, and usage notes. When verification is incomplete, status must stay `blocked`.

## 2. Real-task findings 2026-07-18

### 2.1 What went well

- First round generated 33 files, then filled 4 pages and fixed 7 API imports, continuously using read, write, edit, and search tools.
- Current `npm exec tsc -- --noEmit` passes.
- Vite in-memory production build passes: 3710 modules transformed and bundled without writing `dist`.
- Desktop UI has complete menus, charts, lists, login page, and good visual completeness.
- After hitting command permission limits, did not forge build results; final change turn stayed `blocked` and marked verification gaps.
- Long session continued fixing and summarizing after 8 automatic compactions.

### 2.2 Delivery-blocking issues

| Severity | Issue | Evidence and impact |
|---|---|---|
| P0 | Mock architecture error | Axios request interceptor returns Mock response instead of request config; browser continuously throws `method.toUpperCase`; login fails, data tables empty, page switches report network errors. |
| P1 | First-round project not runnable | Missed 4 route pages; 7 API files had wrong imports; required two user error rounds to fix. |
| P1 | Explicit build request classified as `unclassified` | Original “给我做一个纯前端的项目” did not hit `explicit_write`, so no plan, no collaboration, no deep verification. Classifier replay still reproduces. |
| P1 | Actual writes did not escalate audit | `unclassified` wrote 33 project files under auto, but RunJournal had `audit: not_required` and status wrongly became `completed`. |
| P1 | Verification commands not executable | Model generated `cd ... && npx ... | head`, incompatible with Windows/whitelist; second command also lacked correct working directory/executable resolution. |
| P2 | Engineering quality tools ineffective | `package.json` declares lint but ESLint not installed; no test scripts, test files, or Git baseline. |
| P2 | Insufficient responsive layout | At 390px fixed sidebar takes most width; main content compressed to a narrow column. |
| P2 | Final report inaccurate | “今日操作整理” only emphasized the last 7 import fixes, omitted first generation, 4-page fill-in, and runtime faults; misdiagnosed network errors as Mock env vars not enabled. |
| P2 | Low token utilization | ~10 turns ~190,289 input, 69,121 output, cost about `$0.259410`; first large build never entered multi-model division of labor and verification chain. |

This sample mainly validated continuous generation with “main model + tools,” not MAO’s multi-model engineering capability, because first-round `collaboration_allowed=false`.

## 3. Root-cause boundaries

### 3.1 MAO must fix

1. Insufficient natural-language build-intent coverage: mid-sentence commands like `给我做一个`, `现在给我做` did not enter build.
2. Task classification disconnected from actual behavior: after project writes occurred, risk and verification depth were not dynamically raised.
3. Large builds wrongly went single-Agent; Orchestrator/Worker/Reviewer were not called.
4. Command tools lack stable structured `cwd`, cross-platform command templates, and script discovery.
5. Frontend completion audit only looks at file/command evidence—no browser runtime error, route, or data-render gates.
6. Session summaries depend only on current context and cannot reliably aggregate all RunJournal and fix history.

### 3.2 Generated project templates/models must improve

1. Mock layer must not return response objects as Axios request config; use custom adapter, mock library, or separate service.
2. Route references must check target-file closure before completion.
3. `package.json` scripts, devDependencies, and config files must be consistent.
4. Large screen, 390px narrow screen, login, and all main-nav routes must enter the smoke list.
5. New projects default to establishing a Git baseline unless the user explicitly forbids; commits still need separate authorization.

## 4. Follow-on execution plan

### B4.S1 Intent classification and dynamic risk escalation (P0)

Main files: `src/core/engineering/classifier.py`, `src/core/engineering/audit.py`, `src/core/agent.py`.

- [x] Add natural expressions such as `给我做一个/做一套`, `现在给我做`, `在 <path> 做一个项目`.
- [x] Regress on real sample original sentences; also cover read-only counterexamples like “告诉我怎么做一个项目”.
- [x] When the first project-file write of the turn occurs, record observed mutation; `unclassified/answer` must not continue as no-change audit.
- [x] Multi-file, new directory, or dependency-manifest writes trigger effective kind/risk escalation; deep verification required once build thresholds are met.
- [x] Count `response.md` under the Session output directory separately from target project files; answering archives must not masquerade as project changes.

Acceptance: real original sentences stably classify as `build/high`, enabling Plan/collaboration; even if classification misses, writing 2+ project files cannot complete with `audit: not_required`.

Completion notes (2026-07-18):

- Real smart-mining original sentences, `现在给我做一套`, and `在 G:\MAO_test 中做一个项目` all enter `build/high/deep` and declare Plan and collaboration eligibility.
- RunJournal upgrades to v3: keeps initial `intent`, adds audit-only `effective_intent` and `observed_mutation`; dynamic escalation does not expand this turn’s tool permissions.
- A single real project file escalates at least to `change/medium/standard`; two different files, dependency manifests, or new directories escalate to `build/high/deep`.
- Successful write Evidence, Worker file traces, and end-of-turn file lists jointly participate in observation; failed, skipped, and Session-root `response.md` do not count as project changes.
- CLI/Web display kind, risk, verification depth, and project-file count after actual-write escalation.
- Verification: targeted tests `79 passed`; adjacent Agent/Worker/collaboration/Web regression `89 passed, 1 warning`; full suite `633 passed, 1 warning`.

### B4.S2 Portable verification executor (P0)

Main files: `src/tools/worker_tools.py`, `src/tools/registry.py`, `src/core/worker.py`, permission rules.

- [x] Add normalized `cwd` for `run_command`; forbid models concatenating working directory with `cd &&`.
- [x] Discover existing scripts from `package.json`; generate argv arrays or safe single commands without platform-specific shell tricks like `head` or redirects.
- [x] Cover `npm run build`, `npm run lint`, `npm test`, and Python verification on Windows/Ubuntu separately.
- [x] Whitelist/permission denial returns actionable alternate commands; model may correct once at most—no repeated blind retries.
- [x] Frontend builds prefer in-memory/temp-output verification to avoid polluting the user project.

Acceptance: paths with drive letters such as `G:\MAO_test` can run builds after authorization; command traces include cwd, exit code, truncated output, and permission decisions.

Completion notes (2026-07-18):

- `run_command` adds structured `cwd` and Vite `temporary_output`; still uses argv arrays, `shell=False`; rejects `cd &&`, pipes, redirects, command chaining, and background execution.
- Add read-only `discover_project_commands` discovering commands from actual `package.json`, lockfiles, pytest config, and test dirs—does not invent non-existent scripts.
- Discoverer checks script deps for ESLint, TypeScript, Vite, Vitest, Jest, Playwright, etc.; declared lint without installed ESLint is marked unavailable and does not enter recommended verification order.
- Command traces include normalized cwd, argv, exit code, duration, original stdout/stderr lengths, truncation status, temp-output cleanup status, and permission decisions; verification gates also carry cwd.
- Whitelist, cwd, shell-syntax, and permission precheck failures all return stable error codes and alternate actions; after first failure only one correction is allowed; third call is deterministically rejected.
- Precheck rejection no longer masquerades as test failure and does not generate VerificationGate.
- Windows/Ubuntu CI share argv-array tests covering `npm run build`, `npm run lint`, `npm test`, and `python -m pytest -q`; Vite build can output to an auto-cleaned temp dir.
- Verification: targeted and adjacent regression `118 passed`; full suite `653 passed, 1 warning`.

### B4.S3 Multi-model build contract (P1)

Main files: `src/core/orchestrator.py`, `src/core/dispatcher.py`, `src/core/worker.py`, `config/workers.yaml.example`.

- [x] High-risk frontend projects fixed-split into architecture/scaffold, page modules, data & API, integration verification, Reviewer.
- [x] Orchestrator output must include entry, routes, dependencies, ownership, verification commands, and smoke paths.
- [x] Worker checks import/route closure before completion; forbid referencing uncreated modules.
- [x] Integration Worker runs only after dependencies succeed; does not treat other Workers’ self-claims as verification evidence.
- [x] Reviewer compares original requirements, file list, build results, and runtime evidence; does not accept “done” text claims.

Acceptance: fixed smart-mining fixture has no missing pages or wrong imports in the first round; at least two different-role models participate and are visible in RunJournal.

Completion notes (2026-07-18):

- `TaskPlan.frontend_contract` fixed-declares `project_root`, entry, route targets, npm deps, per-task ownership, verification commands, and smoke paths; integration tasks hold the same contract snapshot.
- High-risk frontend plans must and may only include four Worker stages—`architecture_scaffold`, `pages`, `data_api`, `integration`—with built-in Reviewer as the fifth role. Page and data tasks depend on scaffold; integration depends directly on all implementation tasks.
- Add deterministic closure checks: entry and route targets must exist; `package.json` must declare contract deps; JS/TS relative imports reachable from entry/routes must resolve; local HTML script and style refs must exist.
- Integration Worker requires a successful real `run_command` trace for every `verification_commands` item; “already run/passed” in body text cannot replace evidence. Even if Reviewer returns pass, it cannot override failed subtasks or engineering audit.
- Reviewer inputs include original request, contract, roles and planned/actual models, file list, acceptance evidence, command cwd/exit/output, and RunJournal runtime evidence.
- RunJournal `metrics.collaboration` records role, planned model, actual model, and status for Orchestrator, each Worker, and Reviewer; role and model counts are directly auditable.
- Verification: S3 targeted and adjacent regression `70 passed`; full suite `664 passed, 1 warning`. Existing warning remains Starlette/httpx deprecation.

### B4.S4 Frontend runtime and responsive smoke (P1)

Main files: new frontend smoke adapter/tool, `src/core/engineering/verifier.py`, test fixtures.

- [x] Use a mature browser engine to start controlled dev/preview server; test login, main routes, Mock data, and console errors.
- [x] Check key tables/charts are not blank or permanent skeleton.
- [x] Check 1280×720 and 390×844: no horizontal overflow, fixed-sidebar crush, or content occlusion.
- [x] Server lifecycle managed by verifier; reliable cleanup after timeout/port conflict.
- [x] Smoke failure is a required VerificationGate; project status stays blocked.

Acceptance: current bad Mock project must be stably intercepted by smoke; fixed version passes login, seven main nav routes, and data rendering.

Completion notes (2026-07-18):

- Add `frontend_smoke` execution tool and `FrontendSmokeContract`: structured argv must include dynamic `{port}`; only controlled Node/npm/pnpm/yarn/Python server entries allowed; no shell.
- `ManagedFrontendServer` binds `127.0.0.1` dynamic port and polls ready path; port contention retries up to three times; startup timeout, browser exception, and normal end all clean the full process group / Windows process tree.
- Playwright prefers installed Chromium, then system Edge/Chrome; missing runtime returns stable error codes and keeps smoke blocked—does not auto-download browsers or run install scripts.
- Desktop `1280×720` and mobile `390×844` both run login, all smoke routes, console/page error, visible/text/table_rows/canvas_nonblank/not_visible, horizontal overflow, and declarative element-occlusion checks; failures auto-keep screenshots.
- `ToolEvidenceRecorder` records real browser results as test Evidence; `VerificationTracker` generates `smoke` VerificationGate; Worker body text cannot replace a successful `frontend_smoke` trace.
- Real-browser positive fixture passes login, seven main nav routes, Mock tables, non-blank canvas, and both layout tiers; bad Mock login fixture stably fails with server cleanup. S4 targeted and adjacent regression `129 passed`, full suite `673 passed, 1 warning`.

### B4.S5 Report truthfulness and token efficiency (P1)

Main files: `src/core/summarizer.py`, RunJournal queries, CLI/Web per-turn records.

- [x] “Today’s operations / this session summary” aggregate from all RunJournals rather than only compacted current messages.
- [x] Reports distinguish create, fix, verification pass, verification fail, pending confirmation, and user manual steps.
- [x] Forbid continuing opposite speculation like “please confirm it may not be enabled” when config is already confirmed.
- [x] Dedup repeated file content and tool results; long tasks tally tokens and cost by role and stage.
- [x] Establish success rate, first-round runnable rate, user rework rounds, misdiagnosis rate, and tokens/effective-delivery metrics.

Acceptance: sample summary fully covers 33-file creation, 4-page fill-in, 7-file fixes, build status, and runtime failure; every fact traces to evidence/run_id.

Completion notes (2026-07-18):

- Add fully local `DeliveryReportBuilder`: this session reads all RunJournals; today-range bounded-scans all sessions; corrupt records isolated; no Provider calls.
- Create vs modify distinguished by direct `file_existed_before` evidence; verification pass/fail, missing checks, user-explicit steps, and residual risks aggregated separately; each fact keeps run_id/evidence_id.
- Cross-run dedup by fact fingerprint without re-expanding file content or tool output; after confirmed Provider config, filter “may be unconfigured / please confirm” speculation that conflicts with direct facts.
- Aggregate total input/output tokens, cost, per-role/actual-model tokens and cost; compute completion success rate, first-round runnable rate, explicit/semantic rework rounds, counter-hypothesis misdiagnosis rate, and tokens/effective delivery.
- CLI adds `/report session|today`; Web right bar adds this-session / today segmented summary; clear natural-language requests for “今日操作整理 / this-session engineering report” take the same zero-token local path.
- Browser-verified this-session and today switching at desktop and 390px with no horizontal overflow. S5 targeted and adjacent regression `75 passed`, full suite `679 passed, 1 warning`.

### B4.S6 Real-task replay and release gate (P1)

- [x] Redact this session into an offline fixed transcript and project fixture; do not save user secrets or private path contents.
- [x] Auto-replay classification, plan, file closure, build, browser smoke, audit, and summary.
- [x] CI without paid-model calls covers all deterministic contracts.
- [ ] Real Provider acceptance limited to one full task; confirm models, expected call count, and cost cap before execution.
- [x] Enter B4.3 session recovery only after all B4.S pass; recovery logic reuses new observed mutation and verification gates.

Acceptance: fixed fixtures achieve first-round build pass, core routes usable, no console errors, final audit passed; failure fixtures stay stably blocked.

Completion notes (2026-07-18):

- Add public redacted fixture `tests/fixtures/smart_mining/` with fixed request, structured multi-model role plan, seven-route frontend project, and smoke contract; redaction tests scan all publishable text and reject credentials, user private absolute paths, and `G:\\` paths.
- Add `StabilityReplayRunner` and `scripts/replay_smart_mining.py` running intent classification, frontend contract, route/import/dep closure, real npm commands, real browser smoke, completion audit, and delivery report in sequence with Provider call count fixed at 0.
- `good` fixture fully passes and becomes `completed`; `broken_mock` is intercepted by browser login/console gates; `missing_route` is intercepted by closure and four-level command gates. Both failure variants stay `blocked` with first-round runnable rate 0.
- CI adds offline smart-mining stability gate. Windows actual replay found `shell=False` cannot directly resolve `npm.CMD`; executor now resolves executables via `shutil.which` only after `FileNotFoundError` and retries with argv arrays.
- First-round runnable metric tightened: run status completed, targeted/integration/full/smoke all four gates passed, and Worker attempted only once; static smoke pass cannot mask build or test failure.
- Verification: S6 targeted regression `6 passed`; standalone replay script exit code 0; full suite `683 passed, 1 warning`; `compileall`, `node --check`, and `git diff --check` pass. Existing warning remains Starlette/httpx deprecation.

## 5. Recommended commit boundaries

1. `fix: classify natural project build requests`
2. `feat: escalate audits from observed project mutations`
3. `feat: run portable project verification with cwd`
4. `feat: enforce multi-model frontend build contracts`
5. `feat: add frontend runtime smoke gates`
6. `feat: aggregate truthful session delivery reports`
7. `test: replay the smart-mining acceptance fixture`

Each commit independently passes targeted tests and adjacent regression. B4.S does not change the public version number or create Tags; after completion update the full-test baseline, then resume B4.3.

## 6. Next steps

B4.S offline stability prerequisites are complete. Next execute **B4.3 session recovery confirmation** in [`Beta4-execution-checklist.md`](Beta4-execution-checklist.md); real Provider single-task acceptance still needs separate authorization and is not part of the unattended offline gate.

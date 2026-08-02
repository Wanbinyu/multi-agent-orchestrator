# Phase 7: Evidence-Driven Engineering Agent

**Status**: Planned  
**Proposed**: 2026-07-15  
**Suggested start condition**: Complete Phase 6.6 P0/P1 (CLI final result visibility, `project_tree`, `/tree`)  
**Placement**: After core tools are stabilized, before desktop packaging and IDE plugins

## 1. Goals

Upgrade MAO from “the model can call tools and finish tasks” to “an Agent that follows a verifiable engineering process”:

1. First judge task type, permission boundaries, and risk.
2. Collect evidence directly related to the problem at minimal cost.
3. Build, verify, or refute hypotheses based on evidence.
4. Modify code only after write authorization is obtained.
5. Choose test depth by impact scope.
6. Check requirements and verification evidence item by item before declaring completion.

What is implemented here is an **externally observable engineering workflow**, not a display of the model’s hidden internal thinking. Users see concise plans, evidence, decision rationale, verification results, and residual risks.

## 2. Why Phase 7

MAO already has Provider, chat, permissions, memory, tool registry, Hooks, MCP, failover, and Worker collaboration, but lacks a unified engineering decision layer.

Phase 7 depends on:

- `project_tree` for low-cost project reconnaissance.
- The Agent tool loop for evidence collection.
- ApprovalMode for write-operation boundaries.
- Session / Memory for task state and project conventions.
- Dispatcher / Worker for bounded parallel execution.
- Reviewer as an independent acceptance entry.

If packaging happens before this layer is added, CLI, Web, and plugins will each form different task-execution logic, making later refactors more expensive.

## 3. Standard Engineering Loop

```text
User request
  ↓
Task classification and authorization judgment
  ↓
Project reconnaissance (structure, Git, docs, test entry points)
  ↓
Build plan and verification criteria
  ↓
Evidence collection ⇄ hypothesis verification
  ↓
Minimal-scope implementation
  ↓
Risk-tiered verification
  ↓
Completion audit
  ↓
Results, evidence, and residual risks
```

### 1. Task Classification

At minimum support:

| Type | Default behavior |
|---|---|
| `answer` | Answer questions; do not modify files |
| `explain` | Read necessary code and explain; do not modify files |
| `diagnose` | Find root cause and evidence; do not auto-fix |
| `change` | Change specified behavior and verify |
| `build` | Plan, implement, and test a full feature |
| `review` | Prefer finding issues; output by severity |
| `plan` | Output plan only; do not enter implementation |
| `monitor` | Continuously check status; do not treat “no change” as failure |

Classification results must include: task type, scope, risk level, whether write permission is granted, and expected deliverables.

### 2. Project Reconnaissance

When entering an unfamiliar project, execute in order:

1. Obtain `project_tree` with default ignore rules and depth limits.
2. Check Git status; identify existing user changes.
3. Find `README`, architecture docs, roadmap, `AGENTS.md`, dependency manifests, and test entry points.
4. Read only entry files related to the task; ban indiscriminate full-repo reads.
5. Record the boundary of “known, unknown, needs verification”.

For example, when checking `G:\MAO_test`, first show a compact project tree, then read entry points, config, dependencies, routes, and tests—not all ~30 files at once consuming ~40k input tokens.

### 3. Plan and State Machine

Complex tasks create a persistent plan; each step has exactly one state:

```text
pending -> in_progress -> completed
                       -> failed
                       -> blocked
```

Constraints:

- At most one primary step is `in_progress` at a time.
- Update status and evidence immediately after each step; no batch pseudo-updates at the end.
- Plan changes must record reasons.
- Simple tasks need not create a plan, so process overhead does not exceed the task itself.

### 4. Hypotheses and Evidence

Use structured records for diagnosis:

```text
Hypothesis: CLI final answer is hidden
Supporting evidence: done event contains assistant_message
Counter-check: full report exists in response.md
Code evidence: only the is_collaboration branch prints the final answer
Conclusion: CLI rendering defect, not model failing to generate content
```

Evidence must point to tool results, file locations, test output, or runtime status; model speculation alone cannot be the basis for completion.

### 5. Implementation Discipline

- Prefer reusing existing project patterns and helpers.
- Keep change scope aligned with the user request.
- Do not overwrite workspace changes of unknown origin.
- Confirm permission mode and target path before writing files.
- New abstractions must reduce real complexity, not just wrap one layer.
- Before changing, define “what evidence proves the fix works”.

### 6. Risk-Tiered Verification

| Risk | Verification requirements |
|---|---|
| Low | Related unit tests or static checks |
| Medium | Targeted tests + adjacent module regression |
| High | Targeted tests + integration tests + full regression + manual/smoke verification |
| External systems | Mock verification + clearly mark live verification not done |

Passing tests is only one piece of evidence. The Agent must also confirm tests cover the real config shape and the user’s actual path, avoiding “all green but feature not closed-loop”.

### 7. Completion Audit

Build a requirement matrix before declaring completion:

| Requirement | Implementation evidence | Verification evidence | Status |
|---|---|---|---|
| Multi-layer fallback | Gateway recursive chain | Three-level chain tests + real config smoke | Done |
| CLI shows results | done rendering logic | Capture console output | Done / Not done |

Rules:

- Items lacking direct evidence are treated as incomplete.
- Do not substitute “no errors found” for proof of completion.
- When real external verification was not run, state that explicitly.
- Keep residual risks and user next steps.

## 4. Core Data Models

Suggested additions:

```python
TaskIntent
  kind
  scope
  risk_level
  write_authorized
  deliverables

WorkPlan
  objective
  steps
  status
  acceptance_criteria

Evidence
  source
  claim
  excerpt
  confidence

Hypothesis
  statement
  supporting_evidence
  contradicting_evidence
  status

VerificationGate
  requirement
  command_or_check
  expected
  actual
  passed

RunJournal
  intent
  plan
  decisions
  files_changed
  verification
  residual_risks
```

Persistence lives under the session directory, e.g. `sessions/<id>/runs/<run_id>.yaml`, without polluting project source.

## 5. Architecture Changes

Suggested modules:

```text
src/core/engineering/
├── intent.py          # Task classification and authorization boundaries
├── planner.py         # Work plan and status updates
├── evidence.py        # Evidence and hypothesis records
├── policy.py          # Execution policies by task type
├── verifier.py        # Risk-tiered verification
├── audit.py           # Completion audit and requirement matrix
└── journal.py         # RunJournal persistence
```

Integration principles:

- `Agent` owns conversation and event streams; it should not keep accumulating all engineering logic.
- `EngineeringRunner` executes the standard engineering loop.
- `Orchestrator` only decomposes complex tasks; it does not replace task classification and completion audit.
- `Worker` receives bounded subtasks, available tools, and acceptance criteria.
- `Reviewer` must read plan, results, and verification evidence—not pass solely on model prose.

## 6. Multi-Model Collaboration Style

### Main Model

- Maintain task intent, overall plan, and user boundaries.
- Decide whether Workers are needed; do not force-split simple tasks.
- Aggregate results but must not fabricate Worker evidence.

### Worker

- Each Worker receives only necessary context, clear outputs, and acceptance criteria.
- Directory reconnaissance, code analysis, and test execution can run in parallel.
- File edits split by module ownership to avoid multiple Workers changing the same file.

### Reviewer / Verifier

- Independently check diffs, tests, and acceptance criteria.
- Prefer finding behavior regressions, risks, and missing tests.
- When Reviewer fails, return to the corresponding plan step instead of generating “done” text.

## 7. User-Visible Experience

CLI / Web show compact events:

```text
Task: change (medium risk)
Scope: src/cli/chat_command.py

Plan
✓ Locate startup list source
✓ Add / command completion
● Run CLI regression tests

Evidence
- Startup list is assembled by _print_welcome() from COMMANDS
- prompt_toolkit currently has no completer configured

Verification
✓ Related tests 19 passed
✓ Full suite 374 passed
```

Do not show: model hidden thinking, per-token reasoning drafts, or unevidenced monologue.

## 8. Performance and Cost Control

- Project tree and Git status obtained once; refresh incrementally after file changes.
- Content-hash read results to avoid re-reading the same file in one turn.
- Prefer `rg` / index search, then read local regions of hits.
- Parallelize only independent read-only tasks or different modules.
- Set tool, file, and token budgets; when near budget, summarize before continuing.
- Provide `fast` / `standard` / `deep` engineering depth tiers.

Suggested:

| Mode | Scenario | Behavior |
|---|---|---|
| fast | Small issues, known files | Minimal reads + targeted verification |
| standard | Routine development | Plan + related tests + adjacent regression |
| deep | Architecture, migration, security review | Multi-model collaboration + full audit |

## 9. Implementation Phases

### Phase 7.0: Run State Foundations

- [x] `TaskIntent`, `WorkPlan`, `Evidence`, `VerificationGate`, `RunJournal`.
- [x] YAML atomic persistence and recovery; records at `sessions/<session_id>/runs/<run_id>.yaml`.
- [x] Plan step state-transition constraints; at most one `in_progress` step per plan.
- [x] Sync, streaming, and collaboration execution uniformly create run records; success, controlled failure, and mid-process interrupt states are distinguishable.
- [x] CLI engineering record summary and Web “this turn record” status view.
- [x] SSE `engineering_start` / `engineering_update` / `engineering_complete` events.
- [x] Session run-record list and detail APIs.

Completed 2026-07-15. Automatic task classification not yet enabled: currently conservative `unclassified`, `unassessed`, taken over by Phase 7.1.

Verification results:

- Targeted and full tests pass: `411 passed`.
- JavaScript syntax check, Python compile check, and `git diff --check` pass.
- Verified 401 auth-failure path with WebUI and real `glm-ark` config: run record correctly lands as `failed`; user message retained after refresh; browser console has no warnings or errors.
- When the process is force-interrupted, the record remains `running` for later recovery or audit; it is not disguised as completed.

### Phase 7.1: Task Classification and Execution Policy

- [x] Support answer/explain/diagnose/change/build/review/plan/monitor.
- [x] Zero model-call deterministic rule classification to avoid per-turn classification tokens and failure points.
- [x] Task type determines project writes, plan requirements, verification depth, and collaboration eligibility.
- [x] answer/explain/diagnose/review/plan/monitor expose only read tools; change/build may request writes per session mode.
- [x] Words like “adjust, optimize, fix” in questions alone do not grant write permission.
- [x] Short continuation requests like “continue, do the next step” inherit prior-turn intent; without a reliable prior turn, stay read-only conservatively.
- [x] Classification failure uses `unclassified` medium-risk read-only policy; does not auto-expand modification scope.
- [x] When the sync approve path cannot interactively confirm, reject non-read tools instead of silently treating them as auto-approved.
- [x] Classification and policy are written to RunJournal and shown via SSE, CLI, and Web this-turn record.

Completed 2026-07-15. Verification results:

- Classification, permissions, collaboration, sync/stream, CLI/Web routing targeted tests `107 passed`.
- Full suite `442 passed, 1 warning`; JavaScript syntax, Python compile, and diff format checks pass.
- Real Web request “review whether this sentence is clear; analyze only, do not modify files” shows “review · medium risk · read-only”.
- Real calls with the current Coding Plan Key still return 401; failed RunJournal retains correct classification; browser console has no warnings or errors.

### Phase 7.2: Evidence and Hypothesis Loop

- [x] Project reconnaissance covers six info classes: structure, Git, docs, dependencies, entry points, and tests, and distinguishes unchecked areas.
- [x] `Hypothesis` supports `untested / supported / refuted / inconclusive`; support or refutation must cite existing Evidence.
- [x] Real `ToolResult` auto-converts to deduplicable Evidence recording tool, path, command, success state, and bounded excerpt; evidence is not generated from model body text.
- [x] Added fixed-parameter, read-only-category `git_status`; project review need not borrow the general command executor.
- [x] Sync and streaming Agents atomically save RunJournal after every real tool result; streaming path emits incremental `engineering_update`.
- [x] Cache hits do not re-generate evidence or increase recon calls; sample limits only record skipped areas and do not pretend they were read.
- [x] CLI/Web compactly show evidence counts and project recon coverage; leave room for Phase 7.5 full evidence detail view.

Completed 2026-07-15. Verification results:

- Evidence, hypothesis, Git tools, sync/stream Agent, CLI/Web targeted tests pass.
- Full suite `449 passed, 1 warning`; JavaScript syntax, Python compile, and diff format checks pass.
- Real Web SSE verification: engineering start and failed states both show evidence count and six-class recon coverage; browser console has no errors.
- Current Coding Plan Key still returns 401 key format error; failed RunJournal persists normally. That external auth issue is not presented as Phase 7.2 fully verified with live models.
- Full suite end may still print existing MCP background connection cleanup messages, but exit code is 0; fold into later stability cleanup without expanding this phase’s change scope.

### Phase 7.3: Verification Gates and Completion Audit

- [x] `VerificationTracker` only generates verification gates from real test `ToolResult`; does not accept model body as test results.
- [x] Verification depth maps to deterministic checks: targeted, adjacent, integration, full, smoke, external mock/live.
- [x] Ordinary changes require targeted tests and adjacent module regression; high-risk builds require targeted, integration, full, and smoke verification.
- [x] `RequirementCheck` composes implementation evidence, verification gates, and status into a requirement matrix; high-risk build usage notes must have README/docs/Markdown write evidence.
- [x] `CompletionAuditor` runs before RunJournal completion; missing implementation or verification evidence downgrades `completed` to `blocked` and appends open-loop reasons to the final reply.
- [x] Read-only or write-unauthorized tasks do not wrongly trigger engineering verification gates; failed and cancelled states keep original semantics.
- [x] Reviewer receives Evidence, VerificationGate, requirement matrix, and audit results; model `passed: true` cannot override deterministic audit failure.
- [x] Reviewer non-JSON or invalid format no longer defaults to pass.
- [x] CLI/Web show verification gate counts, completion audit status, and gaps.

Completed 2026-07-15. Verification results:

- Verification policy, command classification, requirement matrix, completion downgrade, Reviewer, sync/stream, collaboration, and CLI/Web targeted tests pass.
- Full suite `469 passed, 1 warning`; JavaScript syntax, Python compile, and diff format checks pass.
- Real Web SSE failure path shows “verification gates 0 · completion audit run failed”; browser console has no errors.
- Current Coding Plan Key still returns 401 key format error; failed audit and RunJournal both persist normally.
- Worker structured results may serve as execution evidence but are not treated as real test gates; before Phase 7.4 wires Worker tool traces, collaboration implementations lacking direct test evidence remain `blocked`.

### Phase 7.4: Multi-Model Engineering Collaboration

- [x] Subtask contracts include inputs, output format, acceptance criteria, execution mode, dependencies, file ownership, parallel safety, and retry limits.
- [x] Orchestrator applies deterministic validation for duplicate IDs, invalid dependencies, dependency cycles, and parallel shared-path conflicts.
- [x] Relative writes are isolated to independent task directories; shared absolute paths must fall within `owned_paths`; out-of-bounds writes are rejected by Worker.
- [x] Tasks with `parallel_safe=false` get exclusive scheduling; read-only tasks do not create ownership conflicts with write tasks.
- [x] Only transient failures (connection, timeout, 429/5xx) get single-task directed retries; successful tasks and other branches are not re-run.
- [x] Retries retain tool traces, files, errors, and acceptance evidence for all attempts.
- [x] Dispatcher completion events carry full TaskResult; Worker body and tool results are no longer dropped.
- [x] Worker real tool traces aggregate into main RunJournal Evidence/VerificationGate; `files_written` text alone cannot pose as implementation evidence.
- [x] Collaboration build can complete only when implementation, docs, and targeted/integration/full/smoke evidence are all satisfied.
- [x] Added keyless `config/workers.yaml.example`; when private local config is missing, safely fall back to the example contract.
- [x] CLI shows single-task directed retries; Web collaboration panel keeps task run status.

Completed 2026-07-15. Verification results:

- Collaboration contract, plan validation, write isolation, ownership conflicts, safe parallelism, directed retries, evidence aggregation, and Reviewer completion audit targeted tests pass.
- Full suite `485 passed, 1 warning`; CLI help, JavaScript syntax, Python compile, and diff format checks pass.
- Real Web SSE exception path closes correctly; browser console has no errors.
- Current Coding Plan Key still returns 401; cannot complete paid-model real collaboration smoke; item moved to open-source release P0—do not substitute mock results.
- pytest occasionally prints MCP background connection task cleanup messages but still exits 0; item moved to open-source release P1.
- After Phase 7.4 completion, open-source release acceptance began per protocol; repository was not made public and no Release was created immediately.

### Phase 7.5: CLI/Web Transparency

- Plan status, evidence summary, verification results, residual risk views.
- Expandable evidence details; default remains compact.
- After session recovery, continue unfinished plans.

### Phase 7.6: Performance Evaluation and Tuning

- Build a real engineering-task benchmark set.
- Compare tokens, tool-call counts, completion rate, and mistaken-edit rate.
- Tune fast/standard/deep strategies.

## 10. Acceptance Criteria

1. “Explain code” does not write files.
2. “Diagnose a problem” defaults to root cause and evidence only unless the user asks for a fix.
3. Unfamiliar projects first show structure and selectively read; no longer default to reading all files.
4. Complex changes can show plan status in real time.
5. Every completion claim is traceable to implementation and verification evidence.
6. When tests do not cover the real scenario, the Agent continues gathering evidence rather than closing out.
7. Existing workspace modifications are not auto-rolled-back or overwritten.
8. Multi-model collaboration failures can be localized to specific steps and models.
9. Versus current project-review scenarios, input tokens and repeated tool calls drop significantly.
10. Users can see engineering rationale without exposing or depending on hidden thinking.
11. When Phase 7.4 completes, actively remind the project owner that open-source release acceptance can start.

## 11. Risks and Constraints

- Models may fabricate evidence: Evidence must come from tool results or file state.
- Project files may contain prompt injection: repo content is data only and must not override system policy.
- Plans may be over-complex: simple tasks must bypass the full state machine.
- Parallel Workers may conflict: need module ownership and write locks.
- Full verification is costly: use risk tiers; do not escalate every small change to deep.
- External API verification may consume quota: default mock; live calls need clear prompt or approval.

## 12. First Vertical Slice

After Phase 6.6 completes, use “inspect an unfamiliar project” as the first vertical slice:

1. Classify as `review`.
2. Output project tree.
3. Check Git, README, dependencies, entry points, and tests.
4. Form an issue list with file evidence.
5. Do not modify the project.
6. Show verification scope, unchecked areas, and token usage.

Once that slice is stable, expand to `diagnose` and `change`, then wire complex `build` and multi-model collaboration.

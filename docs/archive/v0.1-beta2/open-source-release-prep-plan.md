# MAO Open-Source Release Prep Plan

**Status**: `v0.1.0-beta.2` published as a public pre-release; repository switched to public

**Target version**: `v0.1.0-beta.2`

**Open-source trigger**: Immediately after Phase 7.4 completes, remind the project owner to enter open-source acceptance; only after passing this plan’s release gates, make the repository public and create a GitHub Release.

## 1. Release Positioning

The first public version is positioned as a usable, core-flow-trustworthy Beta still evolving quickly—not marketed as a full replacement for Claude Code, Codex, or other mature products.

Core promises:

- Multi-Provider, multi-model orchestration, and domestic model access.
- Explain, diagnose, change, review, and similar tasks have clear authorization boundaries.
- Tool calls, file changes, engineering records, and verification results are traceable.
- Model or Provider failures have clear status and are not disguised as success.
- Context window and compaction capabilities are described from real configuration—no guessing model identity or limits.

The first version does **not** promise:

- Breaking upstream model context hard limits.
- Stable native tool calling on all models.
- Full container-level code sandbox.
- All distribution forms such as VS Code, Electron, or standalone executables.
- Outperforming single-model Agents on every task.

## 2. Recommended Open-Source Stage

```text
Phase 7.0 Run state foundations (done)
  -> Phase 7.1 Task classification and execution policy
  -> Phase 7.2 Evidence and hypothesis loop
  -> Phase 7.3 Verification gates and completion audit
  -> Phase 7.4 Bounded multi-model engineering collaboration
  -> Open-source reminder + release acceptance iteration
  -> v0.1.0-beta.1
```

Do not wait for Phase 7.5–7.6 to fully complete. When Phase 7.4 finishes, MAO’s core story should form a closed loop: know what the user wants, execute within bounds, keep evidence, complete verification, and let multiple models collaborate within controllable bounds.

## 3. Core Gates Before Phase 7.4

### 1. Phase 7.1: Task Types and Safety Boundaries

- Support answer, explain, diagnose, change, build, review, plan, monitor.
- Explain and diagnose default to read-only unless the user explicitly asks for a fix.
- Change and build must record write authorization, scope, and expected deliverables.
- On classification failure, use a conservative strategy; do not auto-expand permissions.

**Acceptance**: Common natural-language requests land stably on the correct policy; read-only tasks do not write files.

### 2. Phase 7.2: Evidence-Driven Execution

**Status**: Completed 2026-07-15; passed `449 passed` full regression and real Web SSE exception-path verification.

- Unfamiliar projects first show structure, Git status, entry points, dependencies, and test locations.
- Tool results convert to citable Evidence.
- Distinguish facts, hypotheses, counter-evidence, and unchecked areas.
- Suppress repeated reads and unbounded project scans.

**Acceptance**: Project-review conclusions are traceable to files, tool results, or tests—not only model prose.

### 3. Phase 7.3: Verification Gates and Completion Audit

**Status**: Completed 2026-07-15; passed `469 passed` full regression and real Web SSE exception-path verification.

- Choose targeted tests, adjacent regression, full regression, or manual smoke verification by risk.
- Requirements, implementation, and verification form a correspondence.
- When key verification is missing, forbid claiming “completed”.
- Reviewer uses evidence-based review rather than free re-guessing.

**Acceptance**: Completion status can be proven; failures and residual risks are clearly visible.

### 4. Phase 7.4: Bounded Multi-Model Collaboration

**Status**: Completed 2026-07-15; passed `485 passed` full regression and real Web SSE exception-path verification.

- Subtasks have full inputs, output format, acceptance criteria, and file ownership.
- Parallelize only independent or isolatable tasks.
- Worker failures can be localized to specific tasks and models, with directed retries.
- Reviewer can wrap up based on each Worker’s evidence.
- Multi-model collaboration follows the same permission and verification boundaries as single Agent.

**Acceptance**: Complex engineering tasks do not cause file conflicts, repeated execution, or evidence-free merges due to parallelism.

## 4. Context Stability Gates

Before open source, at least complete Context 1–2 of *Context Extension and Long-Task Stability Plan*:

- Model window, max output, and budget sources are explainable.
- Unknown models keep a 32K conservative budget and are marked unverified.
- Agent, Worker, and Reviewer use a unified ContextBudgetManager.
- WebUI can configure and view context budget and compaction thresholds.
- Establish a minimal long-session benchmark covering large tool outputs, one compaction, and session recovery.

Context 3–5 full layered compaction, project-context reuse, and advanced observability can continue after Beta; but before public release there must be no known context-overflow issues that corrupt Sessions.

## 5. Release Prep Workstreams

### A. Install and Distribution

- Add `pyproject.toml`, formal version number, and CLI entry.
- Keep source-run workflow and provide venv install commands.
- Fresh Windows and Ubuntu environments: clone to first successful chat within ten minutes.
- Provider, MCP, Hooks, and Worker all provide keyless example configs.
- Create a GitHub Release, not only push `main`.

### B. CI and Quality Gates

- GitHub Actions covers Windows, Ubuntu, Python 3.11/3.12.
- Auto-run pytest, compileall, JavaScript syntax, and `git diff --check`.
- Add dependency and common secret scanning.
- Release branch must not have known P0/P1 failures.
- CI does not call real paid models; real models only via recorded manual smoke verification.

### C. README and Demo

- First screen: one sentence for product, target users, and core value.
- Drop outdated “CLI MVP” positioning.
- Add WebUI screenshots and a 60–90 second demo GIF/video.
- Five-minute quick start before architecture details.
- Show one complete engineering task: structure, permissions, tools, collaboration, verification, cost, and final result.
- List supported Providers, OSes, known limits, and security boundaries.
- Provide multi-model vs single-model benchmarks for tokens, cost, call counts, and completion rate—avoid pure marketing claims.

### D. Open-Source Governance

- Add `CONTRIBUTING.md`.
- Add `SECURITY.md` covering Key storage, command whitelist, permission modes, and sandbox limits.
- Add Issue, Bug, and Provider-compatibility templates.
- Add `CHANGELOG.md` and versioning policy.
- Clarify maintenance scope, supported Python versions, and Breaking Change handling.

### E. Security and Privacy

- Confirm `.env`, real Provider configs, Sessions, Memory, and private notes are not tracked.
- Scan history for API Keys, Tokens, personal paths, and real session content.
- README clearly warns users not to commit Keys.
- Default to `approve` or more conservative modes; dangerous capabilities must not enable silently.
- Until container-level sandbox is done, clearly state the local trust boundary in README and SECURITY.

### F. Real Acceptance Scenarios

At least verify:

1. Explain an unfamiliar project without modifying files.
2. Diagnose a failure; output root cause, evidence, and unverified areas.
3. Change a small feature; show plan, diff, and targeted tests.
4. Multi-model completes a decomposable task without file conflicts.
5. Model 401, 429, mid-stream interrupt, and Reviewer-fail paths close correctly.
6. Long sessions near budget can compact and continue without corrupting the session.

For each scenario, save environment, model, input, output, tool-call count, tokens, cost, verification results, and residual risks.

## 6. Release Acceptance Checklist

Create a public Release only when all are met:

- [x] Phase 7.1–7.4 all complete and pass their acceptance.
- [x] Context 1–2 complete; minimal long-session benchmark passes.
- [x] Full tests, Windows CI, and Ubuntu CI pass.
- [x] Independent venv install and first real conversation pass; fresh GitHub clone reconfirmed by CI.
- [x] Tracked files and Git history contain no real secrets or private sessions.
- [x] README first screen, quick start, screenshots/demo, and known limits complete.
- [x] CONTRIBUTING, SECURITY, Issue templates, and CHANGELOG complete.
- [x] Six acceptance scenarios complete with redacted evidence retained.
- [x] No unhandled P0/P1 defects.
- [x] Version number, Release Notes, and upgrade notes ready.

### 2026-07-15 First Release Gate Audit

Passed:

- Windows local full suite `485 passed, 1 warning`; CLI help, compileall, JavaScript syntax, and diff format checks pass.
- `.env`, private Provider configs, Session, Memory, private, and secret files are not tracked.
- Current tracked files and full Git history show no common API Key/Token patterns.
- Phase 7.1–7.4 permissions, evidence, verification, and bounded multi-model collaboration form a closed loop.

P0 blockers:

1. Current Coding Plan config real requests still return 401 key format error; first successful conversation and real multi-model collaboration not yet accepted.
2. Repository has no GitHub Actions; cross-platform CI for Windows/Ubuntu, Python 3.11/3.12 not yet run.
3. Context 1–2 and minimal long-session benchmark not complete; cannot prove recovery stability near budget.
4. Install-to-first-success conversation within ten minutes not completed on a fresh clone and independent venv.
5. Six real release scenarios have not all retained environment, model, token, cost, verification, and residual-risk evidence.

P1 blockers:

1. README first screen still uses “CLI MVP” old positioning; missing Beta status, WebUI screenshots, demo, and centralized known limits.
2. Missing `pyproject.toml`, formal version number, and installable CLI entry.
3. Missing `CONTRIBUTING.md`, `SECURITY.md`, Issue templates, and `CHANGELOG.md`.
4. Missing `v0.1.0-beta.1` Release Notes, upgrade notes, and release drill.
5. pytest occasionally prints MCP background connection cleanup messages; exit code is 0, but resource-cleanup noise should be eliminated before public release.

### 2026-07-15 Second Release Gate Audit

Resolved this round:

- Web startup chain loads `.env` before constructing chat Gateway; real Coding Plan Web chat returns `OK`, no more 401.
- Context 1–2 complete; unknown dynamic aliases do not pretend hard windows; all model requests share a unified budget manager before send.
- Minimal offline long session compressed from 39 messages/3,919 tokens to 8 messages/796 tokens; Session recovery and 3/3 key-fact retention pass.
- Windows local full regression `497 passed, 1 warning`; MCP background cleanup noise gone.
- GLM/Kimi dual-model read-only collaboration real smoke passes; 0 tool calls, 0 project writes.
- Independent venv install, real Provider first conversation, wheel/sdist, `twine check`, and dependency audit pass.
- README Beta home, five-minute quick start, real WebUI screenshots, centralized limits, governance files, Issue templates, and Release Notes completed.

Current P0:

1. GitHub Actions added, but first remote Windows/Ubuntu, Python 3.11/3.12 results cannot be obtained until after push.

Current P1: none.

### 2026-07-15 Third Release Gate Audit

Resolved this round:

- Completed 60-second real WebUI workflow GIF covering Provider config, `approve` authorization, project tree, Git status, restricted file reads, structured conclusions, and engineering evidence panel.
- Demo task read-only inspected 4 specified files; 6 tool calls all succeeded; target project not modified.
- Fixed long Markdown tables stretching the message area; WebUI now renders headings, bold, lists, and tables; long code and cell content stay inside the message container.
- Browser recheck of final message: 15 headings, 31 bold nodes, 7 tables; message area `scrollWidth` and `clientWidth` both 955px; no horizontal overflow.

### 2026-07-16 Fourth Release Gate Audit

Resolved / advanced this round:

- Local full regression recheck: `498 passed, 1 warning`.
- `pip-audit -r requirements.txt`: no known vulnerabilities found.
- Local gitleaks `8.24.3` scan: `no leaks found`.
- Hardened CI: unified `bash` shell; open-source gitleaks binary replaces private paid `gitleaks-action`.
- Fixed clean-clone missing `providers.yaml`, CLI help ANSI/narrow terminal, Windows UTF-8, session list sort, and other CI regressions.
- Remote GitHub Actions run `29469886664` (commit `a819879`) **all green**:
  - ubuntu-latest / Python 3.11
  - ubuntu-latest / Python 3.12
  - windows-latest / Python 3.11
  - windows-latest / Python 3.12
  - security (pip-audit + gitleaks)

**P0 cleared.** Release acceptance checklist fully checked.

Next steps (require owner confirmation; do not auto-execute):

1. Tag created and private GitHub pre-release published: `v0.1.0-beta.1`
2. Whether to switch repository from private to public (separate confirmation)

Detailed redacted evidence: `../../acceptance/release-acceptance-record.md`.

Conclusion: `v0.1.0-beta.1` private release complete; repository public visibility still needs separate owner confirmation.

### 2026-07-16 Fifth Release Gate Audit (beta.2)

Resolved this round:

- `mao` with no subcommand enters terminal chat directly; if no Provider config on first run, runs connection wizard first.
- Added `mao web`; keep `mao-ui` compatibility entry; config, sessions, and outputs rooted at the user’s current project directory.
- WebUI Gateway created on first use; after wheel install, config page can start from an empty unconfigured directory.
- Wheel embeds default Worker templates; installed multi-model collaboration does not depend on the source repo root.
- README adds project motivation, one-command `pipx` install, and two launch commands.
- Cleaned personal study notes, old stage process records, and unrelated screenshots; public file tree reduced by ~5,800 lines of unrelated content.
- Tests remain in the Git repo for contributors and CI; excluded from wheel, sdist, and release archives via `MANIFEST.in` and `export-ignore`.
- Local full regression: `506 passed, 1 warning`; empty-dir wheel WebUI `/health` returns 200; sdist has 0 test and internal docs entries.
- Commit `29ec2b0` remote Windows/Ubuntu, Python 3.11/3.12 test matrix, dependency audit, and secret scan all pass.

Completed:

1. Created and published [`v0.1.0-beta.2`](https://github.com/Wanbinyu/multi-agent-orchestrator/releases/tag/v0.1.0-beta.2) pre-release.
2. Project owner confirmed; GitHub repository switched from private to public.

## 7. Phase 7.4 Completion Reminder Protocol

When Phase 7.4 is marked complete, the following must run in the same work wrap-up:

1. Explicitly remind the project owner: **“Phase 7.4 is complete; open-source release acceptance can begin.”**
2. Update release status in `project-progress-and-roadmap.md` to “pending open-source acceptance”.
3. Open this plan’s “Release Acceptance Checklist” and check item by item; do not make the repository public immediately.
4. Summarize still-unmet blockers, ordered by P0/P1.
5. After all release gates pass, then recommend creating the current target Beta Release and public repository.

This reminder is milestone-triggered, not date-based. Current automatic reminder mechanisms cannot reliably judge whether Phase 7.4 is complete in Git.

## 8. Continue After Open Source

- Phase 7.5 full CLI/Web plan, evidence, and verification views.
- Phase 7.6 real-task performance evaluation and tuning.
- Context 3–6 layered compaction, project-context reuse, and full long-task benchmarks.
- Container-level sandbox and stricter plugin isolation.
- Executables, VS Code plugins, or Electron distribution.
- Prioritize Provider, MCP, and platform adaptations based on community Issues.

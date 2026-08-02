# MAO v0.1.0-beta.3 to beta.6 Version Plan

**Status**: beta.3–beta.7 released; currently advancing per `v0.2.0` entry criteria

**Current release baseline**: `v0.1.0-beta.7` (security patch)

**Created**: 2026-07-16

**Revision history**: 2026-07-17 — beta.4 adds context interference metrics, L0/L1/L2 layering reference, and Reviewer information-restriction verification; beta.5 adds preset model catalog expansion, benchmark anti-pollution, adversarial test generation, and local-model cost tier. 2026-07-19 — beta.4 release gate passed; current entry switches to B5.1 reproducible benchmark contract. 2026-07-21 — beta.5 (routing/execution depth/reproducible benchmarks) and beta.6 (Plugin API v0) released; beta.7 security patch fixes `run_command` inline code-execution P0; v0.2.0 entry criteria #2/#4/#5 met; #1 (external users) and #3 (real benchmarks) await external input/authorization. See [`v0.2.0-entry-criteria.md`](../../v0.2.0-entry-criteria.md).

## 1. Version split principles

Each of the next four Betas carries one primary outcome to avoid changing Provider, context, routing, and plugins at once:

| Version | Primary outcome | Out of scope for this version |
|---|---|---|
| `beta.3` | Trusted Provider/Claude integration and first-use stability | Large UI redesign, plugin marketplace |
| `beta.4` | Engineering transparency, session recovery, and long-task context | Smart routing, Provider expansion |
| `beta.5` | Model routing, execution depth, and real benchmarks | Desktop app, IDE extensions |
| `beta.6` | Controlled Plugin API v0 and extension diagnostics | Online plugin marketplace, auto-executing unknown code |

Enter the next version only after the current version’s release gates all pass. Urgent security fixes may insert patch versions but must not expand feature scope under cover.

## 2. `v0.1.0-beta.3`: Provider and Claude stability

### Goal

Enable new users to complete “install → configure Provider → test connection → first real task,” and make official Anthropic Claude a verified Provider rather than only a preset name.

### P0 scope

1. **Provider capability truth**
   - Record protocol, upstream model ID, streaming, native tools, vision, reasoning, context window, output limits, information source, and verification date for models.
   - Unverified capabilities stay off or marked `unverified`; do not guess from model names.
   - Show dynamic aliases separately from fixed-version models.

2. **Official Anthropic Claude verification**
   - Audit model IDs, pricing, context, and capability tags in official presets.
   - Verify `ANTHROPIC_API_KEY`, official Messages API, streaming responses, and error classification.
   - Verify full native `tool_use` rounds, not only Schema generation.
   - Clarify Claude subscription plans and Anthropic API Keys are not the same config entry; forbid non-public login credentials.

3. **Unified Provider errors**
   - Produce structured errors for 401/403, 404, 429, timeout, connection failure, 5xx, context exceeded, and unsupported capabilities.
   - CLI/Web show user-actionable next steps without exposing secrets or full response headers.
   - Only transient errors enter retry or failover; auth and config errors stop immediately.

4. **First-use acceptance**
   - Verify `mao` first-run wizard and `mao web` config page in a clean directory.
   - Verify `pipx` install, upgrade, and uninstall on clean Windows and Linux.
   - Provider config, Session, and RunJournal are not corrupted after abnormal exit.

5. **Extension load diagnostics**
   - Hooks/MCP load failures are no longer fully silent.
   - Startup provides bounded error summaries and `doctor`-level diagnostics, without introducing a full plugin system in this version.

### P1 scope

- Build a compatibility table for GLM/Ark Coding, Anthropic Claude, OpenAI-compatible, and local models.
- Issue templates collect platform, Provider, logical model name, upstream model ID, task type, and redacted errors.
- Docs cover common auth differences and “subscription plan ≠ API quota.”

### Release gates

- Full automated tests, Python/JavaScript static checks, and `git diff --check` pass.
- Clean Windows/Linux install passes.
- At least 3 Provider paths documented; official Claude completes offline contract tests at minimum when no key is available; real calls require explicit owner authorization.
- Auth failure, rate limit, timeout, and stream interrupt do not corrupt local state.
- No P0 secret leak, out-of-bounds write, data corruption, or false task-completion issues.

Detailed implementation order: [`Beta3-execution-checklist.md`](Beta3-execution-checklist.md).

## 3. `v0.1.0-beta.4`: Transparency and long tasks

### Goal

Users can understand task plans, execution evidence, verification results, block reasons, and context behavior without asking the model.

### Scope

1. CLI/Web expandable view of:
   - `WorkPlan`
   - `Evidence`
   - `VerificationGate`
   - `RequirementCheck`
   - `CompletionAudit`
   - `residual_risks`
2. After session recovery, detect `running`, `blocked`, and unfinished plans; require user confirmation before continue.
3. Implement Context 3 layered compaction: dedup, local summary, old-turn summary, and task checkpoints.
4. Add requirements, decisions, evidence, files changed, todos, and risks Schema for summaries, plus quality gates.
5. Implement incremental reuse of project tree, file summaries, and content-hash index.
6. CLI/Web show context usage, compaction count, budget source, estimate error, and recent compaction events.
7. Compaction quality gates add context interference metrics: after compaction, task-relevant tokens must dominate—not only retention rate; redundant context hurts model performance; interference must be measurable and replayable.
8. Compaction layering references L0/L1/L2 abstraction (index/summary/full text), keeps on-demand expand channels, and avoids compaction becoming one-way discard.
9. Reviewer uses information-restriction verification: independently verify against requirements and evidence without reading Worker self-narration; prefer parallel independent verification over multi-round review loops; verification-mode differences write to RunJournal.

### Release gates

- After three consecutive compactions, core requirements, file changes, and evidence refs remain.
- Post-compaction task-relevant token share passes agreed thresholds; interference is measurable and replayable.
- Session interrupt recovery never auto-rewrites or re-executes successful tasks.
- UI defaults to clean; full info after expand; no overflow at 390px mobile viewport.
- 32K/64K/128K/200K offline window benchmarks pass agreed thresholds.

## 4. `v0.1.0-beta.5`: Routing and reproducible benchmarks

### Goal

Use public data to prove when single-model should be used and when multi-model collaboration improves completion rate or lowers cost.

### Scope

1. Build a real engineering-task benchmark set: Q&A, diagnosis, small change, build, review, and migration.
2. Record for single-model and MAO:
   - Input/output tokens
   - Estimated cost
   - Tool-call count
   - Total duration
   - Completion rate
   - Mis-modification rate
   - Verification pass rate
3. Provide `fast`, `standard`, and `deep` execution depths.
4. Route by task type, capability, price, context, health, and user constraints.
5. Simple tasks default not to trigger Workers; complex tasks send only necessary context.
6. Routing decisions write to RunJournal with concise explainable reasons.
7. Expand preset model coverage: `src/models/catalog.py` as single source of truth covering Anthropic, OpenAI, DeepSeek, Zhipu GLM, Kimi, Alibaba Qwen, MiniMax, ByteDance Doubao, and Google Gemini; unverified entries stay `unverified`; CLI and Web presets are generated uniformly from the catalog.
8. Benchmark task set uses private or programmatically generated tasks and a reproducible harness, explicitly avoiding public-benchmark pollution controversy; task sources and generation methods are auditable.
9. Add adversarial test-generation experimental tier: independent test Worker tries to refute implementation Worker results; adversarial process and conclusions write to RunJournal.
10. Routing cost tiers include local/open-source models: `fast` defaults to zero-marginal-cost models (Ollama etc.); complex tasks escalate to paid models.
11. When entering real comparison, actively remind the project owner that capability testing is starting; first write a MAO adapter for Terminal-Bench/Harbor and run small terminal tasks; evaluate SWE-bench Lite/Verified only after stable. Aider is only a code-edit supplemental dimension.

### Release gates

- At least one public, reproducible token/cost advantage case.
- At least one multi-model completion-rate advantage over single-model, or a clear proof that certain task types should not use multi-model.
- Benchmark set contains no public benchmark original problems; task sources and generation methods are auditable.
- Routing failure can fall back to the user-specified model without unbounded retry.
- Benchmarks contain no private projects, secrets, or non-public data.
- External evaluation adapters, run versions, traces, and cost bounds are traceable; any real Provider call confirms models, counts, and cost caps first.

## 5. `v0.1.0-beta.6`: Plugin API v0

### Goal

Organize current ToolSource, MCP, Hooks, and Provider presets into a diagnosable, version-constrained extension interface that must be explicitly enabled.

### Scope

1. Define plugin manifest: name, version, MAO API version, entry, capabilities, permissions, and source.
2. Discover installed plugins via Python entry points or equivalent standards; do not scan arbitrary workspace code.
3. Plugin API v0 may contribute:
   - Local tools
   - `ToolSource`
   - Hooks
   - Provider presets
   - Model capability data
4. Provide lifecycle: load, diagnose, enable, disable, and shutdown.
5. Provide `mao plugin list` / `mao plugin doctor`; re-review concrete command names for CLI consistency before implementation.
6. Plugin load failures must be isolated and reported; they must not prevent MAO starting without plugins.
7. Third-party Python plugins are treated as trusted local code; prefer MCP process boundaries for external tools.

### Explicitly out of scope

- No online plugin marketplace.
- Do not auto-install model-recommended plugins.
- Do not download and execute Python code from unknown URLs.
- No third-party plugin sandbox promise; Python plugins share MAO process privileges.

### Release gates

- At least one independent example plugin successfully discovers, enables, executes, and shuts down in a wheel-install environment.
- Incompatible API versions are explicitly rejected.
- Plugin exceptions do not break Session, the tool registry, or no-plugin startup.
- Plugin permissions are visible in CLI/Web and require explicit user enable.

## 6. `v0.2.0` entry criteria

After `beta.3` through `beta.6`, do not automatically release `v0.2.0`. Also require:

- At least 10 external users complete install; at least 5 complete real project tasks.
- No unresolved P0 security, data-corruption, or privilege issues.
- Provider compatibility matrix and real benchmarks are publicly reproducible.
- Plugin API v0 has a clear compatibility policy.
- README, English quickstart, upgrade notes, and migration notes complete.

## 7. Version execution discipline

- When starting a version, mark only that version’s first item as `in_progress`.
- Each task records implementation files, test commands, results, and residual risks.
- Version numbers change only when preparing a candidate package—not during planning.
- Real paid Provider calls require owner-provided local config and confirmed cost bounds.
- Tag, Release, and repository-settings changes require separate confirmation.

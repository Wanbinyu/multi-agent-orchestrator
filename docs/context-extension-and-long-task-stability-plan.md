# Context Extension and Long-Task Stability Plan

**Status**: Context 1–2 and Context 6 minimum release baseline complete; Context 3–5 and full Context 6 pending

**Created**: 2026-07-15

**Principles**: Treat upstream real capability as the boundary; target long-task stability, information fidelity, and controllable cost; do not invent false capability with unverified window numbers.

## 1. Current Baseline

MAO already has a first version of context survival capability:

- `ModelConfig.max_context_tokens` supports per-model context budget overrides.
- When a model window is not configured, the Agent uses a conservative default budget of `32000 tokens`.
- By default, compaction of older messages is attempted at `75%` of budget, currently about `24000 tokens`.
- Compaction keeps system and recent messages and truly replaces earlier history with a summary.
- Token counting prefers `tiktoken`; when unavailable, estimates from UTF-8 bytes.
- CLI `/context` can show model mapping, current estimate, budget source, and compaction threshold with zero model calls.

Current limitations:

- Server-side aliases such as `ark-code-latest` may route models dynamically; MAO cannot yet confirm the final resolved model version.
- The model catalog does not maintain verified context windows, max output, and recommended safety margins.
- 32K is MAO's current safe budget, not equivalent to the physical upper limit of GLM-5.2 or other upstream models.
- Compaction is single-layer summary only; missing tool-output compaction, summary merge, quality checks, and recovery records.
- WebUI cannot yet configure or observe context budgets.

## 2. Goals and Non-Goals

### Goals

1. Every model uses a sourced, verifiable context window and output limit.
2. Dynamically compute available input budget from request, tool output, and reserved generation space.
3. When long sessions approach the window, free space in layers rather than failing on one large tool result.
4. After compaction, retain requirements, decisions, evidence, file locations, unfinished items, and risks.
5. CLI/Web can explain current budget, usage, compaction history, and remaining space.
6. Prove continuous long-task stability and information fidelity with offline benchmarks.

### Non-Goals

- Do not break upstream hard context limits.
- Do not treat Provider protocol compatibility type as model identity or window evidence.
- Do not default all models to 128K, 200K, or 1M.
- Do not unbounded-increase token cost just to enlarge the window.
- Do not mix long-term memory, project index, and raw conversation history into one infinitely growing prompt.

## 3. Budget Model

Later, split the single `max_context_tokens` into an explainable budget:

```text
upstream context window
- reserved output tokens
- Provider/tool protocol overhead
- safety margin
= MAO available input budget
```

Planned configuration semantics:

| Config | Meaning | Default strategy |
|---|---|---|
| `context_window_tokens` | Upstream-declared hard window | Only verified catalog values or user-explicit values |
| `max_output_tokens` | Max output per call | Maintained per model catalog |
| `context_safety_ratio` | Margin for Provider variance and counting error | Conservative 5%–10% reserve |
| `compaction_threshold` | Ratio at which context is reorganized | Default 75%, adjusted by task risk |
| `tool_result_budget` | Per-turn tool result budget | Compress tool results first when over limit |

Legacy `max_context_tokens` remains compatible and is explained as the MAO safe budget during migration.

## 4. Implementation Phases

### Context 1: Model Window Ground Truth and Config Surface (P0)

**Status**: Completed 2026-07-15.

- Add window, max output, source, and verification date to the built-in model catalog.
- Distinguish fixed model IDs from server-side dynamic aliases such as `ark-code-latest`.
- Keep the 32K conservative budget for unknown models and clearly show "unverified".
- WebUI adds fields for context window, safety ratio, compaction threshold, and output reserve.
- Validate ranges on save; forbid compaction threshold greater than the safe input budget.
- `/context` adds layered display: "upstream window / MAO safe budget / current available budget".

**Acceptance**: Any enabled model can state its budget source; unknown values never masquerade as official limits.

Actual implementation:

- `ModelConfig` gained hard window, max output, safety ratio, compaction threshold, source, verification date, and dynamic-alias fields; legacy `max_context_tokens` remains compatible.
- `ark-code-latest` / `ark-chat-latest` are explicitly marked dynamic and unverified; no fabricated official window is filled in.
- Config WebUI can edit window, output reserve, safety ratio, and compaction threshold; Pydantic rejects out-of-range values.
- CLI `/context` and the Web workspace layer hard window, safe input budget, current usage, remaining, output reserve, source, and warnings.

### Context 2: Dynamic ContextBudgetManager (P0)

**Status**: Completed 2026-07-15.

- Add a unified budget manager shared by Agent, Worker, Reviewer, and Compactor.
- Before each request, compute system, history, tool Schema, memory, and reserved-output usage.
- Set output reserves by task type: answer, code generation, and project review use different allotments.
- Use the corresponding tokenizer when the Provider supports it; otherwise keep conservative estimates and safety margin.
- When over budget, give a structured reason rather than relying on an upstream 400.

**Acceptance**: The same request gets a consistent budget on CLI/Web/Worker paths; before send, it is provable that the safe window will not be exceeded.

Actual implementation:

- `src/core/context_budget.py` uniformly subtracts output reserve, protocol overhead, tool Schema, and safety margin.
- Gateway sync and streaming entry points run the same check before every primary/failover model request, so Agent, Worker, Reviewer, and Orchestrator share it automatically.
- Over-budget or over-output-reserve throws a structured local error before send; does not wait for upstream 400.
- Unknown models continue using the 32K conservative safe budget and are explicitly tagged `unverified_default`.

### Context 3: Layered Compaction and Information Fidelity (P1)

Free space from low loss to high loss:

1. Remove duplicate tool results and obsolete intermediate outputs.
2. Produce sourced local summaries for over-long files, commands, and search results.
3. Merge older conversation summaries; keep recent full turns.
4. In extreme cases, produce a task checkpoint stating discard scope and remaining risk.

Also add:

- Summary schema: requirements, decisions, facts, evidence refs, modified files, todos, risks.
- Summary quality gate: do not replace original history when critical fields are missing.
- Compaction failure degradation: reduce tool injection or suggest a new session; do not interrupt the main flow.
- RunJournal records pre/post tokens, strategy, duration, and failure reasons.

**Acceptance**: After multiple compactions, core requirements, changed files, and unfinished items can still be restated; no fabricated non-existent evidence.

### Context 4: Persistent Project Context (P1)

- Project tree, file summaries, and symbol index reuse by project root and content hash.
- Prefer references and summaries in the prompt; read full text on demand.
- File changes invalidate only related summaries; do not rebuild entire project context.
- Separate session checkpoints from long-term memory: the former serves task recovery; the latter stores stable facts.

**Acceptance**: Re-analyzing the same project significantly reduces file reads and input tokens; changed files still refresh promptly.

### Context 5: CLI/Web Observability (P1)

- CLI status bar and Web workspace show usage ratio, remaining budget, and budget source.
- On compaction, show one concise event; do not dump hidden thinking or full summary content.
- Support viewing compaction count, last compaction time, pre/post tokens, and retained message count.
- Budget anomalies, dynamic model aliases, and estimation error use explicit warnings rather than silent guesses.

**Acceptance**: Users understand current context state and compaction behavior without asking the model.

### Context 6: Long-Task Benchmarks and Release Gate (P0)

**Minimum release baseline status**: complete; full multi-window and triple-compaction benchmarks to advance after Beta.

- Build offline simulated-window tests for 32K, 64K, 128K, 200K; do not call paid models in CI.
- Scenarios cover long chat, large tool output, project refactor, multi-compaction, session resume, and model switch.
- Metrics include completion rate, critical-info retention, compaction count, input tokens, latency, and cost.
- Real models only as manual smoke tests; record model, endpoint, window source, and cost.

**Release gates**:

- All budget paths compact or block predictably before limit.
- After three consecutive compactions, critical requirement and file-evidence retention meet baseline.
- Unknown model windows are never shown as confirmed numbers.
- Failure does not corrupt Session, RunJournal, or project index.

## 5. Implementation Order

Recommended order:

1. Advance Phase 7.1 task classification with Context 1 so different tasks have budget basis.
2. Finish Context 2 before Phase 7.2 evidence loops so project recon does not again blow the context budget.
3. Combine Context 3 with Phase 7.3 verification gates; compaction results must also pass quality checks.
4. Implement Context 4/5 after core budgets stabilize.
5. After Phase 7.4, enter open-source acceptance; before public Beta, complete at least Context 1–2 and Context 6 minimum long-session baseline.
6. Context 3–5 may continue after Beta, but expanding default windows or advertising advanced long-task capability requires full Context 6.

## 6. Risks and Controls

| Risk | Control |
|---|---|
| Official window or dynamic alias changes | Store source and verification date; fall back to conservative budget when unknown |
| Token estimate too low | Provider tokenizer + safety margin + pre-send recheck |
| Summary loses critical facts | Structured summary, evidence refs, quality gate, checkpoints |
| Compaction itself costs too much | Prefer local trim/dedupe; limit summary output and call frequency |
| Large windows raise cost | Allocate budget by task; do not fill the window by default |
| UI misconfigured window | Range validation, dangerous-value warnings, restore defaults |

## 7. Near-Term Next Steps

- Keep the current 32K default for unknown models; do not guess hard windows from Coding Plan plan names.
- After confirming actual model, window, and max output for `ark-code-latest` from citable upstream docs, fill source and verification date.
- Advance Context 3 layered compaction and summary quality gate.
- Extend Context 6 to 32K/64K/128K/200K, multi-compaction, model switch, and real summary quality.

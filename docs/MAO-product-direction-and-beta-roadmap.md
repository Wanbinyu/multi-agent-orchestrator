# MAO Product Direction and Beta Roadmap

**Status**: Current execution roadmap

**Baseline version**: `v0.1.0-beta.7` (security patch)

**Last updated**: 2026-07-25

## 1. Long-term goal

MAO’s long-term goal is to become a locally run, self-hostable multi-model Agent that can choose the right model for the task and complete reliable engineering work with fewer tokens.

The project does not treat “number of models” or “concurrency count” as success criteria. Success is defined by these outcomes:

- Users can use their existing model packages from different vendors and are not locked to a single vendor.
- Simple tasks do not call expensive models; collaboration depth increases only for complex tasks.
- Tools, modifications, tests, and risks are visible to the user.
- Long tasks can be recovered; core requirements and Evidence are not lost after compaction.
- Completion is never claimed without implementation Evidence or verification Evidence.

## 2. Target users

- Developers who use domestic models, OpenRouter, Claude, OpenAI, or local models at the same time.
- Individual users sensitive to token cost, plan quotas, or regional availability.
- Small teams that want configuration, sessions, and project data kept on the local machine.
- Engineering users who need to inspect the model’s execution process, not only accept final answers.

The current Beta is not aimed at production teams that need strong isolation sandboxes, enterprise SSO, centralized audit, or SLAs.

## 3. Differentiation

MAO does not compete with mature Coding Agents on full feature parity. It prioritizes four verifiable advantages:

1. **Multi-model task routing**: Choose models by task, capability, cost, context, and availability.
2. **Token and context control**: Observable budgets, compaction, caching, project indexing, and cost reporting.
3. **Evidence-driven completion**: Real tool results, verification gates, requirement matrices, and completion audits form a closed loop.
4. **Bounded collaboration**: Workers have dependencies, acceptance criteria, path ownership, and targeted retry rules.

## 4. Current baseline

As of `v0.1.0-beta.7`, the baseline already includes:

- `pipx` install and global `mao` / `mao web` entry points.
- Provider configuration UI, main model selection, and connection tests.
- CLI/Web multi-turn chat, streaming output, and permission modes.
- Multi-model task decomposition, Worker scheduling, and Reviewer aggregation.
- Tool registry, dual-track native tools, MCP, Hooks, and local models.
- Engineering task classification, Evidence, VerificationGate, CompletionAudit, and RunJournal.
- Model window configuration, dynamic safety budget, and minimal long-session benchmark.
- Windows/Ubuntu, Python 3.11/3.12 CI and security scanning.

## 5. Near-term version roadmap

Completed Beta execution scope and release gates are retained in [`archive/completed-beta/version-plan-v0.1.0-beta.3-to-beta.6.md`](archive/completed-beta/version-plan-v0.1.0-beta.3-to-beta.6.md). Current optimization and follow-up development are maintained in [`MAO-optimization-and-follow-up-plan.md`](MAO-optimization-and-follow-up-plan.md); this document no longer duplicates task lists.

| Version | Primary outcome | Current status |
|---|---|---|
| `v0.1.0-beta.3` | Trusted Provider/Claude access, unified errors, and first-use stability | Released |
| `v0.1.0-beta.4` | Engineering transparency, session recovery, layered compaction, and project indexing | Released |
| `v0.1.0-beta.5` | Model routing, execution depth, and real token/completion-rate baseline | Released |
| `v0.1.0-beta.6` | Controlled Plugin API v0 and extension diagnostics | Released |
| `v0.1.0-beta.7` | Security patch: fix `run_command` inline code execution P0 | Released |
| `v0.2.0` | Stable version for a broader audience | Not auto-released; entry criteria #2/#4/#5 met; #1 (external users) and #3 (real benchmarks) await external input/authorization |

Item-by-item execution and acceptance for `beta.3` are in [`archive/completed-beta/Beta3-execution-checklist.md`](archive/completed-beta/Beta3-execution-checklist.md); historical Claude and plugin boundaries are in [`archive/completed-beta/Claude-and-plugin-integration-decisions.md`](archive/completed-beta/Claude-and-plugin-integration-decisions.md). Desktop apps, IDE extensions, and team services are only green-lit after real user demand is clear.

## 6. User validation metrics

Phase one does not treat star count as the primary metric. Suggested tracking:

- Number of external users (out of 10) who install successfully.
- Number who successfully configure their first Provider.
- Number who complete their first real project task.
- Number who actively use MAO a second time.
- Count of reproducible issues and fix cycle time.
- Token, cost, and completion-rate differences between single-model and multi-model.
- Count of unauthorized writes, data corruption, and false task completion; the target must be 0.

Data collection should primarily use user-submitted Issues, redacted logs, and local benchmarks; project content and secrets are not uploaded by default.

External capability validation proceeds as “locally reproducible contracts → small-scale Terminal-Bench terminal tasks → SWE-bench Lite/Verified.” When entering B5.4, actively remind the project owner to start real capability testing, and confirm model, attempt count, cost cap, and result publication scope before any Provider call. Aider leaderboards only supplement the code-editing dimension and do not replace MAO’s multi-model Agent comprehensive evaluation.

## 7. Priority rules

When multiple directions compete, decide in this order:

1. Safety, data integrity, and authorization boundaries.
2. Install, Provider connection, and first-task success rate.
3. Completion audit, error recovery, and observability.
4. Tokens, cost, and long-task stability.
5. Model routing and multi-Agent effectiveness.
6. New tools, plugins, desktop, and ecosystem expansion.

Every new feature must answer: does it improve real-task success rate, reduce cost or risk, and can it be tested?

## 8. External reference principles

MAO may learn from public designs of OpenCode, Aider, Cline, Roo Code, and similar projects, but does not treat copying feature lists as the roadmap. The OpenCode audit record is in [`archive/completed-beta/reference-project-OpenCode.md`](archive/completed-beta/reference-project-OpenCode.md); whether to absorb further items is decided by verification gates in the optimization plan.

The learning order is: public interfaces and interaction ideas → independent design → small-scope implementation → test verification. When copying MIT code, license and copyright notices must still be retained; prefer independent implementation when not necessary.

## 9. Documentation governance

- Current architecture is maintained only in [`MAO-architecture-overview.md`](MAO-architecture-overview.md).
- Current product principles and priorities are maintained only in this document; current optimization tasks are maintained only in [`MAO-optimization-and-follow-up-plan.md`](MAO-optimization-and-follow-up-plan.md).
- Current progress, recovery steps, and common commands are maintained only in [`project-progress-and-key-operations.md`](project-progress-and-key-operations.md).
- Context details are maintained in [`context-extension-and-long-task-stability-plan.md`](context-extension-and-long-task-stability-plan.md).
- Completed stages, old comparisons, and release process move into `docs/archive/` and must not continue to be cited as current status.
- Release Notes retain the immutable release record for each version.

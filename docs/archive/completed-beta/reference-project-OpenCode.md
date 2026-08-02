# Reference Project Audit: OpenCode

**Audit date**: 2026-07-16

**Candidate conclusion**: X search results and MAO early learning notes both point to OpenCode; it is highly likely the multi-model project the user once saw, but without the original post screenshot or author info it cannot be confirmed with 100% certainty.

## 1. Identification clues

Highly relevant X results:

- Post: <https://x.com/VivekIntel/status/2063350729553936525>
- Description: open-source Claude Code alternative, Terminal UI, Built-in Agents, Desktop App, Multi-Model Support.
- Linked repo: <https://github.com/anomalyco/opencode>

MAO early Git history also had `OpenCode学习规划.md` pointing at the same repo. Most of that early document’s Provider, tools, Agent, permissions, and Session learning goals have been partially implemented in MAO Phase 1–7, so it is not restored as a current plan.

## 2. Is it open source?

Yes.

As of the audit:

- GitHub repo public and not archived.
- License MIT.
- Default branch `dev`.
- Primary language TypeScript.
- About 186,000 Stars, 23,000 Forks.
- Latest stable Release `v1.18.2`, published 2026-07-15.
- Audited source commit `17544802c38a4d35834275526ccf38be1cdcfbf4`.

These numbers are point-in-time snapshots, not competition targets for MAO.

## 3. Capabilities seen in this sample

### Multi-model and Providers

- Provider separated from Model.
- Adapters maintained for Anthropic, OpenAI, xAI, Gemini, OpenRouter, Azure, GitHub Copilot, etc.
- Handles reasoning, caching, output limits, Schema, and Provider-specific parameters by model capability.
- Supports model variants and Provider plugins.

### Agent and permissions

- Built-in Agents such as `build`, `plan`, `general`, `explore`.
- Hidden `compaction`, `title`, `summary` Agents for system tasks.
- Permission rules use `allow / ask / deny` with tool and path pattern matching.
- In-session one-shot and persistent approvals.
- Sub-Agents inherit necessary deny rules and external-directory bounds.

### Session and context

- Persistent Session runtime.
- Independent compaction, overflow, retry, summary, and run-state modules.
- TUI shows context share, tokens, and cost.

### Tools and extensions

- Tools such as read, write, edit, apply patch, shell, glob, grep, web, LSP, task, skill.
- MCP, plugins, LSP, SDK, and server interfaces.
- Terminal UI, desktop app, Web, VS Code extension, and multi-platform install channels.

## 4. Relationship to MAO

| Dimension | OpenCode | MAO current direction |
|---|---|---|
| Product maturity | Large mature project; multi-end and ecosystem complete | Public Beta; focus on stability and engineering closed loop |
| Tech stack | TypeScript, Bun, Effect, large monorepo | Python, Typer, FastAPI, light frontend |
| Multi-model | Broad Provider and model special-case adapters | Multi-Provider, model mapping, failover, and Worker division of labor |
| Agent | Roles such as build/plan/subagent | TaskIntent + Orchestrator/Worker/Reviewer |
| Permissions | Tool/path rules `allow/ask/deny` | Session mode + task write policy + Worker path ownership |
| Context | Mature compaction and TUI metrics | Dynamic budget done; layered compaction and index still progressing |
| Cost | TUI shows token and cost | Gateway billing, budgets, and later benchmarks |
| Completion judgment | This sample found no deterministic completion gates with the same names as MAO | Evidence, VerificationGate, RequirementCheck, CompletionAudit |
| Distribution | Scripts, npm, brew, scoop, choco, desktop installers | Currently mainly pipx and source install |

“Not found” only means this limited source sample; it is not a claim that OpenCode completely lacks similar capabilities.

## 5. Recommended borrowing

### P0: Direct near-term reference

1. **Provider capability matrix**
   - Turn protocol, tools, streaming, vision, reasoning, context, output limits, and verification dates into structured data.
   - Converge model special cases into an independent transform/compatibility layer so they are not scattered in the Agent.

2. **Permission rule expression**
   - On top of existing `auto/approve/readonly`, add `allow/ask/deny` by tool, category, and path.
   - Keep MAO’s task write authorization and Worker `owned_paths`; do not replace existing bounds with OpenCode rules.

3. **Context and cost status bar**
   - CLI/Web simultaneously show current model, context share, tokens, cost, and compaction events.

4. **Install experience**
   - Reference multi-platform install docs and upgrade paths, but first ensure pipx is stable before adding standalone install scripts or binaries.

### P1: After core is stable

- Clear Agent presets such as build/plan/explore and switching UX.
- Hidden system Agents for title, summary, and compaction to reduce main-Agent duties.
- Session concurrency protection, retry state, and recovery model.
- Provider plugins and model-variant configuration.
- LSP diagnostics as a verification evidence source.

### P2: Only with real demand

- Desktop app, IDE extensions, SDK, and server control plane.
- Multi-language docs automation and broader package-manager distribution.
- Plugin marketplace or centralized services.

## 6. Not recommended to copy

- Do not migrate to TypeScript/Bun/Effect merely to imitate its internal structure.
- Do not copy the full scope of large monorepo, cloud services, and desktop.
- Do not pile up unverified model special cases just to chase Provider count.
- Do not drop MAO’s Evidence, VerificationGate, CompletionAudit, or Worker path ownership.
- Do not use OpenCode’s Stars, feature count, or release frequency as MAO success metrics.

## 7. License boundaries

MIT allows using, modifying, and distributing code, but copying OpenCode’s actual code or larger implementation fragments requires retaining its copyright and license notices.

MAO currently prioritizes borrowing public design ideas and implementing independently. Only introduce code when direct reuse significantly lowers risk and license handling is clear, and mark the source in commits and docs.

## 8. Impact on MAO’s roadmap

OpenCode proves mature demand for “multi-model Coding Agents,” so MAO cannot treat “support multiple models” alone as its only selling point. MAO should keep focusing on:

- Low-friction access for multiple existing plans and China-market Providers.
- Token, cost, and context budget control.
- Deterministic evidence, verification gates, and completion audit.
- Multi-model collaboration with dependencies, path ownership, and acceptance criteria.

Corresponding milestones: [`MAO-product-direction-and-beta-roadmap.md`](../../MAO-product-direction-and-beta-roadmap.md).

# Upgrade Roadmap vs Claude Gaps

> Based on the gap list in “MAO vs Claude Code Comparison”, define a phased upgrade plan.
> For each gap, mark **feasibility** (✅ feasible / ⚠️ partially feasible / ❌ infeasible or not recommended) with reasons, and give an implementation order.
> Start date: 2026-07-13.

---

## 1. Gap List and Feasibility Assessment

| # | Gap | Feasibility | Reason | Priority | Effort |
|---|---|---|---|---|---|
| 1 | Auto compaction | ✅ Feasible | Existing `SessionSummarizer` base; switch to “summary replaces old history”; add token-count trigger | P0 | Medium |
| 2 | Context window awareness | ✅ Feasible | Add `max_context_tokens` to `ModelConfig`; trim before send; conservative defaults per model + config override | P0 | Small |
| 3 | Precise token counting | ✅ Feasible | Optional `tiktoken`; else character estimate (existing byte-estimate fallback) | P0 | Small |
| 4 | Edit local-edit tool | ✅ Feasible | Pure local tool; register `edit_file(path, old, new)` in registry | P1 | Small |
| 5 | Glob/Grep enhanced tools | ✅ Feasible | `glob_files`/`grep_content`; stdlib `fnmatch`/`re` or `subprocess rg` | P1 | Small |
| 6 | Background tasks / Monitor / notifications | ✅ Feasible | `subprocess.Popen` without wait; stream monitoring; system notifications | P2 | Medium |
| 7 | Native tool calling (some models) | ⚠️ Partially feasible | Anthropic/OpenAI SDK support native tool_use, but need message-history refactor; domestic model function calling unstable—must keep Markdown fallback | P2 | Large |
| 8 | MCP adapter | ✅ Feasible | MCP has Python SDK; adapter registers MCP tools into `ToolRegistry` | P2 | Medium |
| 9 | Hooks (pre/post tool intercept) | ✅ Feasible | Hooks around `ToolRegistry.execute`; configurable | P3 | Small |
| 10 | Sub-agent parallel abstraction | ✅ Feasible | Reuse Dispatcher for “temporary spawned subtasks” without full Orchestrator split | P3 | Medium |
| 11 | Reach Claude 200K/1M context | ❌ Infeasible | Hard-limited by connected models: domestic models often 32K–128K; MAO cannot change the model; only connecting Claude yields 200K | — | — |
| 12 | Unified native tool_use for all models | ❌ Infeasible | Some domestic models have unstable/unsupported function calling; must keep Markdown block fallback | — | — |
| 13 | Default full shell (drop whitelist) | ❌ Not recommended | Conflicts with MAO’s security-conservative stance; high risk; only as opt-in `unsafe` tool | — | — |
| 14 | Copy Claude official hosting/distribution | ❌ Infeasible | MAO is self-built; no Anthropic official resources/ecosystem; positioning difference, not a feature gap | — | — |

---

## 2. Infeasible / Not Recommended Items — Detail

### ❌ #11 Reach Claude 200K/1M Context
- **Reason**: Context window is a model-layer hard limit. Domestic models MAO connects (GLM / Kimi / DeepSeek / Qwen, etc.) are typically 32K–128K; as a client MAO cannot break that.
- **Alternative**: Via #1 auto compaction + #2 window awareness, achieve “long tasks remain sustainable” within limited windows—mitigation rather than breaking the ceiling. For any larger window, first confirm the real upstream limit, then establish MAO’s safe budget; detailed phases in `../../context-extension-and-long-task-stability-plan.md`.

### ❌ #12 Unified Native tool_use for All Models
- **Reason**: MAO’s core value is multi-vendor access. Some domestic models have poor or unstable function calling (param loss, format drift). Forcing all-native would make those models unusable.
- **Alternative**: #7 uses native path only for models that **declare tool_use capability and are verified stable**; others keep Markdown block fallback—dual track.

### ❌ #13 Default Full Shell
- **Reason**: MAO’s current `run_command` uses prefix whitelist + `shell=False` by deliberate security design. Default open is equivalent to exposing “arbitrary command execution” to the LLM, conflicting with `readonly`/`approve` safety semantics.
- **Alternative**: As an opt-in tool with `category="unsafe"`, enabled only with explicit config + `auto` mode; `approve` mode confirms item by item.

### ❌ #14 Copy Claude Official Hosting/Distribution
- **Reason**: MAO is a local self-built project without official distribution channels or hosted services. This is a positioning difference (self-hosted vs official hosted), not a feature goal.

---

## 3. Phased Implementation Plan

Order: “fix survivability gaps first, then tools, finally ecosystem.” Each phase is independently deliverable and testable.

### Phase 6.1 — Context Survivability (P0, highest priority)
**Goal**: Long sessions stop hard-failing on context limits.

- Token counting (#3): `src/core/token_counter.py`; optional tiktoken; else character estimate.
- Context window awareness (#2): `ModelConfig` adds `max_context_tokens` with conservative defaults; overridable in `config/providers.yaml`.
- Auto compaction (#1): `src/core/compactor.py`; before `Agent.run_turn` check total message tokens; when over threshold:
  - Keep system + last N turns;
  - Call summarizer on older messages to produce a summary;
  - Replace old history with the summary message (true compression, not merely writing memory).
- Trigger threshold: default 75% of window; configurable.
- Tests: `tests/test_compactor.py`, `tests/test_token_counter.py`.

**Acceptance**: Construct an overlong session; auto compaction continues without interruption; `pytest` all green.

### Phase 6.2 — Tool Enhancements (P1)
**Goal**: Fill high-frequency tools; reduce whole-file rewrites.

- `edit_file` (#4): precise `old_string`/`new_string` replace with uniqueness check.
- `glob_files` (#5): pattern match to list files.
- `grep_content` (#5): regex search file content (prefer `rg`, else Python `re`).
- Tests: `tests/test_edit_file.py`, `tests/test_search_tools.py`.

**Acceptance**: Agent can locally edit large files, find files by pattern, and search code by content.

### Phase 6.3 — Native Tool Calling (P2, some models)
**Goal**: Models that stably support tool_use use native structured calls.

- `ModelConfig.capabilities` already has `tool_use` tag; after provider detection, use native `tools` API.
- Refactor Agent message history: native `tool_use`/`tool_result` role support.
- Keep Markdown blocks as fallback for unsupported models.
- Tests: mock native tool_use flow.

**Acceptance**: Claude/GLM and other tool_use-capable models use native path; other model behavior unchanged.

### Phase 6.4 — Extension Ecosystem (P2/P3)
**Goal**: Connect external tools and extensibility mechanisms.

- MCP adapter (#8): `src/tools/mcp_adapter.py` registers MCP server tools into `ToolRegistry`; `config/mcp.yaml` configures server list.
- Hooks (#9): `src/core/hooks.py`; hooks around `ToolRegistry.execute`; `pre_tool`/`post_tool` config.
- Tests: mock MCP server; hook trigger verification.

**Acceptance**: Can mount one MCP server and call its tools; hooks can intercept/record tool calls.

### Phase 6.5 — Sub-Agent Parallel Abstraction (P3)
**Goal**: Temporarily spawn parallel subtasks within a single Agent without the full collaboration pipeline.

- `spawn_subagent` tool or built-in Agent method: reuse `Dispatcher` single-task execution for parallel multi-tasks.
- Merge results back into main conversation.
- Tests: parallel subtask execution and merge.

**Acceptance**: Agent can spawn parallel subtasks within a single turn and merge results.

---

## 4. Explicitly Out of Plan (Abandoned)

- ❌ Break model context ceiling (#11) — model-layer hard limit.
- ❌ All-model native tool_use (#12) — multi-vendor compatibility.
- ❌ Default full shell (#13) — security positioning.
- ❌ Official hosting/distribution (#14) — positioning difference.

---

## 5. Implementation Status

| Phase | Status | Notes |
|---|---|---|
| Phase 6.0 Tool registry + web tools | ✅ Done | 237 passed |
| Phase 6.1 Context survivability | ✅ Done | Auto compaction + window awareness + token counting; 250 passed |
| Phase 6.2 Tool enhancements | ✅ Done | edit_file/glob_files/grep_content; 265 passed |
| Local LLM + extension points | ✅ Done | Ollama/llama.cpp provider + ToolSource(MCP slot); 284 passed |
| Phase 6.3 Native tool calling | ✅ Done | tools= passthrough + schema generation + native_tools switch; 297 passed; developer tool guide + contrib dir |
| Phase 6.4 Extension ecosystem | ✅ Done | Hooks (pre/post intercept) + MCP adapter (stdio/sse) + startup loader; 329 passed |
| Phase 6.5 Sub-agent parallel | ⏳ Planned | Reuse Dispatcher; SubagentSpawner slot reserved |
| Phase 7 Evidence-driven engineering Agent | ⏳ Planned | Task classification, evidence/hypothesis loop, verification gates, completion audit; see separate plan |

---

*This plan rolls forward with implementation progress. After each phase, regress `python -m pytest -q` all green before advancing to the next phase.*

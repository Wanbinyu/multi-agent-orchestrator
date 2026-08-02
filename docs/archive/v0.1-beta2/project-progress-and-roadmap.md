# Project Development Progress and Roadmap

**Updated**: 2026-07-15

This document tracks completion of each stage of `multi-agent-orchestrator` so original plans can be compared with actual progress.

---

## Overall Overview

| Phase | Theme | Status | Completion |
|---|---|---|---|
| Phase 1 | Model connection config UI | ✅ Done | 100% |
| Phase 2 | Conversational interaction (Session + Agent + CLI/Web chat) | ✅ Done | 100% |
| Phase 3 | Streaming answers (SSE + CLI chunked output) | ✅ Done | 100% |
| Phase 4 | Multi-model auto collaboration in chat | ✅ Done | 100% |
| Phase 4.5 | Chat permission confirmation and Shift+Tab mode switch | ✅ Done | 100% |
| Phase 5 | Long-term memory and project context | ✅ Done | 100% |
| Phase 6 | Tool ecosystem and external integration | 🔄 In progress | 94% |
| Phase 7 | Evidence-driven engineering Agent | 🔄 In progress | 71% |

**Current test status**: `506 passed` (includes global install entry, empty-config WebUI, built-in Worker templates, unified context budget, and cross-platform CLI regression)

---

## Phase 1: Model Connection Config UI

### Completed

- [x] FastAPI + Jinja2 + browser UI entry `src/ui/app.py`
- [x] Provider CRUD API `src/ui/routers/providers.py`
- [x] 15+ common Provider presets and modular extension mechanism `src/ui/presets/`
- [x] Connection test and status persistence
- [x] Provider enable/disable; model pool auto-filter
- [x] API Key stored in local `.env`; leave empty on edit to keep unchanged
- [x] Main model selection and save
- [x] Quiet, workstation-style dark UI `src/ui/static/css/style.css`
- [x] Config page field grouping, single-page scroll, and mobile model cards
- [x] Chat page desktop main-area first, context drawer, mobile full-height layout, and horizontal session list
- [x] End-to-end verification: `python scripts/run_ui.py` can configure and run `python run.py`

### Related Files

- `src/ui/app.py`
- `src/ui/routers/providers.py`
- `src/ui/presets/`
- `src/ui/templates/index.html`
- `src/ui/static/js/app.js`
- `src/ui/static/css/style.css`
- `src/ui/config_manager.py`

### Completion

**100%** — Implemented and verified; usable day to day.

---

## Phase 2: Conversational Interaction

### Completed

- [x] `Session` multi-turn session model and YAML persistence `src/core/session.py`
- [x] `SessionStore` CRUD, independent output directory `sessions/<id>/output/`
- [x] `Agent.run_turn()` tool loop (max 5 rounds) `src/core/agent.py`
- [x] CLI REPL: `python run.py chat`, supports `/new`, `/load`, `/save`, `/plan`, `/tools`, `/exit`
- [x] Web chat page `/chat` and session list
- [x] Web chat API: create/get/send/delete sessions `src/ui/routers/chat.py`
- [x] Frontend message rendering, Markdown, tool results, and file display `src/ui/static/js/chat.js`
- [x] Top nav between connection config page and chat page
- [x] Unit tests: `tests/test_session.py`, `tests/test_agent.py`, `tests/test_chat_router.py`

### Related Files

- `src/core/session.py`
- `src/core/agent.py`
- `src/core/worker.py`
- `src/gateway/provider.py`
- `src/tools/worker_tools.py`
- `src/cli/chat_command.py`
- `src/ui/routers/chat.py`
- `src/ui/templates/chat.html`
- `src/ui/static/js/chat.js`

### Completion

**100%** — Implemented and verified; CLI and Web both support continuous multi-turn conversation.

---

## Phase 3: Streaming Answers

### Completed

- [x] `StreamChunk`, `ChatStreamEvent` data models `src/models/schemas.py`
- [x] Provider streaming: `AnthropicProvider.chat_stream()`, `OpenAICompatibleProvider.chat_stream()`
- [x] Gateway streaming methods: `chat_stream()`, `chat_with_main_model_stream()`, sync-generator-to-async wrapping
- [x] Streaming billing `Billing.record_stream()`
- [x] Agent streaming turn `Agent.run_turn_stream()` with tool loop and background-thread tool execution
- [x] Web SSE endpoint `POST /api/chat/sessions/{id}/messages/stream`
- [x] Frontend SSE consumption, placeholder bubbles, incremental Markdown render, final tool-result display
- [x] Streaming state CSS: pulse glow, blinking cursor, error text styles
- [x] CLI streaming print: consume `run_turn_stream()` via `asyncio.run()`
- [x] Keep legacy sync interface `POST /api/chat/sessions/{id}/messages`
- [x] Unit tests: `tests/test_agent_stream.py`, `tests/test_chat_router_stream.py`

### Related Files

- `src/models/schemas.py`
- `src/gateway/provider.py`
- `src/gateway/client.py`
- `src/core/agent.py`
- `src/core/worker.py`
- `src/gateway/provider.py`
- `src/tools/worker_tools.py`
- `src/ui/routers/chat.py`
- `src/ui/static/js/chat.js`
- `src/ui/static/css/style.css`
- `src/cli/chat_command.py`

### Completion

**100%** — Web and CLI both support chunked streaming output; tests pass.

---

## Phase 4: Multi-Model Auto Collaboration in Chat

### Goal

In continuous `/chat` conversation, the main model can **automatically decide** complex requests and call Worker models to collaborate, then integrate results into the current session. Turn the existing one-shot `/plan` capability into an automatic in-chat ability.

### Completed

- [x] Main model auto-decides collaboration need: `Agent._should_collaborate()`
- [x] Reuse `Orchestrator.plan()` + `Dispatcher.dispatch()` + `Worker.execute()` + `Reviewer.review()` pipeline
- [x] Optional `progress_callback` on `Worker.execute()` / `Dispatcher.dispatch()` for backward compatibility
- [x] `ChatStreamEvent` extended with `plan` / `task_start` / `task_complete` / `review_complete` event types and payload
- [x] `Agent._run_collaboration_stream()` async generator for collaboration event stream and collaboration cost
- [x] Web collapsible panel: plan summary, task status, review result, and final answer `src/ui/static/js/chat.js`
- [x] Collaboration panel tech-style CSS `src/ui/static/css/style.css`
- [x] CLI streaming collaboration progress: complex requests in `/chat` auto-show plan / task / review
- [x] Unit tests: `tests/test_agent_collaboration.py`, `tests/test_dispatcher_callback.py`

### Related Files

- `src/core/agent.py`
- `src/core/worker.py`
- `src/gateway/provider.py`
- `src/tools/worker_tools.py`
- `src/core/dispatcher.py`
- `src/core/worker.py`
- `src/models/schemas.py`
- `src/ui/static/js/chat.js`
- `src/ui/static/css/style.css`
- `src/cli/chat_command.py`

### Completion

**100%** — Implemented and verified; simple requests use a single model; complex requests auto-trigger multi-model collaboration.

---

## Phase 4.5: Chat Permission Confirmation and Shift+Tab Mode Switch

### Goal

Before the conversation Agent runs `read_file` / `write_file` / `run_command`, decide by the user’s permission mode whether to execute automatically or request approval first; support hotkeys for quick mode switch with experience close to Claude Code.

### Completed

- [x] Permission mode data models: `ApprovalMode`, `PermissionRequest`, `ChatStreamEvent.permission_request` `src/models/schemas.py`
- [x] `Session` persists `approval_mode` per session; new sessions default to `approve` `src/core/session.py`
- [x] `Agent` permission gate: `readonly` rejects, `approve` yields `permission_request` and waits, `auto` executes directly `src/core/agent.py`
- [x] `Agent.respond_to_permission()` resumes paused streaming via `asyncio.Event`
- [x] In approve / readonly modes, no longer auto-write `response.md` to avoid unauthorized disk writes
- [x] CLI Shift+Tab mode switch: `prompt_toolkit` bottom toolbar, `/mode` command, terminal y/n approval `src/cli/chat_command.py`
- [x] Web mode indicator and Shift+Tab switch: `POST /api/chat/sessions/{id}/mode` `src/ui/static/js/chat.js`
- [x] Web permission cards: SSE `permission_request` event renders Approve/Deny buttons `src/ui/templates/chat.html`
- [x] Web permission response endpoint: `POST /api/chat/sessions/{id}/permission/{request_id}` `src/ui/routers/chat.py`
- [x] Active Agent in-memory map `active_agents` so permission responses route to the streaming instance
- [x] Provider native tool-call compatibility: `tool_use` / `tool_calls` -> Markdown tool blocks `src/gateway/provider.py`
- [x] Tool-call parsing supports multiple closers: `` ``` `` / `<|tool_calls_section_end|>` `src/core/agent.py`
- [x] Volcengine Coding Plan Bearer auth (`/api/coding` endpoint auto uses `auth_token`)
- [x] Request body surrogate cleanup to avoid SDK encoding failures
- [x] Absolute-path writes allowed; relative paths get directory-traversal checks `src/tools/worker_tools.py`
- [x] Worker empty-content failure + tool-written files backfill `files_written` `src/core/worker.py`
- [x] Collaboration Reviewer final output auto disk write `src/core/agent.py`
- [x] Unit tests: `tests/test_agent_permission.py`, `tests/test_agent.py`, `tests/test_worker_tools.py`
- [x] Collaboration pre-dispatch bulk confirmation: in approve mode, one-shot consent before dispatch; deny cancels collaboration `src/core/agent.py`
- [x] /plan and run.py run pre-execution confirmation: readonly skips, approve prompts y/n, auto/non-interactive executes directly `src/cli/chat_command.py` `run.py`

### Related Files

- `src/models/schemas.py`
- `src/core/session.py`
- `src/core/agent.py`
- `src/core/worker.py`
- `src/gateway/provider.py`
- `src/tools/worker_tools.py`
- `src/cli/chat_command.py`
- `src/ui/routers/chat.py`
- `src/ui/templates/chat.html`
- `src/ui/static/js/chat.js`
- `src/ui/static/css/style.css`
- `tests/test_agent_permission.py`
- `tests/test_agent.py`
- `tests/test_worker_tools.py`
- `MAO-architecture-design.md`

### Completion

**100%** — CLI and Web both support permission confirmation and Shift+Tab mode switch; Volcengine Coding Plan auth, tool-call format compatibility, and absolute-path writes fixed; 177 tests passed.

---

## Phase 5: Long-Term Memory and Project Context

### Goal

Let the Agent remember project structure, important decisions, and user preferences across sessions, reducing the cost of re-explaining context from scratch each time.

### Completed

- [x] Project-level Memory abstraction `src/core/memory.py` (keyword inverted index, TF scoring, YAML persistence)
- [x] Session auto-summarization `src/core/summarizer.py` (`/memory summarize`, API endpoint)
- [x] Project file index and code search tools `search_project_files` / `search_memory`
- [x] Memory injection into current session context window (Agent / Orchestrator / Worker / Dispatcher)
- [x] Config persistence: `config/memory.yaml`
- [x] CLI output style improvements (live Markdown render, model attribution, tool-call truncation)
- [x] In-chat permission mode switch (`/auto`, `/approve`, `/readonly`, `/mode`)
- [x] Fixed model “talk only, no action” and conversation break after reading files
- [x] Web chat right-side memory/context sidebar

### Out of Scope for Original Round

- [x] Add “memory/context” sidebar in UI (done)

### Related Files

- `src/core/memory.py`
- `src/core/summarizer.py`
- `src/core/session.py`
- `src/core/agent.py`
- `src/core/orchestrator.py`
- `src/core/worker.py`
- `src/core/dispatcher.py`
- `src/tools/memory_tools.py`
- `src/cli/chat_command.py`
- `src/ui/routers/memory.py`
- `src/ui/templates/chat.html`
- `src/ui/static/js/chat.js`
- `src/ui/static/css/style.css`
- `config/memory.yaml`

### Completion

**100%** — Core memory storage, project index, prompt injection, CLI/Web API, session auto-summarization, CLI output polish, permission mode switch, tool-loop continuation fix, and Web sidebar all complete and end-to-end verified.

---

## Phase 6: Tool Ecosystem and External Integration

### Goal

Expand tool capabilities (web search, browser, code sandbox, MCP, IDE plugins) so the Agent is not limited to local files and commands.

### Plan Documents

- `Phase6-tool-ecosystem-and-external-integration-plan.md`
- `../../context-extension-and-long-task-stability-plan.md`

### Completed

- [x] Unified tool registry `src/tools/registry.py`
- [x] Built-in high-frequency tools: web search `web_search`, URL fetch `fetch_url`
- [x] Agent / Worker / Provider registry-driven
- [x] CLI / Web tool display generalized
- [x] Streaming retry dedup: no retry after output has started, avoid content duplication/overlap
- [x] Automatic model failover: on 429/connection failure switch along `fallback_models` chain and notify user
- [x] Model health cooldown: briefly mark failed models unhealthy to avoid consecutive hits
- [x] CLI `/test-models` diagnostic command
- [x] `list_dir` and absolute-path `glob_files`
- [x] Multi-layer fallback recursive expand, cycle break, and cooldown notifications
- [x] Coding Plan chat/diagnostics unified Bearer auth path
- [x] Collaboration Worker multi-round tool loop and tool authorization checks
- [x] Agent / Worker / Reviewer ban meaningless `generated_N` files
- [x] Hooks and MCP stdio/SSE adapter
- [x] Claude-style `/` command menu: filter live while typing; startup page no longer expands full list
- [x] Phase 6.6 P0: tool `tool_start` / `tool_complete` events, staged CLI process feedback, and final answer visibility
- [x] Phase 6.6 P1: `project_tree`, zero-token `/tree`, and project analysis structure conventions
- [x] Agent / Worker single-turn read-only tool cache; auto-invalidate after writes or command execution
- [x] Analytical requests single-Agent routing, 12-file hard cap, read-only native tools, and full compression of overlong results
- [x] Phase 6.6 P2: Web lazy-loaded project file tree, hidden-file toggle, and restricted text preview
- [x] WebUI responsive and interaction polish: no horizontal overflow at 390px, context drawer, and in-app new-session dialog
- [x] Context status baseline: CLI `/context`, runtime model facts, 32K default budget, and 75% compaction threshold observability

### Remaining

- [x] Context extension Context 1–2: model window ground truth, Web config surface, and unified dynamic budget manager
- [ ] Context extension Context 3–6: minimal release benchmark done; layered compaction, persistent project context, and full long-task benchmarks still pending
- [ ] Code execution sandbox
- [ ] More MCP Server presets and real-environment verification
- [ ] Configure external tool API Keys / MCP servers in UI
- [ ] Packaging and distribution: executables, VS Code plugins, or Electron shell

### Related Files

- `src/tools/registry.py`
- `src/tools/web_tools.py`
- `src/tools/search_tools.py`
- `src/gateway/client.py`
- `src/gateway/provider.py`
- `src/core/agent.py`
- `src/cli/chat_command.py`
- `src/ui/static/js/chat.js`
- `config/providers.yaml`

### Completion

**94%** — Tool registry, web tools, MCP/Hooks, failover, collaboration stability, CLI/Web project structure capabilities, analysis stability bounds, and CLI context status done; context extension continues as a follow-on stability workstream per its own plan and does not directly lower existing Phase 6 completion. Remaining: cross-session index reuse, sandbox, external tool config UI, and distribution. Full suite at the time of that note: `442 passed`.

---

## Phase 7: Evidence-Driven Engineering Agent

### Goal

Add a unified engineering decision layer to MAO: task classification, project reconnaissance, plan state, hypotheses and evidence, risk-tiered verification, completion audit, and evidence-based Reviewer.

### Start Conditions

- Phase 6.6 P0: CLI final answer visibility (met).
- Phase 6.6 P1: `project_tree` and `/tree` available (met).

### Plan Documents

- `Phase7-evidence-driven-engineering-agent-plan.md`
- `open-source-release-prep-plan.md`

### Current Implementation

- Each sync, streaming, and collaboration turn creates an independent `RunJournal`, atomically written to `sessions/<session_id>/runs/<run_id>.yaml`.
- Task intent, work plan, evidence, verification gate, and run journal models defined, with work-plan state-transition constraints.
- CLI shows run ID and result; Web shows “this turn record”; SSE provides engineering start, update, and complete events.
- Session run-record list and detail APIs; normal completion and controlled exceptions land as `completed` / `failed`.
- Web failure stream saves session in `finally`; after model request failure, refresh still retains user message.
- Real `glm-ark` 401 auth-failure path verified; run record is `failed`; browser console has no errors.
- Phase 7.1 deterministic task classification wired: answer, explain, diagnose, change, build, review, plan, and monitor have independent policies.
- Read-only tasks still forbid project writes in auto mode; only change/build can obtain write permission under approve/auto boundaries.
- CLI/Web engineering records show task type, risk, and “read-only / write needs approval / write authorized”.
- Phase 7.2 auto-converts real tool results into deduplicable Evidence; failed evidence keeps tool output and error reasons; does not fabricate evidence from model body.
- Project reconnaissance tracks six-class coverage: structure, Git, docs, dependencies, entry points, tests; cache hits not double-counted; skipped reads do not pretend checked.
- Added fixed-parameter read-only `git_status`; evidence atomically saved immediately after sync/stream tool execution; streaming path sends `engineering_update`.
- `Hypothesis` supports untested, supported, refuted, and inconclusive; support/refutation must bind existing evidence.
- CLI/Web this-turn record shows evidence counts and recon coverage; full evidence detail remains planned for Phase 7.5.
- Phase 7.3 risk verification policy wired: standard changes require targeted + adjacent; high-risk builds require targeted + integration + full + smoke.
- Requirement matrix binds implementation Evidence and VerificationGate; build usage notes must have document write evidence.
- Completion audit downgrades `completed` lacking direct evidence to `blocked` and rewrites the final reply; forbids unverified completion claims.
- Reviewer consumes deterministic audit context; model output and non-JSON fallback cannot bypass failed audits.
- CLI/Web show verification gate counts, audit status, and concrete gaps.
- Phase 7.4 subtasks have execution mode, dependencies, acceptance criteria, shared absolute-path ownership, parallel safety, and retry contracts.
- Orchestrator rejects dependency and ownership conflicts; Worker rejects read-only privilege escalation and undeclared shared absolute-path writes.
- Dispatcher retries only the target task on transient failure, keeps all attempt evidence, and does not re-run already-successful tasks.
- Worker tool traces can generate main RunJournal implementation and verification evidence; after full collaboration verification closes, `completed` is allowed.
- Falls back to `config/workers.yaml.example` when no local private config exists; example contains no secrets.

### Planned Stages

- [x] Phase 7.0: TaskIntent / WorkPlan / Evidence / RunJournal foundations
- [x] Phase 7.1: Task classification and answer/diagnose/change/review execution policies
- [x] Phase 7.2: Project reconnaissance, hypothesis verification, evidence citation, and read cache
- [x] Phase 7.3: Risk-tiered verification, requirement matrix, and completion audit
- [x] Phase 7.4: Bounded multi-model engineering collaboration; entered open-source release acceptance
- [ ] Phase 7.5: CLI/Web plan, evidence, verification, and residual risk views
- [ ] Phase 7.6: Real-task benchmarks, token and completion-rate tuning

### Completion

**71%** — Phase 7.0–7.4 complete with `485 passed` full regression, CLI/JavaScript/Python static checks, and real Web SSE exception-path verification. Core engineering closed loop formed; Phase 7.5–7.6 can continue enhancing transparency and benchmarks, but priority is handling P0/P1 blockers per the open-source release checklist.

### Open-Source Release Status

**`v0.1.0-beta.2` publicly released** — `beta.1` retained as an early private pre-release; current version fills in `mao` / `mao web` global install entry, empty-directory WebUI startup, and public-repo doc slim-down. Local `506 passed`, wheel smoke, remote Windows/Ubuntu test matrix, dependency audit, and secret scan all passed; repository switched to public and [`v0.1.0-beta.2`](https://github.com/Wanbinyu/multi-agent-orchestrator/releases/tag/v0.1.0-beta.2) pre-release published.

---

## Notes

- Completed Phases 1–4 match the original mainline: “connection config → conversation → streaming → multi-model collaboration”.
- Phase 4.5 permission system fixed the earlier issue where “Agent only wrote `response.md` and never truly wrote user-requested files”: after user approval or auto-execution of `write_file` in `approve` / `auto` mode, files truly land on disk and appear in `files_written`.
- Later stages can reorder by real usage frequency: if cross-session memory is more common, do Phase 5 first; if external tools like web search are needed, do Phase 6 first.

- Phase 4.5 continued (existing capability polish): extended permission confirmation to multi-model collaboration (one-shot confirmation before dispatch in approve mode; deny cancels) and to /plan and run.py run (y/n before execution; readonly skips; --yes/non-interactive auto-executes). Worker file writes during collaboration are covered by the pre-dispatch bulk confirmation. Tests: 177 passed.

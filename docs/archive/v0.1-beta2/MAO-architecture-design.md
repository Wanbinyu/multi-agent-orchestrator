# MAO Architecture Design Document

**Project**: multi-agent-orchestrator  
**Purpose**: A multi-model Agent orchestration tool that supports one-shot task decomposition and execution, as well as continuous conversation with tool calls and multi-model collaboration.  
**How to update**: After completing each part, change the corresponding `- [ ]` below to `- [x]` and fill in implementation details.

---

## 1. Project Positioning

MAO (Multi-Agent Orchestrator) splits a large requirement into multiple subtasks, assigns them to models with different strengths for parallel/serial execution, and finally has a Reviewer integrate the results. It also provides a `/chat` continuous conversation mode so users can read files, write files, and run commands through natural language, similar to Claude Code.

---

## 2. Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Language | Python 3.11+ | Primary development language |
| CLI framework | Typer | `run.py` subcommands |
| Web framework | FastAPI + Uvicorn | Config UI and chat API |
| Templates/frontend | Jinja2 + native JS/CSS | No frontend build pipeline |
| Model SDKs | Anthropic SDK, OpenAI SDK | Compatible with Anthropic and OpenAI-compatible APIs |
| Data models | Pydantic v2 | Config, message, and event models |
| Persistence | YAML, .env | Sessions, Provider, and Worker config stored locally |
| CLI interaction | prompt_toolkit, rich, questionary | Colored output, interactive prompts, Shift+Tab mode switching |
| Testing | pytest | Unit tests cover core paths |

---

## 3. Directory Structure

```
multi-agent-orchestrator/
├── config/                 # Runtime config (Provider, Worker)
│   ├── providers.yaml
│   └── workers.yaml
├── sessions/               # Session persistence
│   ├── <id>.yaml
│   └── <id>/output/        # Output files for that session
├── docs/                   # Design docs and records
├── scripts/
│   └── run_ui.py           # One-click Web UI launch
├── src/
│   ├── cli/                # CLI commands and wizards
│   │   ├── agent_setup.py
│   │   ├── chat_command.py
│   │   ├── provider_presets.py
│   │   └── setup_wizard.py
│   ├── core/               # Core orchestration and chat
│   │   ├── agent.py        # Conversation Agent (streaming, tool loop, permission gate)
│   │   ├── dispatcher.py   # Task scheduler
│   │   ├── orchestrator.py # Commander: task decomposition
│   │   ├── reviewer.py     # Review and wrap-up
│   │   ├── session.py      # Session model and storage
│   │   └── worker.py       # Worker executes subtasks
│   ├── gateway/            # Model call gateway
│   │   ├── client.py       # GatewayClient: unified entry, billing, main model selection
│   │   ├── provider.py     # AnthropicProvider / OpenAICompatibleProvider
│   │   ├── router.py       # Model routing and Provider polling
│   │   └── connection_test.py
│   ├── models/             # Shared data models
│   │   ├── catalog.py      # Model catalog
│   │   └── schemas.py      # Pydantic models
│   ├── tools/              # Tool implementations
│   │   ├── file_tools.py
│   │   └── worker_tools.py
│   └── ui/                 # Web UI
│       ├── app.py
│       ├── config_manager.py
│       ├── presets/        # Provider presets (modular)
│       ├── routers/
│       │   ├── chat.py
│       │   └── providers.py
│       ├── static/
│       └── templates/
├── tests/                  # Unit tests
├── run.py                  # CLI entry
├── requirements.txt
└── .env                    # API Key (local, not committed)
```

---

## 4. Core Architecture

### 4.1 Entry Layer

- `run.py`: Typer app providing `setup`, `agent-setup`, `chat`, and `run` subcommands.
- `scripts/run_ui.py`: Starts the FastAPI Web service, default listen `127.0.0.1:8123`.

### 4.2 Gateway Layer

`GatewayClient` in `src/gateway/client.py` is the unified entry for model calls:

- Reads `config/providers.yaml` and loads enabled Providers and models.
- Maintains a `Billing` instance summarizing tokens and cost per call.
- Provides `chat_with_main_model()` / `chat_with_main_model_stream()`.
- Provides `chat()` / `chat_stream()` for Worker/Orchestrator/Reviewer to call by specified model.

`src/gateway/provider.py` implements two Providers:

- `AnthropicProvider`: Native Anthropic Messages API with streaming support.
  - **Auth chosen by endpoint**: Volcengine Coding Plan endpoint (`/api/coding`) uses Bearer (`auth_token`); other Anthropic-compatible endpoints use `x-api-key` (`api_key`).
  - **Coding Plan token source**: Prefer env var `ANTHROPIC_AUTH_TOKEN`, fall back to `.env` `ARK_CODING_TOKEN`.
  - **Native tool-call compatibility**: Normalize model-returned `tool_use` blocks into Markdown tool blocks (`` ```tool:xxx ``), and skip `thinking` blocks so they are not injected into the body.
  - **Request body cleanup**: Strip lone surrogate characters before sending to the API to avoid SDK encoding failures.
- `OpenAICompatibleProvider`: OpenAI-protocol-compatible APIs (DeepSeek, Ark, GLM, Kimi, etc.) with streaming support.
  - Likewise converts native `tool_calls` into Markdown tool blocks and is compatible with `reasoning_content`.

`src/gateway/router.py` is responsible for:

- Finding an available Provider by model name.
- Polling / fallback across multiple Providers, handling RPM limits and failure retries.

### 4.3 Models Layer

`src/models/schemas.py` defines core data structures:

- `ProviderConfig`, `ModelConfig`, `WorkerConfig`
- `ChatMessage`, `ChatResponse`, `StreamChunk`, `ChatStreamEvent`
- `Task`, `TaskPlan`, `TaskResult`
- `ApprovalMode`, `PermissionRequest`

`src/models/catalog.py` maintains the available model list.

### 4.4 Orchestration Layer (Orchestrator / Dispatcher / Worker / Reviewer)

Used for one-shot tasks `python run.py <requirement>` or automatic collaboration inside `/chat`.

```
User request
  ↓
Orchestrator.plan()      # Split into subtasks
  ↓
Dispatcher.dispatch()    # Schedule by dependencies, concurrent execution
  ↓
Worker.execute()         # Each subtask calls the matching model + tools
  ↓
Reviewer.review()        # Review, integrate, produce final conclusion
```

- **Orchestrator**: Commander that splits a requirement into a dependency-aware `TaskPlan`.
- **Dispatcher**: Topological sort by `depends_on`; concurrent execution of independent tasks.
- **Worker**: Actual executor of each Task; selects model by task type, builds system prompt, invokes tools.
- **Reviewer**: Reads all TaskResults, decides pass/fail, and produces the final integrated output.

### 4.5 Conversation Layer (Session / Agent)

`src/core/session.py`:

- `Session`: Multi-turn conversation session with YAML persistence.
- `SessionStore`: CRUD, list in reverse chronological order.
- Each session has its own `output_dir`; file writes default to this directory.
- `approval_mode` is saved per session: new sessions default to `"approve"`; model default `"auto"` keeps tests compatible.

`src/core/agent.py`:

- `Agent.run_turn()`: Synchronous single-turn conversation for legacy interfaces.
- `Agent.run_turn_stream()`: Streaming version producing `ChatStreamEvent`.
- Tool loop: up to `max_tool_iterations` rounds until the model stops emitting tool blocks.
- **Tool-call parsing**: `_parse_tool_calls` supports three closing forms: standard `` ``` ``, coding-model special token `<|tool_calls_section_end|>`, and end-of-string; `_strip_toolcall_artifacts` clears leftover special tokens.
- Permission gate:
  - `readonly`: Reject directly.
  - `approve`: `yield permission_request` + `asyncio.Event` wait for user response.
  - `auto`: Execute directly.
- Auto disk write: write `response.md` only in `auto` mode; in multi-model collaboration, the Reviewer's final output code blocks are also written to disk.

### 4.6 Tools Layer

`src/tools/worker_tools.py`:

- `read_file`
- `write_file`: **Absolute paths write directly**; relative paths get directory-traversal checks.
- `run_command` (prefix whitelist)

`src/tools/file_tools.py`:

- `write_output_files`: Infer filenames from Markdown code blocks and write.
- `write_text_file`: Write arbitrary text files.

### 4.7 Web UI

`src/ui/app.py`: FastAPI app mounting static assets, Jinja2 templates, and routes.

Routes:

- `/`: Provider config page (`src/ui/routers/providers.py`).
- `/chat`: Chat page (`src/ui/routers/chat.py`).
- `/api/chat/sessions/*`: Session API.
- `/api/providers/*`: Provider API.

Frontend:

- `chat.js`: SSE consumption, mode switching, permission cards, collaboration panel.
- `app.js`: Provider config form, connection test, preset selection.

### 4.8 CLI

- `agent_setup.py`: New Provider config wizard.
- `setup_wizard.py`: Legacy Worker config wizard.
- `chat_command.py`: Interactive chat REPL with Shift+Tab mode switch, `/mode` command, and terminal permission confirmation.

---

## 5. Data Flow

### 5.1 One-Shot Task Flow

```
run.py run "Build a login page"
  ↓
GatewayClient
  ↓
Orchestrator.plan("Build a login page")
  → TaskPlan { summary, tasks[] }
  ↓
Dispatcher.dispatch(plan)
  → topological sort, concurrent execution
  ↓
Worker.execute(task)
  → call specified model, may use tools
  → TaskResult
  ↓
Reviewer.review(request, plan, results)
  → Review { passed, issues, final_output }
  ↓
Output files + summary.md + billing info
```

### 5.2 Continuous Conversation Flow

```
/chat user input
  ↓
Agent.run_turn_stream(user_input)
  ↓
_should_collaborate(user_input)?
  ├─ yes → _run_collaboration_stream()
  │         → plan / task_start / task_complete / review_complete / done
  └─ no  → main model single-turn / tool loop
            → delta / permission_request / done
  ↓
CLI or Web consumes events
```

### 5.3 Streaming and SSE

- Provider layer returns async generator `StreamChunk`.
- `GatewayClient` wraps it as an async stream.
- `Agent.run_turn_stream()` consumes and converts to `ChatStreamEvent`.
- Web returns via `StreamingResponse` as `text/event-stream`.
- CLI consumes with `async for` and prints.

---

## 6. Configuration and Persistence

| File | Content | Write method |
|---|---|---|
| `config/providers.yaml` | Provider list, API Key placeholders, model map, main_model | Web UI or `agent_setup` |
| `config/workers.yaml` | Worker role definitions | `setup` wizard |
| `sessions/<id>.yaml` | Session metadata, message history, approval_mode | `SessionStore.save()` |
| `sessions/<id>/output/` | Files produced by the session | Tool writes |
| `.env` | Real API Key / Token | Manual or wizard |

API Keys are stored only in local `.env`. Leaving the field empty when editing a Provider in the frontend means keep unchanged.

### Active Configuration (2026-07-12)

- `main_model`: `glm-ark` (Volcengine `ark-code-latest`, Anthropic-compatible `/api/coding` endpoint).
- `.env` environment variables:
  - `ARK_CODING_TOKEN`: Volcengine Coding Plan Token (Bearer auth), primary.
  - `ARK_API_KEY` / `VOLCENGINEARK_API_KEY`: Regular Ark Key; only usable with `/api/v3`, not Coding Plan.
  - `KIMI_API_KEY` / `KIMI1_API_KEY`: Kimi relay Key (quota-limited).
- Provider auth rules: `/api/coding` endpoint uses Bearer (`auth_token`, prefer `ANTHROPIC_AUTH_TOKEN` env var); other Anthropic endpoints use `x-api-key`.
- Switch main model: edit the `main_model` field in `config/providers.yaml`; optional values are under the `models` section (`glm-ark`, `glm-chat`, `glm`, `kimi-for-coding`).

---

## 7. Permission Mode Architecture

```
User input
  ↓
Agent.run_turn_stream()
  ├─ Main model outputs tool blocks
  ├─ _parse_tool_calls()
  │     ├─ readonly → reject
  │     ├─ approve  → yield permission_request
  │     │              → asyncio.Event wait
  │     │              → respond_to_permission(request_id, approved)
  │     │              → execute only if approved is true
  │     └─ auto     → execute directly
  ↓
CLI: terminal y/n prompt
Web: permission card Approve/Deny
```

The Web backend keeps the currently streaming Agent in memory via `active_agents: dict[str, Agent]` so the permission response endpoint can route correctly.

**Pre-dispatch bulk confirmation on the collaboration path**: Multi-model collaboration (`_run_collaboration_stream`), after the `plan` event and before dispatch, yields a `permission_request` in `approve` mode (`tool="collaboration"`, including subtask count and output directory) to obtain one-shot user consent:

- Approve → subtasks run automatically (no per-item confirmation).
- Deny → `done` prompts “collaboration cancelled”, no dispatch.
- `readonly` → collaboration not triggered.
- `auto` → execute directly.

`/plan` chat command and `run.py run` also confirm before execution: `readonly` skips, `approve` uses terminal y/n, `auto`/non-interactive (`--yes` or non-TTY) executes directly.

---

## 8. Multi-Model Collaboration Architecture

In `/chat`, the main model first judges request complexity:

- Chit-chat, single-file read/write → single model answers directly.
- Feature/page/API development or multi-step implementation → trigger collaboration.

The collaboration flow reuses `Orchestrator` → `Dispatcher` → `Worker` → `Reviewer` and reports progress to the frontend in real time via SSE events.

---

## 9. Testing Strategy

- Unit tests cover each core module: `tests/test_*.py`.
- Key test suites:
  - `test_agent_permission.py`: Permission modes.
  - `test_agent.py`: Tool-call parsing (including `<|tool_calls_section_end|>` close), artifact cleanup.
  - `test_agent_stream.py`, `test_chat_router_stream.py`: Streaming conversation.
  - `test_agent_collaboration.py`, `test_dispatcher_callback.py`: Multi-model collaboration.
  - `test_worker_tools.py`: Absolute-path writes, directory-traversal checks.
  - `test_ui.py`, `test_provider_model_map.py`: Web UI and Provider config.
- Current status: `177 passed`.
- How to run:

```powershell
python -m pytest -q
```

---

## 10. Deploy and Run

```powershell
# Install dependencies
pip install -r requirements.txt

# Configure Provider
python run.py agent-setup
# Or start Web UI to configure
python scripts/run_ui.py

# One-shot task
python run.py "Build a login page"

# Continuous conversation
python run.py chat

# Web chat
python scripts/run_ui.py --no-open
# Open browser http://127.0.0.1:8123/chat
```

---

## 11. Module Completion Checklist

After finishing each part, change the corresponding `- [ ]` to `- [x]`, and record implementation notes at the end of this file or in the related Phase document.

### Phase 1: Provider Connection Configuration

- [x] Provider model and config persistence
- [x] 15+ common Provider presets and modular extension
- [x] Provider CRUD API
- [x] Connection test
- [x] API Key stored in local `.env`
- [x] Main model selection
- [x] Web config UI

### Phase 2: Conversational Interaction

- [x] Session multi-turn session model
- [x] SessionStore YAML persistence
- [x] Agent synchronous tool loop
- [x] CLI interactive chat
- [x] Web chat page and session list
- [x] Web chat API

### Phase 3: Streaming Answers

- [x] StreamChunk / ChatStreamEvent models
- [x] Provider streaming implementation
- [x] Gateway streaming methods
- [x] Agent streaming single turn
- [x] Web SSE endpoint
- [x] Frontend SSE consumption and incremental rendering
- [x] CLI streaming print

### Phase 4: Multi-Model Auto Collaboration in Chat

- [x] Main model auto-decides whether collaboration is needed
- [x] Reuse Orchestrator / Dispatcher / Worker / Reviewer
- [x] Collaboration progress callbacks
- [x] Collaboration event type extensions
- [x] Web collaboration panel
- [x] CLI collaboration progress print

### Phase 4.5: Permission Confirmation and Shift+Tab Mode Switch

- [x] ApprovalMode / PermissionRequest data models
- [x] Agent permission gate (readonly / approve / auto)
- [x] `respond_to_permission` + `asyncio.Event`
- [x] CLI Shift+Tab switch and `/mode` command
- [x] Web mode indicator and switch endpoint
- [x] Web permission card and response endpoint
- [x] Active Agent in-memory map
- [x] Provider native tool-call compatibility (`tool_use` / `tool_calls` -> Markdown tool blocks)
- [x] Tool-call parsing supports multiple closers (`` ``` `` / `<|tool_calls_section_end|>`)
- [x] Volcengine Coding Plan Bearer auth (`/api/coding` endpoint)
- [x] Request body surrogate cleanup
- [x] Absolute-path write allowed
- [x] Worker empty-content failure + tool-written files backfill `files_written`
- [x] Collaboration Reviewer final output auto disk write
- [x] Unit tests (177 passed)

### Phase 5: Long-Term Memory and Project Context

- [x] Project-level Memory abstraction
- [x] Session auto-summarization
- [x] Project file index and code search tools
- [x] Memory injection into context window
- [x] UI memory/context sidebar

### Phase 6: Tool Ecosystem and External Integration

- [x] Unified tool registry
- [x] Web search / URL fetch tools
- [x] Context compression and local LLM Provider
- [x] Native tool_use
- [x] Hooks and MCP adapter
- [x] Multi-layer model failover
- [x] Collaboration Worker multi-round tool loop
- [ ] Optional code execution sandbox
- [ ] External tool config UI
- [ ] Packaging/distribution (executables / IDE plugins)

---

## 12. Known Limitations and Follow-Up Directions

1. Worker subtasks in collaboration still auto-execute file writes without per-item user confirmation.
2. MCP adapter is done, but real use of specific servers needs optional dependencies installed and separate verification.
3. No browser automation or isolated code execution sandbox yet.
4. External tools still lack a Web config panel.
5. `ark-code-latest` is a reasoning model; it consumes thinking tokens before body output; retry after brief wait on quota/availability fluctuation.
6. Different models/proxies vary widely in tool-call format; currently Markdown tool blocks + native `tool_use`/`tool_calls` are supported; new formats will require extending `_parse_tool_calls`.

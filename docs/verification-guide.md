# MAO Manual Functional Verification Guide

> Manually verify tools, Hooks, native tool use, context, MCP, and local models. Source-development commands run from the project root; install users can use `mao` directly.

---

## Preparation

```bash
# 1. Confirm tests are green (v0.1.0-beta.2 baseline was 506 passed)
python -m pytest -q

# 2. Start CLI chat (choose one)
mao

# 2. Or start Web UI (choose one)
mao web --no-open
# then open http://127.0.0.1:8123 in a browser
```

> Prerequisite: `config/providers.yaml` already has usable models and a main model configured. CLI uses the main model by default.

After B5.5, the local full test suite is `798 passed, 1 warning`; B5.4 historical baseline was `787 passed, 1 warning`; released beta.4 baseline was `722 passed, 1 warning`. High-risk frontend contracts can be verified alone:

```bash
python -m pytest -q tests/test_frontend_contract.py tests/test_orchestrator.py tests/test_worker.py tests/test_reviewer.py tests/test_agent_collaboration.py tests/test_registry.py
```

These tests do not call paid models; they cover fixed duties, dependency/ownership, missing pages and bad imports, real command Evidence, Reviewer completion gates, and multi-duty RunJournal records.

S4 browser smoke uses Python Playwright. Installing project dependencies automatically provides the Python package; at runtime system Edge/Chrome is preferred. If the machine has no available Chromium kernel, install once:

```bash
playwright install chromium
```

Offline positive/negative fixture verification:

```bash
python -m pytest -q tests/test_frontend_smoke.py
```

The positive fixture covers login, seven main routes, table/canvas, and two responsive layouts; the broken Mock login fixture must fail and confirm the server was cleaned. This verification does not call a Provider.

S6 full-chain offline release gate:

```bash
python -m pytest -q tests/test_delivery_report.py tests/test_stability_replay.py
python scripts/replay_smart_mining.py
```

The script must return 0; output `good` is `completed`, `broken_mock` and `missing_route` are `blocked`, and all three have `provider_calls` of 0. It runs real local npm commands and browser smoke but does not call any configured model.

B5.1 engineering benchmark contract:

```bash
python -m pytest -q tests/test_engineering_benchmark.py
python scripts/benchmark_engineering.py
```

The public suite must cover Q&A, diagnosis, small change, build, review, and migration. `fixture-fixed-single`, `fixture-auto-route`, and `fixture-multi-model` each run three times for 54 results total; top-level `passed=true`, `provider_calls=0`, and all stability entries must be stable. Data type in JSON/Markdown is `synthetic_contract` and cannot be used for real model quality claims.

B5.4 non-interactive and Harbor adapter contract:

```bash
python -m pytest -q tests/test_benchmark_agent.py tests/test_engineering_benchmark.py tests/test_agent_collaboration.py tests/test_explainable_model_routing.py
python run.py benchmark-agent --help
```

Must verify the three strategies respectively as fixed routing/single Agent, auto routing/single Agent, and auto routing/multi-model; `fixed-single` must specify a main model; `multi-model` rejects `fast`. Offline tests do not read keys. Real execution must first create a `LiveBenchmarkAuthorization` with model list, attempt count, cost stop threshold, and visibility. Attempt count must be atomically reserved via `reserve_provider_attempt` before each Provider network request; tests must cover sync, stream, and concurrent Workers to prove the next request after the cap never reaches the mock Provider—not only report over-limit after the full round.

B5.2 execution depth contract:

```bash
python -m pytest -q tests/test_execution_depth.py tests/test_engineering_verification.py tests/test_agent.py tests/test_agent_stream.py tests/test_agent_collaboration.py tests/test_chat_command_mode.py tests/test_chat_router.py
```

Verification must cover automatic recommendation, user explicit choice, high-risk safety elevation, real multi-file write dynamic elevation, RunJournal v5 round-trip of v4 fields, main Agent/Worker budgets, CLI `/depth`, and Web API. `fast` must not start Workers; explicit `deep` must raise the change-verification floor. This suite does not call a Provider.

B5.3 explainable model routing:

```bash
python -m pytest -q tests/test_explainable_model_routing.py tests/test_model_router.py tests/test_gateway_client.py tests/test_gateway_failover.py tests/test_agent.py tests/test_agent_stream.py tests/test_chat_command_mode.py tests/test_chat_router.py
```

Must verify: `fixed` locks the user main model; only verified capabilities can trigger automatic upgrade; unknown price cannot generate savings claims; context shortage and health cooldown can select qualified candidates; automatic upgrade at most once; on switchable candidate failure, prefer fallback to user main model; CLI/Web show concise reasons while RunJournal v5 keeps full candidates. Tests use mock Providers and do not consume real tokens.

B5.5 adversarial testing and local model routing contract:

```bash
python -m pytest -q tests/test_adversarial_tester.py tests/test_agent_collaboration.py tests/test_reviewer.py tests/test_chat_command_mode.py tests/test_chat_router.py tests/test_explainable_model_routing.py
```

Must verify: Session defaults adversarial testing off; the read-only role is only called when explicitly enabled `deep change/build` collaboration, all Workers succeed, and deterministic audit already passed; Worker self-description body text must not enter its prompt. `refuted` must downgrade completion to blocked; `inconclusive` may only record risk; recommended checks must be marked not executed. CLI uses `/adversarial on|off`; Web uses the “Adversarial testing” checkbox; mid-run changes return 409; state persists after refresh.

Local/Ollama cases must also cover: a healthy qualified model has estimated cost 0 under `fast`; health cooldown, unverified capability, or insufficient context cannot select solely for zero cost; a local model that only declares coding cannot take a `deep build` needing reasoning. All above tests use mocks and do not call Providers. Web manual acceptance should check at least 320px, 390px, and desktop widths; labels must not wrap character-by-character or overlap workspace buttons.

B4.3 session recovery offline verification:

```bash
python -m pytest -q tests/test_session_recovery.py tests/test_session.py tests/test_chat_router.py tests/test_chat_router_stream.py tests/test_agent.py tests/test_agent_stream.py
```

After loading an interrupted fixture, CLI must prompt `/resume continue|abandon`; Web must show a recovery banner and disable input; both sync and stream send return 409. Confirm actions must not call a Provider; the new RunJournal after continue must include `metrics.recovery`; completed steps must not enter the unfinished-step list.

B4.4 layered compaction verification:

```bash
python -m pytest -q tests/test_compactor.py tests/test_compaction_layers.py tests/test_compaction_benchmark.py tests/test_context_observability.py
python scripts/bench_compaction.py
```

All four profiles must each complete three compactions; `critical_fact_retention` is 1.0; final layer is `L0/L1/L2`; `task_relevance_ratio` is greater than 0; top-level and per-profile `provider_calls` are all 0. Schema failure cases must record fallback; if model summary calls fail, original history must not be replaced.

B4.5 incremental project index verification:

```bash
python -m pytest -q tests/test_project_index.py tests/test_memory.py tests/test_memory_tools.py tests/test_search_tools.py tests/test_read_cache.py
```

First refresh reads all indexable text; second must have `read=0`. After modifying one file only, must have `read=1`, `updated=1`, with other entries counted as reused; mtime-only change with same content hash should count as metadata_only. Corrupt YAML and project-root switch must rebuild and must not return old project search results.

B4.6 Reviewer information restriction verification:

```bash
python -m pytest -q tests/test_reviewer.py tests/test_agent_collaboration.py tests/test_collaboration_boundaries.py tests/test_engineering_verification.py
```

Restricted sentinels must not appear in the Reviewer prompt; files, real commands, Evidence, Verification, and Requirement must be present; full mode should include Worker body. Under both modes, failed Workers and `audit.can_complete=false` must force `passed=false`; RunJournal collaboration metrics must record the actual mode.

S5 local real reports:

```bash
mao
/report session
/report today
```

Web workspace “Engineering summary” can switch this session / today. Explicit inputs like “please generate this session’s engineering report” or “summarize today’s operations” also read RunJournal directly and show 0 tokens; report facts all carry run_id and do not call a Provider.

### Distribution package and empty-directory first use (offline Provider acceptance)

```bash
python -m pip install build wheel
python scripts/verify_distribution.py
```

This script builds wheel/sdist in a temp directory and installs the wheel plus declared dependencies in a temp venv that does not inherit system packages; it verifies the distribution package does not include `tests/`, `docs/`, `.github/`, or reference snapshots, then verifies non-interactive `mao` prompts, command help, Web config page, and `/health` in an unconfigured empty directory. The script does not call a Provider and does not modify global pipx installs.

---

## 1. Tool discovery (simplest—do this first)

In CLI, enter:
```
/tools
```
**Expected**: List 14 built-in tools, including:
`read_file`, `write_file`, `edit_file`, `discover_project_commands`, `run_command`, `list_dir`, `project_tree`, `git_status`, `glob_files`, `grep_content`, `search_project_files`, `search_memory`, `web_search`, `fetch_url`, `word_count`.

---

## 2. New tool hands-on

In CLI, enter the following in order and observe whether each triggers the corresponding tool:

| Input | Expected tool | Expected result |
|---|---|---|
| `Search for Python 3.13 new features and summarize` | web_search | Search result list + summary |
| `Fetch https://example.com and tell me the page content` | fetch_url | Page text summary |
| `Use list_dir to view E:\multi-agent-orchestrator` | list_dir | Cross-platform directory listing |
| `Use glob_files to list all .py files in the project` | glob_files | File path list |
| `Use grep_content to search the project for all "def main"` | grep_content | Matching file:line |
| `Read src/tools/registry.py and explain ToolRegistry` | read_file | Explain after reading the file |

**Permission tips**: Default `approve` mode confirms each time; enter `y` to allow, or `auto` to switch to automatic. `/auto`, `/approve`, `/readonly` switch modes; Shift+Tab quick-switches.

---

## 3. Hooks (audit log)

```bash
# Copy example config (remove .example suffix)
copy config\hooks.yaml.example config\hooks.yaml
```

`hooks.yaml` enables audit hooks by default (`audit_pre`/`audit_post`), writing every tool call to `logs/tool_audit.log`.

Restart CLI (`python run.py chat`), run any tool call, then:
```bash
type logs\tool_audit.log
```
**Expected**: Log contains `CALL <tool_name>` and `OK/ERR <tool_name>` lines.

> Hooks also support custom: write `pre`/`post` lists in `hooks.yaml`, each item an importable `module:function` path. See section 5 of `docs/tool-development-guide.md`.

Failure acceptance: temporarily write a nonexistent Hook path and restart. Expected: CLI shows a redacted config summary but can still enter chat; summary must not show keys, env values, full commands, or raw exceptions. Web can visit `http://127.0.0.1:8123/api/diagnostics/extensions` for up to 10 diagnostics while `/health` still returns `{"status":"ok"}`.

---

## 4. Native tool_use (Claude-like)

Default is Markdown mode. Enable native mode: edit `config/providers.yaml` and add under the main model config:

```yaml
models:
  glm-ark:                      # your main model
    provider: glm
    model_id: glm-4.6
    # ... other fields
    native_tools: true          # add this line to force native tool_use
    # or: add tool_use under capabilities to auto-enable
    # capabilities: [tool_use, coding, reasoning]
```

Restart CLI and send a task that needs tools (e.g. “read README.md”).

**How to confirm native mode is active**:
- Open the current session YAML (`sessions/<session_id>.yaml`) and inspect the first system message:
  - **Native mode**: does not contain ```` ```tool: ```` code blocks (tool definitions go via the `tools=` parameter).
  - **Markdown mode**: contains tool blocks such as ```` ```tool:read_file ````.
- Behavioral difference: in native mode the model uses structured function calls; tool calls are more stable.

> Note: the model itself must support function calling (Claude / GLM-4.6 / Kimi etc.). Unsupported models keep Markdown fallback and remain usable.

---

## 5. Automatic compaction (long sessions without interruption)

To make observation easier, artificially lower the trigger threshold. Edit the main model in `config/providers.yaml`:
```yaml
  glm-ark:
    # ...
    max_context_tokens: 8000   # lower; compaction triggers around 6000 tokens
```

Enter CLI and create a long conversation:
- Many back-and-forth turns (10+), or have the model read large files (e.g. `read src/gateway/provider.py`).
- Continue until near the threshold.

**Expected**:
- Conversation does not error with “context too long” and can continue.
- (Optional) Temporarily add logging: when `_maybe_compact_context` in `src/core/agent.py` returns True, compaction was triggered.

> After verification, restore `max_context_tokens` to the real value (e.g. 131072 for GLM-4.6); otherwise early compaction wastes tokens.

---

## 6. MCP external tools (optional, install required)

```bash
pip install mcp
copy config\mcp.yaml.example config\mcp.yaml
```

`mcp.yaml` defaults to `@modelcontextprotocol/server-filesystem` (needs Node.js/npx). Ensure npx works:
```bash
npx -v
```

Restart CLI and enter `/tools`:
**Expected**: List includes tools exposed by the MCP server (e.g. `read_file`, `write_file` from the filesystem server; names may collide with built-ins—built-ins take priority).

Call an MCP-unique tool to verify. If the server fails to start, check `mcp.yaml` command/args.

> MCP adapter code and mock tests are already done; this section verifies optional dependency, Node environment, and real connectivity to a concrete Server.

---

## 7. Local LLM (optional)

### Method A: Ollama (recommended)
1. Install Ollama: https://ollama.com
2. Pull a model: `ollama pull qwen2.5:7b`
3. Start the Ollama service (default port 11434)
4. Add to `config/providers.yaml` (see `config/providers.yaml.example`):
   ```yaml
   providers:
     ollama:
       name: ollama
       type: ollama
       base_url: http://localhost:11434/v1
       api_keys: []
       timeout: 300
   models:
     qwen-local:
       provider: ollama
       model_id: qwen2.5:7b
       capabilities: [coding]
       max_context_tokens: 32768
   main_model: qwen-local   # switch to main model
   ```
5. Restart CLI; chat uses the local model (billing shows $0).

### Method B: llama.cpp in-process
```bash
pip install llama-cpp-python
```
Download a GGUF model; configure `type: llamacpp` in providers.yaml with `base_url` as the GGUF path (see example).

---

## Common issues

| Symptom | Check |
|---|---|
| `/tools` missing new tools | Confirm `src/tools/worker_tools.py` imports the corresponding tool module at the top |
| Tool call rejected | Currently `readonly` or `approve` not confirmed; `/auto` for automatic |
| Native mode not active | Model does not support function calling; or `native_tools` not added to main model |
| MCP tools missing | `pip install mcp`; check `config/mcp.yaml`; see if npx can start the server |
| Web UI tools not shown | Web loads extensions in lifespan; confirm corresponding yaml exists under `config/` |

---

## 8. Stability automatic verification (no real models)

```bash
python -m pytest -q tests/test_gateway_failover.py tests/test_connection_test.py
python -m pytest -q tests/test_worker.py tests/test_worker_e2e.py
python -m pytest -q tests/test_chat_router_stream.py tests/test_chat_command_mode.py
python scripts/demo_failover.py
```

Covers: three-level fallback, 5-hour quota cooldown, request errors do not mis-switch, Coding Plan Bearer, Worker multi-turn read/write, native tool protocol, ban on `generated_N`, CLI/Web failover notifications.

`/test-models` sends a minimal request to each model and consumes a small amount of tokens; it is not offline verification—do not run it in unattended regression.

---

## Verification record recommendations

After each verification item, keep the following in the corresponding Issue, PR, or release acceptance record:
- Verification time, model, mode
- Whether actual behavior matched expectations
- Issues found

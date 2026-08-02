# Phase 6: Tool Ecosystem and External Integration

## Context

Phase 5 (long-term memory and project context) is 100% complete. Next is **Phase 6: Tool Ecosystem and External Integration**, so the Agent is no longer limited to local files and commands and can access external information, call web services, and integrate more tools.

## Progress

| Capability | Status |
|---|---|
| Unified tool registry `src/tools/registry.py` | ✅ Done |
| Web search `web_search` | ✅ Done |
| URL fetch `fetch_url` | ✅ Done |
| Agent / Worker / Provider registry-driven | ✅ Done |
| CLI / Web tool display generalized | ✅ Done |
| Streaming retry dedup | ✅ Done |
| Automatic model failover | ✅ Done |
| Collaboration Worker multi-round tool loop | ✅ Done |
| Explicit file outputs (ban generated_N) | ✅ Done |
| Claude-style `/` command dynamic completion | ✅ Done |
| CLI tool-loop final answer visibility | ⏳ Phase 6.6 P0 |
| Project tree tool and `/tree` command | ⏳ Phase 6.6 P1 |
| Web project file tree | ⏳ Phase 6.6 P2 |
| Code execution sandbox | ⏳ Planned |
| MCP adapter (stdio / SSE) | ✅ Done, optional dependency |
| UI tool config panel | ⏳ Planned |

## Goal

Expand Agent tool capabilities, establish a unified tool registration and management mechanism, and integrate high-frequency external tools:

1. **Unified tool registry**: `src/tools/registry.py` ✅
2. **Built-in high-frequency tools**:
   - Web search (DuckDuckGo; optional `duckduckgo-search` enhancement) ✅
   - URL fetch (fetch page content and convert to Markdown) ✅
3. **Optional enhancements** (later iterations):
   - Code execution sandbox
   - More MCP Server presets and real-environment verification
   - IDE plugin / VS Code extension
4. **UI configuration** (later iterations): Add external tool API Key / MCP server settings on the connection config page.

## Implemented

### Unified Tool Registry

`src/tools/registry.py` provides a `ToolRegistry` singleton:

- Decorator `@tool_registry.register(name, description, params, category)` registers tools.
- `build_instructions(tool_names=None)` auto-generates tool instructions for the system prompt (Markdown code block examples).
- `execute(name, params, base_dir, allowed_prefixes)` unified execution; auto-injects `base_dir` / `allowed_prefixes`; exceptions fall back to `ToolResult(success=False)`.
- Tools classified by `category`: `read` / `write` / `execute` / `external` / `unsafe`.

Built-in tools auto-register on import of `src/tools/worker_tools.py`, 12 total: `read_file`, `write_file`, `edit_file`, `run_command`, `list_dir`, `glob_files`, `grep_content`, `search_project_files`, `search_memory`, `web_search`, `fetch_url`, `word_count`.

### Web Tools `src/tools/web_tools.py`

- `web_search(query, top_n=5)`: Prefer optional dependency `duckduckgo-search`; if not installed, fall back to scraping DuckDuckGo lite HTML. Returns a Markdown list (title, link, snippet).
- `fetch_url(url, max_length=8000)`: Fetch page with `urllib` (1MB limit, set UA, handle gzip); extract title/body/links with `html.parser` into simple Markdown.
- Both `category=external`, depend only on the standard library, no new hard dependencies.
- Honor permission modes: `readonly` rejects, `approve` triggers confirmation (same as local tools).

### Integration Point Changes

- `src/core/agent.py`: `TOOL_INSTRUCTIONS` constant replaced by `tool_registry.build_instructions()` + `TOOL_RULES`; `_build_permission_message()` generalized to show key fields such as `path`/`command`/`url`/`query` for any tool.
- `src/core/worker.py`: `build_tool_instructions()` now calls the registry.
- `src/gateway/provider.py`: Removed 4 places that filtered `path/content/command` params; native `tool_use` / `tool_calls` params are fully passed through as Markdown blocks so new tool params are not dropped.
- `src/tools/worker_tools.py`: `execute_tool_call()` delegates to `tool_registry.execute()`.
- `src/cli/chat_command.py`: Tool-call display adds `WebSearch` / `Fetch` with a generic fallback for unknown tools; `/tools` command is generated dynamically from the registry.
- `src/ui/static/js/chat.js`: Permission cards and turn record show any tool generically.
- `config/workers.yaml`: Grant `web_search` / `fetch_url` to `architect` / `frontend_dev` / `backend_dev` / `tester`.

### Streaming Retry Dedup

- **Problem**: When `GatewayClient.chat_stream()` hits an exception mid-stream, it retried from the start, causing already-emitted content to be sent again; users saw overlapping/duplicated answers.
- **Fix**: Retry only when **no chunk has been produced yet**; once output has started, surface the error and do not retry.
- **File**: `src/gateway/client.py`

### Automatic Model Failover

- **Problem**: When the main model quota is exhausted or connection fails, the request failed immediately without using a backup model.
- **Implementation**:
  - `ModelConfig` adds `fallback_models`, `failover_enabled`, `failover_cooldown_seconds`.
  - `providers.yaml` supports global `default_failover_chain`.
  - `GatewayClient.chat()` / `chat_stream()` recursively expand the fallback chain, support `A -> B -> C`, and auto-break cycles.
  - Error classification: auth/request-parameter errors surface directly; switch only on model unavailable and 429; connection errors allow retry then switch.
  - Health cooldown: prefer `Retry-After`; can also parse windows like `5-hour` from error text.
  - On switch, notify CLI and Web via `StreamChunk(type="failover")` / `ChatStreamEvent(type="model_failover")`.
- **CLI diagnostics**: `/test-models` sends a minimal request through the Provider's formal auth path; failed models enter cooldown immediately; the command warns about small token usage.
- **Files**: `src/gateway/client.py`, `src/models/schemas.py`, `config/providers.yaml`, `src/core/agent.py`, `src/cli/chat_command.py`, `src/ui/static/js/chat.js`, `src/ui/static/css/style.css`

### Collaboration Worker Stability Wrap-Up

- Worker supports up to 5 tool-loop rounds; directory/file read results are fed back to the model for continued work.
- Older configs that already granted read ability automatically get `list_dir` / `glob_files` / `grep_content` / `read_file` filled in.
- Worker may only call config-authorized tools; Markdown and native `tool_use` share the same tool whitelist.
- Native mode no longer also injects Markdown tool instructions, avoiding protocol conflicts.
- Agent / Worker / Reviewer no longer generate `generated_N` project files from body code blocks.
- When the model only pastes code blocks, first require `write_file`; if still not executed, keep content in `content.txt` and mark the task failed to avoid false success and content loss.

## Principles

- Keep the project lean; prioritize the most common and stable tools.
- Do not introduce unnecessary dependencies; prefer standard library or lightweight third-party libraries.
- New tools must register via the registry so CLI and Web pick them up automatically.
- External tool calls must honor the current permission mode (auto/approve/readonly).

## Expected Key Files

- `src/tools/registry.py` - Tool registry ✅
- `src/tools/web_tools.py` - Web search, URL fetch ✅
- `src/ui/routers/tools.py` - Tool list/config API (later)
- `src/ui/static/js/tools.js` - Tool config frontend (later)
- `src/ui/templates/index.html` - Add tool config panel (later)
- `src/core/agent.py` - Load tool instructions from registry ✅
- `src/tools/worker_tools.py` - Execute tools via registry ✅

## Completion Criteria

- Agent can complete “search XXX and summarize” style tasks via tool calls. ✅
- Permission confirmation for new tools matches local tools. ✅
- `python -m pytest -q` all green. ✅
- Web UI can configure/disable external tools. (later iteration)

## Verification

- Unit tests: `tests/test_registry.py`, `tests/test_web_tools.py` (all network mocked), `tests/test_gateway_failover.py`.
- Full regression: `python -m pytest -q` passes with `374 passed`.
- CLI: `python run.py chat`, input “search for the latest Claude Code features”; Agent calls `web_search` and summarizes.
- Web: On `/chat` send “fetch https://example.com and summarize”; right sidebar turn record shows `fetch_url`.
- Failover: On main model 429/connection failure, CLI/Web show a yellow notice and auto-switch to backup model.
- Free mock demo: `python scripts/demo_failover.py`; output written to system temp directory.

## Out of Scope for This Round

- Large-scale MCP ecosystem integration (adapter framework first; specific servers added as needed later).
- Browser automation / complex crawlers.
- Packaging/distribution (executables, VS Code plugins, etc.).

## Next Iteration

Phase 6.6 is complete: fixed final-answer not displayed after single-Agent tool loops, and implemented cross-platform `project_tree`, zero-token `/tree`, and Web file tree.

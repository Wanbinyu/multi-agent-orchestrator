# Local LLM Integration and Extension Points

**Status**: Current  
**Updated**: 2026-07-25  

> Enable MAO to use local LLMs (Ollama / llama.cpp) and reserve extension points for future features (MCP, etc.).  
> Phase: Phase 6.1+ local LLM integration.  
> Relation to the global compatibility matrix: local models usually have `metadata_source=unverified` or user-supplied values; zero marginal cost is only a routing score and **must not** bypass health cooldowns, verified capabilities, or context budgets. See [`Provider-compatibility-matrix.md`](Provider-compatibility-matrix.md).

---

## 1. Transformer Decoder and MAO (Background)

- **Transformer Decoder** is the network architecture of modern LLMs (GPT/Claude/Llama/Qwen/GLM/Kimi).
- **MAO is an orchestration layer**, not a Transformer: it schedules, runs tool loops, and manages memory/permissions; intelligence comes from the LLMs it calls.
- "Adding an LLM to MAO" ≠ "implementing a Transformer in MAO"; it means **letting MAO load/call a local Transformer model**. The model itself is hosted by Ollama / llama.cpp; MAO only handles invocation.

---

## 2. Two Ways to Connect Local LLMs

### Approach A: Ollama (Recommended, Fastest)

Ollama exposes an OpenAI-compatible endpoint; MAO reuses the existing `OpenAICompatibleProvider` with almost no code.

1. Install Ollama: https://ollama.com
2. Pull a model: `ollama pull qwen2.5:7b`
3. Add to `config/providers.yaml`:

```yaml
providers:
  ollama:
    name: ollama
    type: ollama
    base_url: http://localhost:11434/v1
    api_keys: []          # no key required
    timeout: 300

models:
  qwen-local:
    provider: ollama
    model_id: qwen2.5:7b
    input_price_per_1m: 0.0
    output_price_per_1m: 0.0
    capabilities: [coding]
    context_window_tokens: 32768
    context_window_source: user_configured
```

4. Set as main model: `main_model: qwen-local`, or switch in the Web UI model selector.

### Approach B: In-Process llama.cpp (Truly Built-In)

Load a GGUF model directly into the MAO process with no external service.

1. Install: `pip install llama-cpp-python`
2. Download a GGUF model (e.g. `Qwen2.5-7B-Instruct-Q4_K_M.gguf` on HuggingFace)
3. Configure:

```yaml
providers:
  llamacpp:
    name: llamacpp
    type: llamacpp
    base_url: "D:/models/qwen2.5-7b-instruct-q4_k_m.gguf"   # GGUF path
    api_keys: []
    timeout: 600
    extra:
      n_ctx: 4096
      n_gpu_layers: 0      # 0=CPU only; set layer count if GPU available
      n_threads: 8

models:
  qwen-llamacpp:
    provider: llamacpp
    model_id: qwen2.5-7b-instruct
    context_window_tokens: 4096
    context_window_source: user_configured
```

- Models are **lazy-loaded**: loaded into memory/VRAM only on first call.
- If `llama-cpp-python` is not installed, a clear error is returned; other providers are unaffected.
- Local model `cost_usd` is always 0.

### Trade-offs and Recommendations

| | Ollama | llama.cpp | Cloud API |
|---|---|---|---|
| Ease of setup | Very low | Medium | Low |
| Dependencies | Separate service | In-process library | None |
| Offline/privacy | ✅ | ✅ | ❌ |
| Billing | Free | Free | Usage-based |
| Coding ability | Medium (model-dependent) | Medium | High (Claude/GLM-ark) |
| Speed | Medium | Medium (CPU slow) | Fast |

Local small models (7B–14B) are weaker than Claude / GLM-ark on complex coding tasks; they suit offline, privacy, or zero-cost scenarios, or as auxiliary Workers in collaboration.

---

## 3. Extension Points (Reserved for Future Features)

To lower future refactor cost, MAO establishes extension points. Only **currently needed** ones are built now; others wait until needed.

### 1. ToolSource Protocol and MCP Implementation

`src/tools/registry.py` defines the `ToolSource` protocol; `src/tools/mcp_adapter.py` implements `MCPToolSource`:

```python
@runtime_checkable
class ToolSource(Protocol):
    def list_tools(self) -> list[ToolSpec]: ...
    def execute(self, name: str, params: dict) -> ToolResult: ...
```

`ToolRegistry` adds `add_source(source)`:
- After registration, tools from external sources effectively appear in `list_tools()` / `build_instructions()`;
- `execute()` prefers local tools, then external sources on miss;
- Local same-name tools take priority.

Phase 6.4 completed MCP integration: stdio / SSE, lazy connection, sync/async bridging, and config loading. After optionally installing the `mcp` package and configuring `config/mcp.yaml`, `load_extensions()` auto-registers sources **without changing the registry skeleton**.

### 2. ProviderConfig.extra (Provider-Specific Parameters)

`ProviderConfig` gains an `extra: dict` field for provider-specific parameters (e.g. llamacpp `n_ctx`/`n_gpu_layers`). Future providers can reuse this field without schema changes.

### 3. Reserved but Not Yet Built

The following extension points **do not have files yet**; build when needed (avoid dead code):
- `EmbeddingProvider` (vector memory retrieval)
- `SubagentSpawner` (parallel sub-agents)

Each will follow the same "protocol + registration point + placeholder" pattern as ToolSource.

---

## 4. Related Files

- `src/gateway/local_provider.py` - OllamaProvider / LocalLlamaCppProvider
- `src/gateway/provider.py` - `create_provider()` supports `ollama` / `llamacpp` types
- `src/models/schemas.py` - `ProviderConfig.type` extensions, `extra` field, and model context budget config
- `src/tools/tool_sources.py` - MCPToolSource compatibility export
- `src/tools/mcp_adapter.py` - MCP stdio / SSE implementation
- `src/core/hooks.py` - Pre/post tool-call interception
- `src/tools/registry.py` - `add_source()` + external source discovery/execution
- `config/providers.yaml.example` - Ollama / llamacpp config examples
- `tests/test_local_provider.py` / `tests/test_tool_sources.py` - tests

---

*Local LLM and extension-point integration is complete; current regression status follows the root README and CI.*

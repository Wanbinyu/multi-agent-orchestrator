# 本地 LLM 接入与扩展点

> 让 MAO 能使用本地 LLM（Ollama / llama.cpp），并为未来功能（MCP 等）预留扩展点。
> 阶段：Phase 6.1+ 本地 LLM 接入。

---

## 一、Transformer Decoder 与 MAO 的关系（背景）

- **Transformer Decoder** 是现代 LLM（GPT/Claude/Llama/Qwen/GLM/Kimi）的网络架构。
- **MAO 是编排层**，不是 Transformer：它调度、管工具循环、管记忆/权限，智能来自它调用的 LLM。
- "把 LLM 加到 MAO" ≠ "让 MAO 实现 Transformer"，而是**让 MAO 能加载/调用本地 Transformer 模型**。模型本身由 Ollama / llama.cpp 运行时承载，MAO 只管调用。

---

## 二、两种本地 LLM 接入方式

### 方式 A：Ollama（推荐，最快）

Ollama 暴露 OpenAI 兼容端点，MAO 复用现有 `OpenAICompatibleProvider`，几乎零代码。

1. 安装 Ollama：https://ollama.com
2. 拉模型：`ollama pull qwen2.5:7b`
3. 在 `config/providers.yaml` 加：

```yaml
providers:
  ollama:
    name: ollama
    type: ollama
    base_url: http://localhost:11434/v1
    api_keys: []          # 无需 key
    timeout: 300

models:
  qwen-local:
    provider: ollama
    model_id: qwen2.5:7b
    input_price_per_1m: 0.0
    output_price_per_1m: 0.0
    capabilities: [coding]
    max_context_tokens: 32768
```

4. 设为主模型：`main_model: qwen-local`，或在 Web UI 模型选择器切换。

### 方式 B：llama.cpp 进程内加载（真正内置）

把 GGUF 模型直接加载进 MAO 进程，不依赖外部服务。

1. 安装：`pip install llama-cpp-python`
2. 下载 GGUF 模型（如 HuggingFace 上的 `Qwen2.5-7B-Instruct-Q4_K_M.gguf`）
3. 配置：

```yaml
providers:
  llamacpp:
    name: llamacpp
    type: llamacpp
    base_url: "D:/models/qwen2.5-7b-instruct-q4_k_m.gguf"   # GGUF 路径
    api_keys: []
    timeout: 600
    extra:
      n_ctx: 4096
      n_gpu_layers: 0      # 0=纯CPU；有 GPU 填层数
      n_threads: 8

models:
  qwen-llamacpp:
    provider: llamacpp
    model_id: qwen2.5-7b-instruct
    max_context_tokens: 4096
```

- 模型**懒加载**：首次调用时才载入内存/显存。
- 未安装 `llama-cpp-python` 时给出清晰错误，不影响其他 provider。
- 本地模型 `cost_usd` 恒为 0。

### 代价与建议

| | Ollama | llama.cpp | 云端 API |
|---|---|---|---|
| 上手难度 | 极低 | 中 | 低 |
| 依赖 | 独立服务 | 进程内库 | 无 |
| 离线/隐私 | ✅ | ✅ | ❌ |
| 计费 | 免费 | 免费 | 按量 |
| 编码能力 | 中（看模型） | 中 | 高（Claude/GLM-ark） |
| 速度 | 中 | 中（CPU 慢） | 快 |

本地小模型（7B-14B）在复杂编码任务上弱于 Claude / GLM-ark，适合离线、隐私、零成本场景或作为协作中的辅助 Worker。

---

## 三、扩展点（为未来功能预留位置）

为降低未来重构成本，MAO 建立了扩展点机制。当前只建**当前需要的**，其余等用到再建。

### 1. ToolSource 协议与 MCP 实现

`src/tools/registry.py` 定义 `ToolSource` 协议；`src/tools/mcp_adapter.py` 已实现 `MCPToolSource`：

```python
@runtime_checkable
class ToolSource(Protocol):
    def list_tools(self) -> list[ToolSpec]: ...
    def execute(self, name: str, params: dict) -> ToolResult: ...
```

`ToolRegistry` 新增 `add_source(source)`：
- 注册后，外部工具源的工具有效出现在 `list_tools()` / `build_instructions()` 中；
- `execute()` 优先本地工具，未命中再查外部源；
- 本地同名工具优先。

Phase 6.4 已完成 MCP 接入：支持 stdio / SSE、懒连接、同步/异步桥接和配置加载。安装可选 `mcp` 包并配置 `config/mcp.yaml` 后，由 `load_extensions()` 自动注册，**不改 registry 骨架**。

### 2. ProviderConfig.extra（Provider 专属参数）

`ProviderConfig` 新增 `extra: dict` 字段，承载 provider 专属参数（如 llamacpp 的 `n_ctx`/`n_gpu_layers`）。未来新 provider 可复用此字段，无需改 schema。

### 3. 预留但未建的扩展点

以下扩展点**尚未建文件**，等用到再建（避免死代码）：
- `EmbeddingProvider`（向量记忆检索）
- `SubagentSpawner`（子 Agent 并行）

每个届时按 ToolSource 同样的"协议 + 注册点 + 占位"模式建立。

---

## 四、相关文件

- `src/gateway/local_provider.py` - OllamaProvider / LocalLlamaCppProvider
- `src/gateway/provider.py` - `create_provider()` 支持 `ollama` / `llamacpp` 类型
- `src/models/schemas.py` - `ProviderConfig.type` 扩展、`extra` 字段、`ModelConfig.max_context_tokens`
- `src/tools/tool_sources.py` - MCPToolSource 兼容导出
- `src/tools/mcp_adapter.py` - MCP stdio / SSE 实现
- `src/core/hooks.py` - 工具调用前后拦截
- `src/tools/registry.py` - `add_source()` + 外部源发现/执行
- `config/providers.yaml.example` - Ollama / llamacpp 配置示例
- `tests/test_local_provider.py` / `tests/test_tool_sources.py` - 测试

---

*本地 LLM 与扩展点接入完成。回归测试 284 passed。*

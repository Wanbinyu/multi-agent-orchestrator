# CCswitch 学习笔记

> 仓库地址：https://github.com/farion1231/cc-switch  
> 学习方式：直接阅读 GitHub 上的 README、package.json、Cargo.toml 以及关键源码文件，未执行 clone 或其它本地操作。

---

## 一、项目定位与技术栈

**CCswitch** 全称是 **"Claude Code Switch"**，定位是跨平台桌面端的 **All-in-One Assistant**，主要面向 Claude Code、Codex、Gemini CLI、OpenCode、OpenClaw、Hermes Agent 等 AI 编程工具。目标一句话：**不再手动编辑 JSON/TOML/.env 配置文件**，用一个可视化界面统一管理多工具、多 provider。

### 技术栈

- **前端**：Tauri 2 + React 18 + TypeScript + Vite
- **后端**：Rust（Tauri 原生层）
- **数据库**：SQLite（`~/.cc-switch/cc-switch.db`）
- **本地代理**：Rust 实现，基于 `axum` + `tower` + `hyper` + `reqwest`
- **本地配置**：`~/.cc-switch/settings.json`、`~/.cc-switch/backups/`

### 核心依赖

- `axum` / `tower` / `hyper`：本地 HTTP 代理服务
- `reqwest`：上游 HTTP 请求客户端，支持 SOCKS、流式、TLS
- `rusqlite`：本地 SQLite 数据持久化
- `serde` / `serde_json` / `serde_yaml` / `toml`：配置序列化
- `rquickjs`：脚本能力（如 usage 查询脚本）

---

## 二、整体架构

CCswitch 不是简单的"配置编辑器"，它由三层组成：

```
┌─────────────────────────────────────┐
│         Tauri + React UI            │  ← 配置界面、托盘、导入导出
├─────────────────────────────────────┤
│     Rust Services / Commands        │  ← 业务逻辑、数据库、文件同步
├─────────────────────────────────────┤
│   Local Proxy (axum + hyper)        │  ← 请求转发、协议转换、故障转移
└─────────────────────────────────────┘
```

### 1. 配置管理层

- 所有 provider 配置以 **SQLite 为单一数据源**。
- 切换 provider 时，把配置写入各 CLI 工具的"实时配置文件"（live config）。
- 编辑当前激活 provider 时，会**从 live config 反向回填**（dual-way sync）。
- 写文件使用 **temp file + rename** 原子写入，防止配置损坏。

### 2. 本地代理层

- 在本地启动 HTTP 代理服务器。
- 各 AI 工具把请求发给本地代理，代理再转发到真实上游 provider。
- 支持协议转换、自动故障转移、熔断、健康检查、请求修正。

---

## 三、Provider 预设体系

### 1. ProviderPreset 接口关键字段

```ts
interface ProviderPreset {
  id: string;              // 唯一标识
  name: string;            // 显示名
  category: string;        // official / aggregator / third_party / cn_official / cloud_provider
  settingsConfig: {
    env: Record<string, string>;  // 对应 Claude Code 等工具的环境变量
  };
  apiKeyField?: string;    // 使用 ANTHROPIC_AUTH_TOKEN 还是 ANTHROPIC_API_KEY
  apiFormat?: string;      // anthropic / openai_chat / openai_responses / gemini_native
  endpointCandidates?: string[];  // 候选 endpoint，用于测速/切换
  templateValues?: Record<string, { default: string }>; // 用户填写的模板变量
  // ...
}
```

### 2. 预设分类

CCswitch 内置 **50+ provider presets**，大致分类：

- **official**：Anthropic 官方
- **aggregator**：聚合平台，如 OpenRouter、SiliconFlow、七牛等
- **third_party**：各种第三方 relay / 转发服务
- **cn_official**：国内官方兼容层
  - 火山方舟 Coding Plan：`https://ark.cn-beijing.volces.com/api/coding`，模型 `ark-code-latest`
  - DeepSeek：`https://api.deepseek.com/anthropic`
  - 智谱 GLM：`https://open.bigmodel.cn/api/anthropic`
  - Kimi：`https://api.moonshot.cn/anthropic`、`https://api.kimi.com/coding/`
  - 百度千帆、阿里云百炼、阶跃星辰、MiniMax 等
- **cloud_provider**：AWS Bedrock、NVIDIA NIM 等

### 3. 关键发现：国内 Coding Plan 大多是 Anthropic 兼容协议

从预设配置可以看到：

- 火山方舟 Coding Plan 的 `base_url` 是 `https://ark.cn-beijing.volces.com/api/coding`
- DeepSeek  anthropic 端点是 `https://api.deepseek.com/anthropic`
- 智谱 GLM  anthropic 端点是 `https://open.bigmodel.cn/api/anthropic`
- Kimi For Coding 是 `https://api.kimi.com/coding/`

这些不是 OpenAI 兼容接口，而是 **Anthropic Messages API 兼容接口**。Claude Code 等工具天然使用 Anthropic 协议，所以直接修改 `ANTHROPIC_BASE_URL` 和 `ANTHROPIC_AUTH_TOKEN` 即可接入。

### 4. apiFormat 与协议转换

即使都是 Anthropic 兼容接口，上游实际协议可能不同。CCswitch 用 `apiFormat` 标记：

| apiFormat | 含义 |
|-----------|------|
| `anthropic` | 上游就是 Anthropic Messages API，直接透传 |
| `openai_chat` | 上游是 OpenAI Chat Completions，需要 Anthropic ↔ OpenAI 互转 |
| `openai_responses` | 上游是 OpenAI Responses API（Codex 使用） |
| `gemini_native` | 上游是 Gemini generateContent API |

例如 NVIDIA NIM 的 preset 配置为 `apiFormat: "openai_chat"`，模型是 `moonshotai/kimi-k2.5`。

---

## 四、配置同步机制

### 1. 双向同步

CCswitch 的核心设计是 **Dual-way Sync**：

- **切换 provider 时写入 live files**：把当前 provider 的配置写到 Claude Code、Codex、Gemini CLI 各自的配置文件中。
- **编辑时反向回填**：如果用户直接编辑当前激活 provider，CCswitch 会从 live files 读取最新值回填到 UI，避免覆盖用户手动修改。

### 2. 原子写入

配置写入使用：

```rust
// 伪代码
let temp_path = path.with_extension("tmp");
write(&temp_path, content)?;
rename(&temp_path, path)?;
```

避免写一半崩溃导致配置文件损坏。

### 3. 各工具配置映射

| 工具 | 写入的位置/环境变量 |
|------|---------------------|
| Claude Code | `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_MODEL` 等环境变量或 settings.json |
| Claude Desktop | 桌面端配置 + MCP 配置 |
| Codex | `auth.OPENAI_API_KEY` + TOML `config`，base_url 仅在纯 origin 时自动追加 `/v1` |
| Gemini CLI | `GOOGLE_GEMINI_BASE_URL`、`GEMINI_API_KEY`、`GEMINI_MODEL` |
| OpenCode / OpenClaw / Hermes | 各自的配置文件 |

### 4. Universal Provider

CCswitch 提供 **Universal Provider** 预设，目标是"一份配置同步到多个工具"。典型如 NewAPI 聚合网关：

- 同一个 `base_url` + `api_key`
- 对 Claude Code 生成 Anthropic 配置
- 对 Codex 生成 OpenAI 配置（模型如 `gpt-5.5`）
- 对 Gemini CLI 生成 Gemini 配置（模型如 `gemini-3.5-flash`）

---

## 五、本地代理与协议转换

### 1. 代理服务器启动

Rust 后端用 `axum` 启动本地 HTTP 服务，监听地址和端口可配置（默认一般绑定到 `127.0.0.1` 某个端口）。

### 2. 请求处理入口

`handlers.rs` 是 Axum 路由入口，主要端点：

- `/v1/messages`：Claude Messages API
- `/claude-desktop`：Claude Desktop 网关
- `/v1/chat/completions`：OpenAI Chat Completions（也用于 Codex）
- `/v1/responses*`：OpenAI Responses API（Codex）
- `/v1beta/models/...`：Gemini Native API

### 3. 请求转发流程

```
Claude Code 客户端
       ↓
  本地代理 /v1/messages
       ↓
  解析请求体、模型名
       ↓
  ProviderRouter 选择上游 provider
       ↓
  ModelMapper 做模型名映射
       ↓
  ClaudeAdapter 判断 apiFormat
       ↓
  需要转换？→ anthropic_to_openai / anthropic_to_responses / anthropic_to_gemini
       ↓
  构造认证头、发送上游请求
       ↓
  接收响应、反转换、返回给客户端
```

### 4. 认证头映射

`AuthStrategy` 枚举区分不同上游的认证方式：

| 策略 | 请求头 |
|------|--------|
| `Anthropic` | `x-api-key` + `anthropic-version: 2023-06-01` |
| `ClaudeAuth` / `Bearer` | `Authorization: Bearer <key>` |
| `Google` | `x-goog-api-key: <key>` |
| `GoogleOAuth` | `Authorization: Bearer <access_token>` |
| `GitHubCopilot` | 附加 `editor-version`、`copilot-integration-id` 等专用头 |
| `CodexOAuth` | `Authorization: Bearer <access_token>` + `ChatGPT-Account-Id` + `originator: cc-switch` |

### 5. Anthropic ↔ OpenAI Chat Completions 转换

`transform.rs` 实现了核心字段映射。

#### Anthropic 请求 → OpenAI 请求

- `messages` 从 Anthropic 格式转换为 OpenAI 格式
- `system` 合并置顶
- `tool_use` / `tool_result` 映射为 `tool_calls` / `tool` 角色
- `tool_choice` 映射：`any` → `required`，具名工具 → `function`
- `output_config.effort` / `thinking.budget_tokens` 映射为 `reasoning_effort`
- 流式请求注入 `stream_options.include_usage`，确保能拿到 usage chunk

#### OpenAI 响应 → Anthropic 响应

| OpenAI 字段 | Anthropic 字段 |
|-------------|----------------|
| `choices[0].message.content` | `content[].text` |
| `message.reasoning_content` | `content[].thinking` |
| `message.tool_calls` | `content[].tool_use` |
| `message.function_call` | `content[].tool_use`（兼容旧格式） |
| `finish_reason` | `stop_reason` |
| `stop` → `end_turn` | |
| `length` → `max_tokens` | |
| `tool_calls` / `function_call` → `tool_use` | |
| `usage.prompt_tokens`（扣除缓存） | `usage.input_tokens` |
| `usage.completion_tokens` | `usage.output_tokens` |
| 缓存命中字段 | `cache_read_input_tokens` / `cache_creation_input_tokens` |

返回的 Anthropic 消息形状：

```json
{
  "id": "...",
  "type": "message",
  "role": "assistant",
  "content": [...],
  "model": "...",
  "stop_reason": "...",
  "stop_sequence": null,
  "usage": {...}
}
```

### 6. Anthropic ↔ OpenAI Responses API 转换

Codex 使用 OpenAI Responses API。CCswitch 在 `transform_responses.rs` 中实现：

- Anthropic 请求 → Responses 请求
- Responses SSE → Anthropic SSE
- Responses 非流 JSON → Anthropic 消息格式

Codex OAuth 场景会强制走 `openai_responses`，不可覆盖。

### 7. Anthropic ↔ Gemini Native 转换

`transform_gemini.rs` 和 `gemini_schema.rs` 处理：

- Anthropic messages → Gemini `contents` 数组
- `tools` → Gemini `tools/functionDeclarations`
- Gemini `candidates` → Anthropic `content`
- 流式 Gemini SSE → Anthropic SSE

---

## 六、模型映射

### 1. 模型名映射

`model_mapper.rs` 实现了从请求模型名到上游实际模型名的替换。配置来源是 `provider.settings_config["env"]` 中的环境变量：

| 环境变量 | 映射字段 |
|----------|----------|
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | `haiku_model` |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | `sonnet_model` |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | `opus_model` |
| `ANTHROPIC_DEFAULT_FABLE_MODEL` | `fable_model` |
| `CLAUDE_CODE_SUBAGENT_MODEL` | `subagent_model` |
| `ANTHROPIC_MODEL` | `default_model` |

### 2. 映射规则

`map_model` 对原始模型名做大小写不敏感的子串匹配：

- 包含 `fable` → `fable_model`，未配置则降级到 `opus_model`（模拟官方分类器行为）
- 包含 `haiku` → `haiku_model`
- 包含 `opus` → `opus_model`
- 包含 `sonnet` → `sonnet_model`
- 子代理模型匹配 `subagent_model`
- 其它情况 → `default_model`
- 什么都没配置 → 保持原样

### 3. 本地 1M 上下文标记剥离

CCswitch 支持本地标记 `[1M]` 表示 1M 上下文窗口。请求发到上游前会剥离该后缀，避免上游不识别。

---

## 七、故障转移与熔断

### 1. ProviderRouter

`provider_router.rs` 负责选择上游 provider：

```rust
pub struct ProviderRouter {
    db: Arc<Database>,
    circuit_breakers: Arc<RwLock<HashMap<String, Arc<CircuitBreaker>>>>,
}
```

- 从数据库读取 `proxy_config.auto_failover_enabled`
- 关闭时：只返回当前 provider
- 开启时：按故障转移队列顺序尝试（P1 → P2 → ...）
- 对每个 provider 检查熔断器 `is_available()`

### 2. 熔断器

`circuit_breaker.rs` 实现标准熔断逻辑：

- **Closed**：正常放行
- **Open**：拒绝请求，超时后进入 HalfOpen
- **HalfOpen**：按限流放行探测请求

`record_result` 记录成功/失败，更新数据库健康状态。

### 3. 错误分类与重试

`forwarder.rs` 的 `categorize_proxy_error` 把错误分为：

- **可重试**：超时、连接失败、5xx、非白名单 4xx、流空闲超时、配置/转换/认证错误等
- **不可重试**：400/405/406/413/414/415/422/501 等客户端错误、`NoAvailableProvider`

最大尝试次数 = `max_retries + 1`。所有 provider 都失败时返回 `MaxRetriesExceeded` 或 `NoAvailableProvider`。

### 4. 流式响应首包超时

`prepare_success_response_for_failover` 对流式响应会等待首个 chunk：

- 在 `streaming_first_byte_timeout` 内没有收到首包 → 认为失败，触发故障转移
- 避免上游返回 200 后一直不吐 SSE，导致代理误记成功

---

## 八、对 multi-agent orchestrator 的借鉴意义

### 1. Provider 抽象

CCswitch 把每个上游抽象为 `Provider`，包含：

- `base_url`
- `api_key` 字段名
- `apiFormat`（anthropic / openai_chat / openai_responses / gemini_native）
- `providerType`（普通、OAuth、Copilot、Codex OAuth 等）
- `settings_config` 中的环境变量/配置模板

我们的 CLI 工具可以借鉴：在 `providers.yaml` 中除了 `type: anthropic | openai`，还可以增加 `api_format` 字段，未来支持更细致的协议转换。

### 2. 模型映射层

CCswitch 的 `model_mapper` 启示：

- 不要让 Orchestrator 直接决定"发给上游的模型名"。
- 可以在 provider 配置层做"模型别名 → 真实模型名"映射。
- 支持按 tier（fable/sonnet/opus/haiku）自动映射，方便用户用一个名字统一切换。

我们的工具可以扩展 `models` 配置，支持 `aliases` 或 `tier_mapping`。

### 3. 本地代理/网关

CCswitch 最重要的架构优势是**本地代理层**：

- 用户无需修改各 CLI 工具的内部配置，只改一个代理地址。
- 代理负责路由、协议转换、故障转移、计费统计。
- 可以"应用级接管"，不同应用走不同 provider。

我们的 CLI MVP 目前是每个 worker 直接调用 `GatewayClient`。未来可以考虑：

- 启动本地轻量代理（如基于 `httpx`/uvicorn 或 Rust）
- 所有 worker 统一走本地代理
- 代理层做模型路由、多 key 轮询、失败重试、缓存、计费

### 4. 配置同步与原子写入

- 配置文件写 temp 再 rename，避免损坏。
- 双向同步：从 live config 读取回填，减少配置冲突。

### 5. 计费与 usage 解析

CCswitch 针对每种 app_type 定义 `UsageParserConfig`：

- Claude 协议解析 `usage.input_tokens` / `output_tokens`
- OpenAI 协议解析 `prompt_tokens` / `completion_tokens`
- 流式响应通过 SSE parser 提取 usage chunk

我们的工具目前已经做了 Anthropic 的 token 计费，后续可以：

- 为 OpenAI 兼容响应增加 parser
- 支持流式 usage chunk 解析
- 缓存命中 token 不计费或单独计费

### 6. 错误处理与状态码映射

CCswitch 把代理层错误统一映射为 HTTP 状态码：

- 上游错误复用上游状态码
- 超时/流空闲 → 504
- 无可用 provider → 503
- 认证错误 → 401
- 转换错误 → 422

我们可以把 `GatewayClient` 的异常统一包装，便于 worker 判断是否重试。

---

## 九、关键代码文件速查

| 文件 | 职责 |
|------|------|
| `src-tauri/src/proxy/mod.rs` | 代理模块根，声明所有子模块 |
| `src-tauri/src/proxy/handlers.rs` | Axum 路由入口，/v1/messages 等端点 |
| `src-tauri/src/proxy/forwarder.rs` | 请求转发、重试、故障转移 |
| `src-tauri/src/proxy/provider_router.rs` | provider 选择与熔断检查 |
| `src-tauri/src/proxy/model_mapper.rs` | 模型名映射 |
| `src-tauri/src/proxy/providers/claude.rs` | ClaudeAdapter：apiFormat 判定、认证头、请求转换 |
| `src-tauri/src/proxy/providers/transform.rs` | Anthropic ↔ OpenAI Chat Completions 转换 |
| `src-tauri/src/proxy/providers/transform_responses.rs` | Anthropic ↔ OpenAI Responses 转换 |
| `src-tauri/src/proxy/providers/transform_gemini.rs` | Anthropic ↔ Gemini Native 转换 |
| `src-tauri/src/proxy/providers/auth.rs` | 认证策略与请求头映射 |
| `src-tauri/src/proxy/circuit_breaker.rs` | 熔断器实现 |
| `src-tauri/src/proxy/response_processor.rs` | 响应透传、usage 解析、header 清理 |
| `src-tauri/src/provider.rs` | Provider / UniversalProvider 数据结构 |
| `src/config/claudeProviderPresets.ts` | Claude Code 的 provider 预设 |
| `src/config/codingPlanProviders.ts` | 火山方舟 Coding Plan 检测规则 |
| `src/config/universalProviderPresets.ts` | 通用网关预设（NewAPI 等） |
| `src-tauri/src/config.rs` / `provider_defaults.rs` | 配置读取与默认值 |

---

## 十、总结

CCswitch 的核心价值不是"配置 prettier"，而是：

1. **统一的 Provider 抽象**：把不同厂商的 API 抽象成同一套配置模型。
2. **本地代理层**：在本地做请求转发、协议转换、故障转移。
3. **模型映射**：让 Claude Code 等工具以为自己在调用 Claude，实际上可以转发到任意兼容接口。
4. **双向配置同步**：既方便用户切换，又不会覆盖用户手动修改。

对于我们的 multi-agent orchestrator CLI，最值得优先借鉴的是：

- **更细化的 Provider 配置**：增加 `api_format`、`provider_type`、`auth_strategy` 等字段。
- **模型别名/层级映射**：让 orchestrator 只关心能力层级（fable/sonnet/opus/haiku），具体模型名由 provider 配置映射。
- **本地网关/代理**：把多 key 轮询、重试、计费、协议转换下沉到网关层，worker 只负责业务。
- **原子写入配置**：避免配置损坏。

后续如果要把 CLI 扩展为更稳定的生产工具，可以参考 CCswitch 的 Rust 代理层设计，或者先用 Python 实现一个简化版本地网关。

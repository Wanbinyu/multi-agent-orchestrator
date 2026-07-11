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

## 十一、Provider 预设配置文件摘录（来自 GitHub 源码）

> 以下数据从 `https://github.com/farion1231/cc-switch` 的 `src/config/` 目录下载并解析。
> 字段说明：
> - **apiFormat**：上游协议格式，空表示由目标应用决定（Claude 默认 anthropic，Codex 默认 openai_responses，Gemini 默认 gemini_native）。
> - **Base URL**：实际请求地址，优先从 `baseURL` / `env.*_BASE_URL` 提取，否则留空。
> - **默认模型**：从 `model` / `env.*_MODEL` 提取的默认模型名。

### codingPlanProviders.ts（Coding Plan 路由检测规则）

| id | label | base_url 匹配正则 |
|---|---|---|
| kimi |  | （见源码正则） |
| zhipu |  | （见源码正则） |
| zhipu_team |  | （见源码正则） |
| minimax |  | （见源码正则） |
| zenmux |  | （见源码正则） |
| volcengine |  | （见源码正则） |

### universalProviderPresets.ts（统一网关预设）

该文件定义**统一供应商（Universal Provider）**，典型如 NewAPI 等聚合网关。
一份配置会同时生成 Claude / Codex / Gemini 三份输出：

| 应用 | 默认模型示例 |
|---|---|
| Claude | claude-sonnet-5 / claude-opus-4-8 / claude-haiku-4-5 |
| Codex | gpt-5.5（reasoning_effort: high） |
| Gemini | gemini-3.5-flash |

### claudeProviderPresets.ts（Claude Code Provider 预设，共 70 条）

<details>
<summary>点击展开 claudeProviderPresets.ts 完整预设表</summary>

| 名称 | 分类 | apiFormat | Base URL | 默认模型 | endpointCandidates | templateValues |
|---|---|---|---|---|---|---|
| Claude Official | official |  |  |  |  |  |
| Shengsuanyun | aggregator |  | https://router.shengsuanyun.com/api | anthropic/claude-sonnet-5 |  |  |
| PatewayAI | third_party |  | https://api.pateway.ai |  |  |  |
| 火山Agentplan | cn_official |  | https://ark.cn-beijing.volces.com/api/coding | ark-code-latest |  |  |
| BytePlus | cn_official |  | https://ark.ap-southeast.bytepluses.com/api/coding | ark-code-latest |  |  |
| DouBaoSeed | cn_official |  | https://ark.cn-beijing.volces.com/api/compatible | doubao-seed-2-1-pro-260628 |  |  |
| CCSub | aggregator |  | https://www.ccsub.net |  |  |  |
| SubRouter | aggregator |  | https://subrouter.ai |  |  |  |
| Unity2.ai | aggregator |  | https://api.unity2.ai |  |  |  |
| Qiniu | aggregator |  | https://api.qnaigc.com | Pro/MiniMaxAI/MiniMax-M2.7 | https://api.qnaigc.com<br>https://api.modelink.ai |  |
| FennoAI | aggregator |  | https://api.fenno.ai |  |  |  |
| ZetaAPI | aggregator |  | https://api.zetaapi.ai |  |  |  |
| TeamoRouter | aggregator |  | https://api.teamorouter.com |  |  |  |
| Amux | aggregator |  | https://api.amux.ai |  |  |  |
| Gemini Native | third_party | gemini_native | https://generativelanguage.googleapis.com | gemini-3.5-flash | https://generativelanguage.googleapis.com |  |
| DeepSeek | cn_official |  | https://api.deepseek.com/models | deepseek-v4-pro |  |  |
| OpenCode Go | third_party | openai_chat | https://opencode.ai/zen/go | deepseek-v4-flash | https://opencode.ai/zen/go |  |
| Zhipu GLM | cn_official |  | https://open.bigmodel.cn/api/anthropic | glm-5.1 |  |  |
| Zhipu GLM en | cn_official |  | https://api.z.ai/api/anthropic | glm-5.1 |  |  |
| Baidu Qianfan Coding Plan | cn_official |  | https://qianfan.baidubce.com/anthropic/coding | qianfan-code-latest | https://qianfan.baidubce.com/anthropic/coding |  |
| Bailian | cn_official |  | https://dashscope.aliyuncs.com/apps/anthropic |  |  |  |
| Bailian For Coding | cn_official |  | https://coding.dashscope.aliyuncs.com/apps/anthropic |  |  |  |
| Kimi | cn_official |  | https://api.moonshot.cn/anthropic | kimi-k2.7-code |  |  |
| Kimi For Coding | cn_official |  | https://api.kimi.com/coding/ |  |  |  |
| StepFun | cn_official |  | https://api.stepfun.com/step_plan | step-3.5-flash-2603 | https://api.stepfun.com/step_plan |  |
| StepFun en | cn_official |  | https://api.stepfun.ai/step_plan | step-3.5-flash-2603 | https://api.stepfun.ai/step_plan |  |
| ModelScope | aggregator |  | https://api-inference.modelscope.cn | ZhipuAI/GLM-5.1 |  |  |
| KAT-Coder | cn_official |  |  |  |  |  |
| Longcat | cn_official |  | https://api.longcat.chat/anthropic | LongCat-2.0 |  |  |
| MiniMax | cn_official |  | https://api.minimaxi.com/anthropic | MiniMax-M2.7 |  |  |
| MiniMax en | cn_official |  | https://api.minimax.io/anthropic | MiniMax-M2.7 |  |  |
| BaiLing | cn_official |  | https://api.tbox.cn/api/anthropic | Ling-2.5-1T |  |  |
| AiHubMix | aggregator |  | https://aihubmix.com |  | https://aihubmix.com<br>https://api.aihubmix.com |  |
| CherryIN | aggregator |  | https://open.cherryin.net | anthropic/claude-sonnet-5 | https://open.cherryin.net |  |
| SiliconFlow | aggregator |  | https://api.siliconflow.cn | Pro/MiniMaxAI/MiniMax-M2.7 |  |  |
| SiliconFlow en | aggregator |  | https://api.siliconflow.com | MiniMaxAI/MiniMax-M2.7 |  |  |
| DMXAPI | aggregator |  | https://www.dmxapi.cn |  | https://www.dmxapi.cn<br>https://api.dmxapi.cn |  |
| PackyCode | third_party |  | https://www.packyapi.com |  | https://www.packyapi.com<br>https://api-slb.packyapi.com |  |
| APIKEY.FUN | third_party |  | https://api.apikey.fun |  | https://api.apikey.fun<br>https://slb.apikey.fun |  |
| APINebula | third_party |  | https://apinebula.com |  | https://apinebula.com |  |
| AtlasCloud | aggregator |  | https://api.atlascloud.ai | zai-org/glm-5.1 | https://api.atlascloud.ai |  |
| SudoCode | third_party |  | https://sudocode.us |  | https://sudocode.us<br>https://sudocode.run |  |
| ClaudeAPI | aggregator |  | https://gw.claudeapi.com |  |  |  |
| Code0 | aggregator |  | https://code0.ai |  |  |  |
| NekoCode | aggregator |  | https://nekocode.ai |  |  |  |
| ClaudeCN | third_party |  | https://claudecn.top |  |  |  |
| RunAPI | aggregator |  | https://runapi.co |  |  |  |
| RelaxyCode | third_party |  | https://www.relaxycode.com |  |  |  |
| Cubence | third_party |  | https://api.cubence.com |  | https://api.cubence.com<br>https://api-cf.cubence.com<br>https://api-dmit.cubence.com<br>https://api-bwg.cubence.com |  |
| AIGoCode | third_party |  | https://api.aigocode.com |  | https://api.aigocode.com |  |
| RightCode | third_party |  | https://www.right.codes/claude |  |  |  |
| AICodeMirror | third_party |  | https://api.aicodemirror.com/api/claudecode |  | https://api.aicodemirror.com/api/claudecode<br>https://api.claudecode.net.cn/api/claudecode |  |
| CrazyRouter | third_party |  | https://cn.crazyrouter.com |  | https://cn.crazyrouter.com |  |
| SSSAiCode | third_party |  | https://node-hk.sssaicodeapi.com/api |  | https://node-hk.sssaicodeapi.com/api<br>https://node-hk.sssaiapi.com/api<br>https://node-cf.sssaicodeapi.com/api |  |
| Compshare | aggregator |  | https://api.modelverse.cn |  | https://api.modelverse.cn |  |
| Compshare Coding Plan | aggregator |  | https://cp.compshare.cn |  | https://cp.compshare.cn |  |
| Micu | third_party |  | https://www.micuapi.ai |  | https://www.micuapi.ai |  |
| ETok.ai | third_party |  | https://api.etok.ai |  |  |  |
| E-FlowCode | third_party |  | https://e-flowcode.cc |  | https://e-flowcode.cc |  |
| OpenRouter | aggregator |  | https://openrouter.ai/api | anthropic/claude-sonnet-5 |  |  |
| TheRouter | aggregator |  | https://api.therouter.ai | anthropic/claude-sonnet-5 | https://api.therouter.ai |  |
| Novita AI | aggregator |  | https://api.novita.ai/anthropic | zai-org/glm-5.1 | https://api.novita.ai/anthropic |  |
| GitHub Copilot | third_party | openai_chat | https://api.githubcopilot.com | claude-sonnet-5 |  |  |
| Codex | third_party | openai_responses | https://chatgpt.com/backend-api/codex | gpt-5.5 |  |  |
| Nvidia | aggregator | openai_chat | https://integrate.api.nvidia.com | moonshotai/kimi-k2.5 |  |  |
| PIPELLM | aggregator |  | https://cc-api.pipellm.ai | claude-opus-4-8 |  |  |
| Xiaomi MiMo | cn_official |  | https://api.xiaomimimo.com/anthropic | mimo-v2.5-pro |  |  |
| Xiaomi MiMo Token Plan (China) | cn_official |  | https://token-plan-cn.xiaomimimo.com/anthropic | mimo-v2.5-pro |  |  |
| AWS Bedrock (AKSK) | cloud_provider |  |  |  |  |  |
| AWS Bedrock (API Key) | cloud_provider |  |  |  |  |  |

</details>

### codexProviderPresets.ts（Codex Provider 预设，共 63 条）

<details>
<summary>点击展开 codexProviderPresets.ts 完整预设表</summary>

| 名称 | 分类 | apiFormat | Base URL | 默认模型 | endpointCandidates | templateValues |
|---|---|---|---|---|---|---|
| OpenAI Official | official |  |  |  |  |  |
| Shengsuanyun | aggregator |  |  |  | https://api.pateway.ai/v1 |  |
| PatewayAI | third_party |  |  |  | https://api.pateway.ai/v1 |  |
| 火山Agentplan | cn_official | openai_chat |  | ark-code-latest | https://ark.cn-beijing.volces.com/api/coding/v3 |  |
| BytePlus | cn_official | openai_chat |  | ark-code-latest | https://ark.ap-southeast.bytepluses.com/api/coding/v3 |  |
| DouBaoSeed | cn_official | openai_responses |  | doubao-seed-2-1-pro-260628 | https://ark.cn-beijing.volces.com/api/v3 |  |
| CCSub | aggregator |  |  |  | https://www.ccsub.net/v1 |  |
| SubRouter | aggregator |  |  |  | https://subrouter.ai/v1 |  |
| Unity2.ai | aggregator |  |  |  | https://api.unity2.ai |  |
| Qiniu | aggregator |  |  |  | https://api.qnaigc.com/bypass/openai/v1<br>https://api.modelink.ai/bypass/openai/v1 |  |
| FennoAI | aggregator |  |  |  | https://api.fenno.ai |  |
| ZetaAPI | aggregator |  |  |  | https://api.zetaapi.ai/v1 |  |
| TeamoRouter | aggregator |  |  |  | https://api.teamorouter.com/v1 |  |
| Amux | aggregator |  |  |  | https://api.amux.ai/v1 |  |
| Code0 | aggregator |  |  |  | https://code0.ai/v1 |  |
| NekoCode | aggregator |  |  |  | https://nekocode.ai/v1 |  |
| Azure OpenAI | third_party |  |  |  | https://YOUR_RESOURCE_NAME.openai.azure.com/openai |  |
| DeepSeek | cn_official | openai_chat |  | deepseek-v4-flash | https://api.deepseek.com |  |
| Zhipu GLM | cn_official | openai_chat |  | glm-5.2 | https://open.bigmodel.cn/api/coding/paas/v4 |  |
| Zhipu GLM en | cn_official | openai_chat |  | glm-5.2 | https://api.z.ai/api/coding/paas/v4 |  |
| Baidu Qianfan Coding Plan | cn_official | openai_chat |  | qianfan-code-latest | https://qianfan.baidubce.com/v2/coding |  |
| Bailian | cn_official | openai_responses |  | qwen3-coder-plus | https://dashscope.aliyuncs.com/compatible-mode/v1 |  |
| Kimi | cn_official | openai_chat |  | kimi-k2.7-code | https://api.moonshot.cn/v1 |  |
| Kimi For Coding | cn_official | openai_chat |  | kimi-for-coding | https://api.kimi.com/coding/v1 |  |
| StepFun | cn_official | openai_chat |  | step-3.7-flash | https://api.stepfun.com/step_plan/v1 |  |
| StepFun en | cn_official | openai_chat |  | step-3.7-flash | https://api.stepfun.ai/step_plan/v1 |  |
| ModelScope | aggregator | openai_chat |  | ZhipuAI/GLM-5.1 | https://api-inference.modelscope.cn/v1 |  |
| Longcat | cn_official | openai_responses |  | LongCat-2.0 | https://api.longcat.chat/openai/v1 |  |
| MiniMax | cn_official | openai_responses |  | MiniMax-M3 | https://api.minimaxi.com/v1 |  |
| MiniMax en | cn_official | openai_responses |  | MiniMax-M3 | https://api.minimax.io/v1 |  |
| BaiLing | cn_official | openai_chat |  | Ling-2.6-1T | https://api.tbox.cn/api/llm/v1 |  |
| Xiaomi MiMo | cn_official | openai_responses |  | mimo-v2.5-pro | https://api.xiaomimimo.com/v1 |  |
| Xiaomi MiMo Token Plan (China) | cn_official | openai_responses |  | mimo-v2.5-pro | https://token-plan-cn.xiaomimimo.com/v1 |  |
| SiliconFlow | aggregator | openai_chat |  | Pro/MiniMaxAI/MiniMax-M2.7 | https://api.siliconflow.cn/v1 |  |
| SiliconFlow en | aggregator | openai_chat |  | MiniMaxAI/MiniMax-M2.7 | https://api.siliconflow.com/v1 |  |
| Novita AI | aggregator | openai_chat |  | zai-org/glm-5.1 | https://api.novita.ai/openai/v1 |  |
| Nvidia | aggregator | openai_chat |  | moonshotai/kimi-k2.5 | https://integrate.api.nvidia.com/v1 |  |
| OpenCode Go | third_party | openai_chat |  | glm-5.2 | https://opencode.ai/zen/go/v1 |  |
| AiHubMix | aggregator |  |  |  | https://aihubmix.com/v1<br>https://api.aihubmix.com/v1 |  |
| CherryIN | aggregator |  |  |  | https://open.cherryin.net/v1 |  |
| DMXAPI | aggregator |  |  |  | https://www.dmxapi.cn/v1 |  |
| PackyCode | third_party |  |  |  | https://www.packyapi.com/v1<br>https://api-slb.packyapi.com/v1 |  |
| APIKEY.FUN | third_party | openai_responses |  |  | https://api.apikey.fun/v1<br>https://slb.apikey.fun/v1 |  |
| APINebula | third_party | openai_responses |  |  | https://apinebula.com/v1 |  |
| AtlasCloud | aggregator | openai_chat |  | zai-org/glm-5.1 | https://api.atlascloud.ai/v1 |  |
| SudoCode | third_party | openai_responses |  |  | https://sudocode.us/v1<br>https://sudocode.run/v1 |  |
| ClaudeCN | third_party |  |  |  |  |  |
| RunAPI | aggregator |  |  |  |  |  |
| RelaxyCode | third_party |  |  |  |  |  |
| Cubence | third_party |  |  |  | https://api.cubence.com/v1<br>https://api-cf.cubence.com/v1<br>https://api-dmit.cubence.com/v1<br>https://api-bwg.cubence.com/v1 |  |
| AIGoCode | third_party |  |  |  | https://api.aigocode.com |  |
| RightCode | third_party |  |  |  |  |  |
| AICodeMirror |  |  |  |  | https://api.aicodemirror.com/api/codex/backend-api/codex<br>https://api.claudecode.net.cn/api/codex/backend-api/codex |  |
| CrazyRouter |  |  |  |  | https://cn.crazyrouter.com/v1 |  |
| SSSAiCode | third_party |  |  |  | https://node-hk.sssaicodeapi.com/api/v1<br>https://node-hk.sssaiapi.com/api/v1<br>https://node-cf.sssaicodeapi.com/api/v1 |  |
| Compshare | aggregator |  |  |  | https://api.modelverse.cn/v1 |  |
| Compshare Coding Plan | aggregator |  |  |  | https://cp.compshare.cn/v1 |  |
| Micu | third_party |  |  |  | https://www.micuapi.ai/v1 |  |
| ETok.ai | third_party |  |  |  | https://api.etok.ai/v1 |  |
| E-FlowCode | third_party |  |  |  | https://e-flowcode.cc/v1 |  |
| OpenRouter | aggregator |  |  |  |  |  |
| TheRouter | aggregator |  |  |  | https://api.therouter.ai/v1 |  |

</details>

### geminiProviderPresets.ts（Gemini CLI Provider 预设，共 21 条）

<details>
<summary>点击展开 geminiProviderPresets.ts 完整预设表</summary>

| 名称 | 分类 | apiFormat | Base URL | 默认模型 | endpointCandidates | templateValues |
|---|---|---|---|---|---|---|
| Google Official | official |  |  |  |  |  |
| Shengsuanyun | aggregator |  | https://router.shengsuanyun.com/api | google/gemini-3.5-flash |  |  |
| Unity2.ai | aggregator |  | https://api.unity2.ai | gemini-3.1-pro |  |  |
| SubRouter | aggregator |  | https://subrouter.ai/v1beta | gemini-3.5-flash | https://subrouter.ai/v1beta |  |
| Qiniu | aggregator |  | https://api.qnaigc.com/bypass/vertex | gemini-3.1-pro-preview | https://api.qnaigc.com/bypass/vertex<br>https://api.modelink.ai/bypass/vertex |  |
| Code0 | aggregator |  | https://code0.ai | gemini-3.1-pro-preview |  |  |
| PackyCode | third_party |  | https://www.packyapi.com | gemini-3.5-flash | https://api-slb.packyapi.com<br>https://www.packyapi.com |  |
| APIKEY.FUN | third_party |  | https://api.apikey.fun | gemini-3.5-flash | https://api.apikey.fun<br>https://slb.apikey.fun |  |
| APINebula | third_party |  | https://apinebula.com | gemini-3.5-flash | https://apinebula.com |  |
| SudoCode | third_party |  | https://sudocode.us | gemini-3.1-flash-lite | https://sudocode.us<br>https://sudocode.run |  |
| Cubence | third_party |  | https://api.cubence.com | gemini-3.5-flash | https://api.cubence.com/v1<br>https://api-cf.cubence.com/v1<br>https://api-dmit.cubence.com/v1<br>https://api-bwg.cubence.com/v1 |  |
| AIGoCode | third_party |  | https://api.aigocode.com | gemini-3.5-flash | https://api.aigocode.com |  |
| AICodeMirror | third_party |  | https://api.aicodemirror.com/api/gemini | gemini-3.5-flash | https://api.aicodemirror.com/api/gemini<br>https://api.claudecode.net.cn/api/gemini |  |
| CrazyRouter | third_party |  | https://cn.crazyrouter.com | gemini-3.5-flash | https://cn.crazyrouter.com |  |
| SSSAiCode | third_party |  | https://node-hk.sssaicodeapi.com/api | gemini-3.5-flash | https://node-hk.sssaicodeapi.com/api<br>https://node-hk.sssaiapi.com/api<br>https://node-cf.sssaicodeapi.com/api |  |
| ETok.ai | third_party |  | https://api.etok.ai/v1beta | gemini-3.5-flash | https://api.etok.ai/v1beta |  |
| E-FlowCode | third_party |  | https://api.etok.ai/v1beta | gemini-3.5-flash | https://api.etok.ai/v1beta |  |
| CherryIN | aggregator |  | https://open.cherryin.net | google/gemini-3.5-flash | https://open.cherryin.net |  |
| OpenRouter | aggregator |  | https://openrouter.ai/api | gemini-3.5-flash |  |  |
| TheRouter | aggregator |  | https://api.therouter.ai | gemini-3.5-flash | https://api.therouter.ai |  |
| 自定义 | custom |  |  | gemini-3.5-flash |  |  |

</details>

### openclawProviderPresets.ts（OpenClaw Provider 预设，共 59 条）

<details>
<summary>点击展开 openclawProviderPresets.ts 完整预设表</summary>

| 名称 | 分类 | apiFormat | Base URL | 默认模型 | endpointCandidates | templateValues |
|---|---|---|---|---|---|---|
| Shengsuanyun | aggregator |  |  |  |  |  |
| 火山Agentplan | cn_official |  |  |  |  |  |
| BytePlus | cn_official |  |  |  |  |  |
| DouBaoSeed | cn_official |  |  |  |  |  |
| CCSub | aggregator |  |  |  |  |  |
| SubRouter | aggregator |  |  |  |  |  |
| Qiniu | aggregator |  |  |  |  |  |
| FennoAI | aggregator |  |  |  |  |  |
| ZetaAPI | aggregator |  |  |  |  |  |
| TeamoRouter | aggregator |  |  |  |  |  |
| Amux | aggregator |  |  |  |  |  |
| Code0 | aggregator |  |  |  |  |  |
| NekoCode | aggregator |  |  |  |  |  |
| Unity2.ai | aggregator |  |  |  |  |  |
| DeepSeek | cn_official |  |  |  |  |  |
| Zhipu GLM | cn_official |  |  |  |  |  |
| Zhipu GLM en | cn_official |  |  |  |  |  |
| Qwen Coder | cn_official |  |  |  |  |  |
| Kimi | cn_official |  |  |  |  |  |
| Kimi For Coding | cn_official |  |  |  |  |  |
| StepFun | cn_official |  |  |  |  |  |
| StepFun en | cn_official |  |  |  |  |  |
| MiniMax | cn_official |  |  |  |  |  |
| MiniMax en | cn_official |  |  |  |  |  |
| KAT-Coder | cn_official |  |  |  |  |  |
| Longcat | cn_official |  |  |  |  |  |
| BaiLing | cn_official |  |  |  |  |  |
| Xiaomi MiMo | cn_official |  |  |  |  |  |
| Xiaomi MiMo Token Plan (China) | cn_official |  |  |  |  |  |
| AiHubMix | aggregator |  |  |  |  |  |
| CherryIN | aggregator |  |  |  |  |  |
| SiliconFlow | aggregator |  |  |  |  |  |
| SiliconFlow en | aggregator |  |  |  |  |  |
| DMXAPI | aggregator |  |  |  |  |  |
| PackyCode | third_party |  |  |  |  |  |
| APIKEY.FUN | third_party |  |  |  |  |  |
| APINebula | third_party |  |  |  |  |  |
| AtlasCloud | aggregator |  |  |  |  |  |
| SudoCode | third_party |  |  |  |  |  |
| Cubence | third_party |  |  |  |  |  |
| AIGoCode | third_party |  |  |  |  |  |
| RightCode | third_party |  |  |  |  |  |
| AICodeMirror | third_party |  |  |  |  |  |
| CrazyRouter | third_party |  |  |  |  |  |
| SSSAiCode | third_party |  |  |  |  |  |
| Compshare | aggregator |  |  |  |  |  |
| Compshare Coding Plan | aggregator |  |  |  |  |  |
| Micu | third_party |  |  |  |  |  |
| ETok.ai | third_party |  |  |  |  |  |
| E-FlowCode | third_party |  |  |  |  |  |
| OpenRouter | aggregator |  |  |  |  |  |
| TheRouter | aggregator |  |  |  |  |  |
| ModelScope | aggregator |  |  |  |  |  |
| SiliconFlow | aggregator |  |  |  |  |  |
| SiliconFlow en | aggregator |  |  |  |  |  |
| Novita AI | aggregator |  |  |  |  |  |
| Nvidia | aggregator |  |  |  |  |  |
| PIPELLM | aggregator |  |  |  |  |  |
| AWS Bedrock | cloud_provider |  |  |  |  |  |

</details>

### opencodeProviderPresets.ts（OpenCode Provider 预设，共 59 条）

<details>
<summary>点击展开 opencodeProviderPresets.ts 完整预设表</summary>

| 名称 | 分类 | apiFormat | Base URL | 默认模型 | endpointCandidates | templateValues |
|---|---|---|---|---|---|---|
| Shengsuanyun | aggregator |  | https://router.shengsuanyun.com/api/v1 |  |  |  |
| Qiniu | aggregator |  | https://api.qnaigc.com/v1 |  |  |  |
| FennoAI | aggregator |  | https://api.fenno.ai/v1 |  |  |  |
| ZetaAPI | aggregator |  | https://api.zetaapi.ai/v1 |  |  |  |
| TeamoRouter | aggregator |  | https://api.teamorouter.com/v1 |  |  |  |
| Amux | aggregator |  | https://api.amux.ai/v1 |  |  |  |
| Code0 | aggregator |  | https://code0.ai/v1 |  |  |  |
| NekoCode | aggregator |  | https://nekocode.ai/v1 |  |  |  |
| 火山Agentplan | cn_official |  | https://ark.cn-beijing.volces.com/api/coding/v3 |  |  |  |
| BytePlus | cn_official |  | https://ark.ap-southeast.bytepluses.com/api/coding/v3 |  |  |  |
| DouBaoSeed | cn_official |  | https://ark.cn-beijing.volces.com/api/v3 |  |  |  |
| CCSub | aggregator |  | https://www.ccsub.net/v1 |  |  |  |
| SubRouter | aggregator |  | https://subrouter.ai/v1 |  |  |  |
| Unity2.ai | aggregator |  | https://api.unity2.ai/v1 |  |  |  |
| DeepSeek | cn_official |  | https://api.deepseek.com/v1 |  |  |  |
| Zhipu GLM | cn_official |  | https://open.bigmodel.cn/api/coding/paas/v4 |  |  |  |
| Zhipu GLM en | cn_official |  | https://api.z.ai/api/coding/paas/v4 |  |  |  |
| Bailian | cn_official |  | https://dashscope.aliyuncs.com/compatible-mode/v1 |  |  |  |
| Kimi | cn_official |  | https://api.moonshot.cn/v1 |  |  |  |
| Kimi For Coding | cn_official |  | https://api.kimi.com/coding/v1 |  |  |  |
| StepFun | cn_official |  | https://api.stepfun.com/step_plan/v1 |  |  |  |
| StepFun en | cn_official |  | https://api.stepfun.ai/step_plan/v1 |  |  |  |
| StepFun Step Plan | cn_official |  | https://api.stepfun.com/step_plan/v1 |  |  |  |
| ModelScope | aggregator |  | https://api-inference.modelscope.cn/v1 |  |  |  |
| KAT-Coder | cn_official |  | https://vanchin.streamlake.ai/api/gateway/v1/endpoints/${ENDPOINT_ID}/openai |  |  |  |
| Longcat | cn_official |  | https://api.longcat.chat/openai/v1 |  |  |  |
| MiniMax | cn_official |  | https://api.minimaxi.com/v1 |  |  |  |
| MiniMax en | cn_official |  | https://api.minimax.io/v1 |  |  |  |
| BaiLing | cn_official |  | https://api.tbox.cn/v1 |  |  |  |
| Xiaomi MiMo | cn_official |  | https://api.xiaomimimimo.com/v1 |  |  |  |
| Xiaomi MiMo Token Plan (China) | cn_official |  | https://token-plan-cn.xiaomimimo.com/v1 |  |  |  |
| OpenCode Go | third_party |  | https://opencode.ai/zen/go/v1 |  |  |  |
| AiHubMix | aggregator |  | https://aihubmix.com/v1 |  |  |  |
| CherryIN | aggregator |  | https://open.cherryin.net/v1 |  |  |  |
| DMXAPI | aggregator |  | https://www.dmxapi.cn/v1 |  |  |  |
| OpenRouter | aggregator |  | https://openrouter.ai/api/v1 |  |  |  |
| TheRouter | aggregator |  | https://api.therouter.ai/v1 |  |  |  |
| Novita AI | aggregator |  | https://api.novita.ai/openai |  |  |  |
| Nvidia | aggregator |  | https://integrate.api.nvidia.com/v1 |  |  |  |
| PIPELLM | aggregator |  | https://cc-api.pipellm.ai |  |  |  |
| PackyCode | third_party |  | https://www.packyapi.com/v1 |  |  |  |
| APIKEY.FUN | third_party |  | https://api.apikey.fun/v1 |  |  |  |
| APINebula | third_party |  | https://apinebula.com/v1 |  |  |  |
| AtlasCloud | aggregator |  | https://api.atlascloud.ai/v1 |  |  |  |
| SudoCode | third_party |  | https://sudocode.us/v1 |  |  |  |
| Cubence | third_party |  | https://api.cubence.com/v1 |  |  |  |
| AIGoCode | third_party |  | https://api.aigocode.com |  |  |  |
| RightCode | third_party |  | https://right.codes/codex/v1 |  |  |  |
| AICodeMirror | third_party |  | https://api.aicodemirror.com/api/claudecode |  |  |  |
| ClaudeCN | third_party |  | https://claudecn.top |  |  |  |
| RunAPI | aggregator |  | https://runapi.co |  |  |  |
| CrazyRouter | third_party |  | https://cn.crazyrouter.com |  |  |  |
| SSSAiCode | third_party |  | https://node-hk.sssaicodeapi.com/api/v1 |  |  |  |
| Micu | third_party |  | https://www.micuapi.ai/v1 |  |  |  |
| ETok.ai | third_party |  | https://api.etok.ai/v1 |  |  |  |
| E-FlowCode | third_party |  | https://e-flowcode.cc/v1 |  |  |  |
| AWS Bedrock | cloud_provider |  |  |  |  |  |
| Oh My OpenCode | omo |  |  |  |  |  |
| Oh My OpenCode Slim | omo-slim |  |  |  |  |  |

</details>

### hermesProviderPresets.ts（Hermes Provider 预设，共 60 条）

<details>
<summary>点击展开 hermesProviderPresets.ts 完整预设表</summary>

| 名称 | 分类 | apiFormat | Base URL | 默认模型 | endpointCandidates | templateValues |
|---|---|---|---|---|---|---|
| Shengsuanyun | aggregator |  |  |  |  |  |
| Qiniu | aggregator |  |  |  |  |  |
| FennoAI | aggregator |  |  |  |  |  |
| ZetaAPI | aggregator |  |  |  |  |  |
| TeamoRouter | aggregator |  |  |  |  |  |
| Amux | aggregator |  |  |  |  |  |
| Code0 | aggregator |  |  |  |  |  |
| NekoCode | aggregator |  |  |  |  |  |
| 火山Agentplan | cn_official |  |  |  |  |  |
| BytePlus | cn_official |  |  |  |  |  |
| DouBaoSeed | cn_official |  |  |  |  |  |
| CCSub | aggregator |  |  |  |  |  |
| SubRouter | aggregator |  |  |  |  |  |
| Unity2.ai | aggregator |  |  |  |  |  |
| OpenRouter | aggregator |  |  |  |  |  |
| DeepSeek | cn_official |  |  |  |  |  |
| Together AI | aggregator |  |  |  |  |  |
| Nous Research | official |  |  |  |  |  |
| Zhipu GLM | cn_official |  |  |  |  |  |
| Zhipu GLM en | cn_official |  |  |  |  |  |
| Bailian | cn_official |  |  |  |  |  |
| Bailian For Coding | cn_official |  |  |  |  |  |
| Kimi | cn_official |  |  |  |  |  |
| Kimi For Coding | cn_official |  |  |  |  |  |
| StepFun | cn_official |  |  |  |  |  |
| ModelScope | aggregator |  |  |  |  |  |
| KAT-Coder | cn_official |  |  |  |  |  |
| Longcat | cn_official |  |  |  |  |  |
| MiniMax | cn_official |  |  |  |  |  |
| MiniMax en | cn_official |  |  |  |  |  |
| BaiLing | cn_official |  |  |  |  |  |
| AiHubMix | aggregator |  |  |  |  |  |
| CherryIN | aggregator |  |  |  |  |  |
| SiliconFlow | aggregator |  |  |  |  |  |
| SiliconFlow en | aggregator |  |  |  |  |  |
| DMXAPI | aggregator |  |  |  |  |  |
| PackyCode | third_party |  |  |  |  |  |
| APIKEY.FUN | third_party |  |  |  |  |  |
| APINebula | third_party |  |  |  |  |  |
| AtlasCloud | aggregator |  |  |  |  |  |
| SudoCode | third_party |  |  |  |  |  |
| Cubence | third_party |  |  |  |  |  |
| ClaudeCN | third_party |  |  |  |  |  |
| RunAPI | aggregator |  |  |  |  |  |
| AIGoCode | third_party |  |  |  |  |  |
| RightCode | third_party |  |  |  |  |  |
| AICodeMirror | third_party |  |  |  |  |  |
| CrazyRouter | third_party |  |  |  |  |  |
| SSSAiCode | third_party |  |  |  |  |  |
| Compshare | aggregator |  |  |  |  |  |
| Compshare Coding Plan | aggregator |  |  |  |  |  |
| Micu | third_party |  |  |  |  |  |
| ETok.ai | third_party |  |  |  |  |  |
| E-FlowCode | third_party |  |  |  |  |  |
| TheRouter | aggregator |  |  |  |  |  |
| Novita AI | aggregator |  |  |  |  |  |
| Nvidia | aggregator |  |  |  |  |  |
| PIPELLM | aggregator |  |  |  |  |  |
| Xiaomi MiMo | cn_official |  |  |  |  |  |
| Xiaomi MiMo Token Plan (China) | cn_official |  |  |  |  |  |

</details>

### claudeDesktopProviderPresets.ts（Claude Desktop Provider 预设，共 67 条）

<details>
<summary>点击展开 claudeDesktopProviderPresets.ts 完整预设表</summary>

| 名称 | 分类 | apiFormat | Base URL | 默认模型 | endpointCandidates | templateValues |
|---|---|---|---|---|---|---|
| Claude Desktop Official | official | anthropic |  |  |  |  |
| Shengsuanyun | aggregator | anthropic |  |  |  |  |
| PatewayAI | third_party | anthropic |  |  |  |  |
| Qiniu | aggregator | anthropic |  |  | https://api.qnaigc.com<br>https://api.modelink.ai |  |
| FennoAI | aggregator | anthropic |  |  |  |  |
| ZetaAPI | aggregator | anthropic |  |  |  |  |
| TeamoRouter | aggregator | anthropic |  |  |  |  |
| Amux | aggregator | anthropic |  |  |  |  |
| 火山Agentplan | cn_official | anthropic |  |  |  |  |
| BytePlus | cn_official | anthropic |  |  |  |  |
| DouBaoSeed | cn_official | anthropic |  |  |  |  |
| CCSub | aggregator | anthropic |  |  |  |  |
| SubRouter | aggregator | anthropic |  |  |  |  |
| Unity2.ai | aggregator | anthropic |  |  |  |  |
| Gemini Native | third_party | gemini_native |  |  | https://generativelanguage.googleapis.com |  |
| GitHub Copilot | third_party | openai_chat |  |  |  |  |
| Codex | third_party | openai_responses |  |  |  |  |
| DeepSeek | cn_official | anthropic |  |  |  |  |
| OpenCode Go | third_party | openai_chat |  |  | https://opencode.ai/zen/go |  |
| Zhipu GLM | cn_official | anthropic |  |  |  |  |
| Zhipu GLM en | cn_official | anthropic |  |  |  |  |
| Baidu Qianfan Coding Plan | cn_official | anthropic |  |  | https://qianfan.baidubce.com/anthropic/coding |  |
| Bailian | cn_official | anthropic |  |  |  |  |
| Bailian For Coding | cn_official | anthropic |  |  |  |  |
| Kimi | cn_official | anthropic |  |  |  |  |
| Kimi For Coding | cn_official | anthropic |  |  |  |  |
| StepFun | cn_official | anthropic |  |  | https://api.stepfun.com/step_plan |  |
| StepFun en | cn_official | anthropic |  |  | https://api.stepfun.ai/step_plan |  |
| ModelScope | aggregator | anthropic |  |  |  |  |
| Longcat | cn_official | anthropic |  |  |  |  |
| MiniMax | cn_official | anthropic |  |  |  |  |
| MiniMax en | cn_official | anthropic |  |  |  |  |
| BaiLing | cn_official | anthropic |  |  |  |  |
| AiHubMix | aggregator | anthropic |  |  | https://aihubmix.com<br>https://api.aihubmix.com |  |
| CherryIN | aggregator | anthropic |  |  | https://open.cherryin.net |  |
| SiliconFlow | aggregator | anthropic |  |  |  |  |
| SiliconFlow en | aggregator | anthropic |  |  |  |  |
| DMXAPI | aggregator | anthropic |  |  | https://www.dmxapi.cn<br>https://api.dmxapi.cn |  |
| PackyCode | third_party | anthropic |  |  | https://www.packyapi.com<br>https://api-slb.packyapi.com |  |
| APIKEY.FUN | third_party | anthropic |  |  | https://api.apikey.fun<br>https://slb.apikey.fun |  |
| APINebula | third_party | anthropic |  |  | https://apinebula.com |  |
| AtlasCloud | aggregator | anthropic |  |  | https://api.atlascloud.ai |  |
| SudoCode | third_party | anthropic |  |  | https://sudocode.us<br>https://sudocode.run |  |
| ClaudeAPI | aggregator | anthropic |  |  |  |  |
| Code0 | aggregator | anthropic |  |  |  |  |
| NekoCode | aggregator | anthropic |  |  |  |  |
| ClaudeCN | third_party | anthropic |  |  |  |  |
| RunAPI | aggregator | anthropic |  |  |  |  |
| RelaxyCode | third_party | anthropic |  |  |  |  |
| Cubence | third_party | anthropic |  |  | https://api.cubence.com<br>https://api-cf.cubence.com<br>https://api-cf.cubence.com<br>https://api-bwg.cubence.com |  |
| AIGoCode | third_party | anthropic |  |  | https://api.aigocode.com |  |
| RightCode | third_party | anthropic |  |  |  |  |
| AICodeMirror | third_party | anthropic |  |  | https://api.aicodemirror.com/api/claudecode<br>https://api.claudecode.net.cn/api/claudecode |  |
| CrazyRouter | third_party | anthropic |  |  | https://cn.crazyrouter.com |  |
| SSSAiCode | third_party | anthropic |  |  | https://node-hk.sssaicodeapi.com/api<br>https://node-hk.sssaiapi.com/api<br>https://node-cf.sssaicodeapi.com/api |  |
| Compshare | aggregator | anthropic |  |  | https://api.modelverse.cn |  |
| Compshare Coding Plan | aggregator | anthropic |  |  | https://cp.compshare.cn |  |
| Micu | third_party | anthropic |  |  | https://www.micuapi.ai |  |
| ETok.ai | third_party | anthropic |  |  |  |  |
| E-FlowCode | third_party | anthropic |  |  | https://e-flowcode.cc |  |
| OpenRouter | aggregator | anthropic |  |  |  |  |
| TheRouter | aggregator | anthropic |  |  | https://api.therouter.ai |  |
| Novita AI | aggregator | anthropic |  |  | https://api.novita.ai/anthropic |  |
| Nvidia | aggregator | openai_chat |  |  |  |  |
| PIPELLM | aggregator | anthropic |  |  |  |  |
| Xiaomi MiMo | cn_official | anthropic |  |  |  |  |
| Xiaomi MiMo Token Plan (China) | cn_official | anthropic |  |  |  |  |

</details>

### mcpPresets.ts（MCP Server 预设，共 5 条）

<details>
<summary>点击展开 mcpPresets.ts 完整预设表</summary>

| 名称 | 分类 | apiFormat | Base URL | 默认模型 | endpointCandidates | templateValues |
|---|---|---|---|---|---|---|
| mcp-server-fetch |  |  |  |  |  |  |
| @modelcontextprotocol/server-time |  |  |  |  |  |  |
| @modelcontextprotocol/server-memory |  |  |  |  |  |  |
| @modelcontextprotocol/server-sequential-thinking |  |  |  |  |  |  |
| @upstash/context7-mcp |  |  |  |  |  |  |

</details>


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

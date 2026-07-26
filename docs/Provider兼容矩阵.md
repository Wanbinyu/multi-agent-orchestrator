# Provider 兼容矩阵与安全边界

**状态**：现行（O3）  
**更新日期**：2026-07-25  
**基线**：`v0.1.0-beta.7`  
**真值源**：`src/models/catalog.py`（`BUILTIN_MODELS` / `PROVIDER_TEMPLATES` / `export_compatibility_matrix()`）  
**路由实现**：`src/gateway/router.py`（`ModelRouter`）  
**错误码实现**：`src/gateway/errors.py`（`ProviderErrorCode`）

本文说明 MAO 对各 Provider/模型预设的能力状态、价格来源、上下文窗口、已知限制，以及权限规则与 OS 沙箱的区别。  
**未在真实 smoke 中核实的字段不得用于自动升级或成本节省声明。**

## 1. 能力与元数据语义

| 字段 | 取值 | 路由与展示含义 |
|---|---|---|
| `capability_status` | `supported` | 已核实，可参与自动升级与能力声明 |
| `capability_status` | `unverified` | 默认保守；**不能**触发自动升级，**不能**宣称具备该能力 |
| `capability_status` | `unsupported` | 明确不支持，不得作为候选能力 |
| `metadata_source` | 官方文档 URL 等 | 来源不含 `unverified`/`unknown` 时视为可追溯 |
| `metadata_source` | `unverified` | 价格、能力声明均按占位处理 |
| `context_window_tokens` | `0` 或未验证 | MAO 使用 **200K** 本地默认安全预算，不代表上游物理上限 |
| `dynamic_model_alias` | `true` | 上游可能切换真实模型版本，窗口与能力可能漂移 |

能力名（目录内常见）：`tool_use`、`coding`、`reasoning`、`chat`、`vision`。

### 路由合同（与测试绑定）

- 自动路由（`/routing auto`）**只**把 `capability_status == supported` 的能力当作已验证。
- 列表型 `capabilities` 且 `metadata_source` 含 `unverified` 时，能力视为 `unverified`，**不能**触发升级（见 `tests/test_explainable_model_routing.py`）。
- 价格未知或来源未验证时：`savings_claim_allowed` 为 false，不得声称“更省钱”。
- 用户 `fixed` 模式固定主模型，即使其他候选有更高已验证分数。
- 未验证能力默认保守：失败回退、健康冷却与上下文预算仍优先于能力猜测。

## 2. Provider 预设模板

| 模板 key | 显示名 | 协议类型 | 默认 Base URL（示例） | 目录模型别名 |
|---|---|---|---|---|
| `volcengine_ark` | 火山方舟 | anthropic | `https://ark.cn-beijing.volces.com/api/coding` | `glm-ark`, `glm-chat` |
| `openai` | OpenAI | openai | `https://api.openai.com/v1` | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` |
| `anthropic` | Anthropic | anthropic | `https://api.anthropic.com` | `claude-fable-5`, `claude-opus-5`, `claude-sonnet-5`, `claude-haiku-4-5` |
| `kimi` | Kimi 转发 | openai | `https://api.moonshot.cn/v1` | `kimi-k3`（上游 `k3`）、`kimi-k2.7-code`（上游 `k3-256k`）、`kimi-k2.7`、`kimi-k2.5`、`kimi-for-coding` |
| `kimi_coding` | Kimi Coding Plan | openai | `https://api.kimi.com/coding/v1` | `k3`, `k3-256k`, `kimi-for-coding`, `kimi-for-coding-highspeed` |
| `deepseek` | DeepSeek | openai | `https://api.deepseek.com/v1` | `deepseek-v4-pro`, `deepseek-v4-flash` |
| `zhipu_glm` | 智谱 GLM | openai | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.2`, `glm-5` |
| `qwen` | 阿里通义千问 | openai | DashScope compatible-mode | `qwen3.8-max-preview`, `qwen3.7-max`, `qwen3.7-plus`, `qwen3.7-flash` |
| `minimax` | MiniMax | openai | `https://api.minimaxi.com/v1` | `minimax-m3` |
| `ark_openai` | 火山方舟 (OpenAI 兼容) | openai | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed` |
| `gemini` | Google Gemini (OpenAI 兼容) | openai | Generative Language OpenAI 兼容 | `gemini-3.6-flash`, `gemini-3.5-flash-lite` |
| `custom_openai` | 自定义 OpenAI 兼容 | openai | 用户填写 | （无内置模型） |

### 2.1 聚合与部署型预设

以下预设不能仅凭一个公共模型名判断可用性，MAO 只提供连接模板和示例，不把它们标记为离线验证通过：

| 预设 | 关键配置 | 使用前必须确认 |
|---|---|---|
| `openrouter` | `anthropic/claude-opus-5`, `openai/gpt-5.6-terra` | OpenRouter 当前模型目录、账号权限和实际价格 |
| `azure-openai` | `YOUR_RESOURCE_NAME`, `YOUR_DEPLOYMENT_NAME` | Azure resource、deployment name、API version 与该部署的能力 |
| `baidu-qianfan` | `qianfan-code-latest` 示例 | 千帆账号、区域和控制台实际 model_id |
| `siliconflow` | 平台格式的 Qwen/GLM 示例 | SiliconFlow 当前模型目录和账号权限 |
| `stepfun` | `step-3.7-flash` 示例 | StepFun 控制台当前可用 model_id |
| `ark_openai` / `ark` | `doubao-seed-2-1-pro-260628` 示例 | 火山方舟 endpoint 或账号实际允许的模型标识 |

这些条目的失败应归类为 `model_not_found`、`permission_error` 或 `invalid_request_error`，不应据此推断上游官方模型目录错误。

本地接入（`ollama` / `llamacpp`）见 [`本地LLM接入与扩展点.md`](本地LLM接入与扩展点.md)；不在内置 `PROVIDER_TEMPLATES` 主表，但 `providers.yaml.example` 提供配置样例。本地模型零边际成本只作路由评分因素，**不能**绕过健康冷却、已验证能力与上下文容量。

## 3. 模型目录矩阵（与 catalog 绑定）

下列行由 `export_compatibility_matrix()` 概念导出。更新目录后请同步本文，并运行 `tests/test_provider_matrix.py`。

### 3.1 元数据已部分核实（Anthropic 官方文档，2026-07-16）

| 别名 | 上游 model_id | 已验证能力 | 未验证能力 | 上下文 tokens | 价格 |
|---|---|---|---|---|---|
| `claude-fable-5` | `claude-fable-5` | coding, reasoning | tool_use, vision | 1_000_000 | 目录价；来源已标注 |
| `claude-opus-5` | `claude-opus-5` | coding, reasoning | tool_use, vision | 1_000_000 | 同上 |
| `claude-sonnet-5` | `claude-sonnet-5` | coding, reasoning | tool_use, vision | 1_000_000 | 同上 |
| `claude-haiku-4-5` | `claude-haiku-4-5-20251001` | chat, reasoning | tool_use, vision | 200_000 | 同上 |

说明：`tool_use` / `vision` 保持 `unverified`，直至真实端到端 smoke 与结构化图片消息验收。离线原生 tool 回合测试不构成 `supported`。Anthropic 元数据本次按官方文档更新于 2026-07-26。

### 3.2 元数据未核实（默认保守，价格为占位）

| 别名 | 协议类型 | 声明能力（均为 unverified） | 上下文 | 已知限制摘要 |
|---|---|---|---|---|
| `glm-ark` | anthropic | tool_use, coding, reasoning | 动态别名 → 200K 默认 | `ark-code-latest` 动态别名 |
| `glm-chat` | anthropic | tool_use, chat | 动态别名 → 200K 默认 | `ark-chat-latest` 动态别名 |
| `kimi-for-coding` | openai | tool_use, coding | 0 → 200K 默认 | 占位价 |
| `k3` | openai | coding, reasoning, tool_use, vision | 1_048_576 → 200K 默认 | 上游 Model ID 为 `k3`；元数据未逐项核实 |
| `k3-256k` | openai | coding, reasoning, tool_use | 262_144 → 200K 默认 | 上游 Model ID 为 `k3-256k`；元数据未逐项核实 |
| `kimi-for-coding-highspeed` | openai | coding, tool_use | 0 → 200K 默认 | 上游 Model ID 与别名相同；占位价 |
| `deepseek-chat` | openai | tool_use, chat, reasoning | 0 → 200K 默认 | 占位价 |
| `deepseek-reasoner` | openai | reasoning | 0 → 200K 默认 | 占位价 |
| `claude-opus-4-8` | anthropic | legacy alias | 0 → 200K 默认 | 兼容别名，实际发送 `claude-opus-5`；不再作为默认预设 |
| `gpt-4o` / `gpt-4o-mini` / `gpt-5` | openai | legacy 兼容条目 | 0 → 200K 默认 | 不再作为默认预设 |
| `gpt-5.6-sol` / `gpt-5.6-terra` / `gpt-5.6-luna` | openai | 见目录 | 1_050_000 → 200K 默认 | 官方目录来源；价格仍为占位 |
| `deepseek-v4-pro` / `deepseek-v4-flash` | openai | 见目录 | 0 → 200K 默认 | 占位价 |
| `kimi-k3` | openai | coding, reasoning, tool_use, vision | 1_048_576（来源 press，未逐项核实） | 展示别名；上游 Model ID 为 `k3` |
| `kimi-k2.7-code` | openai | coding, tool_use, reasoning | 0 → 200K 默认 | 展示别名；上游 Model ID 为 `k3-256k` |
| `kimi-k2.7` / `kimi-k2.5` | openai | 见目录 | 0 → 200K 默认 | 普通 Moonshot 兼容配置；Coding Plan 请使用专用预设 |
| `glm-5` / `glm-4-flash` | openai | 见目录 | 0 → 200K 默认 | GLM-4 Flash 不再作为默认预设 |
| `glm-5.2` | openai | 见目录 | 1_000_000 → 200K 默认 | 官方目录来源；价格仍为占位 |
| `minimax-m2.7` | openai | legacy 兼容条目 | 0 → 200K 默认 | 不再作为默认预设 |
| `minimax-m3` | openai | 见目录 | 1_000_000 → 200K 默认 | 官方目录来源；价格仍为占位 |
| `qwen3-coder-plus` / `qwen3-235b-a22b` | openai | legacy 兼容条目 | 0 → 200K 默认 | 不再作为默认预设 |
| `qwen3.8-max-preview` / `qwen3.7-max` / `qwen3.7-plus` / `qwen3.7-flash` | openai | 见目录 | 1_000_000 → 200K 默认 | 官方目录来源；价格仍为占位 |
| `doubao-seed` | openai | coding, reasoning | 0 → 200K 默认 | 占位价 |
| `gemini-3.1-pro` / `gemini-3.5-flash` / `gemini-3-flash` | openai | legacy 兼容条目 | 0 → 200K 默认 | 不再作为默认预设 |
| `gemini-3.6-flash` / `gemini-3.5-flash-lite` | openai | 见目录 | 1_000_000 → 200K 默认 | 官方目录来源；OpenAI 兼容端点差异 |

完整字段以 `python -c "from src.models.catalog import export_compatibility_matrix; import json; print(json.dumps(export_compatibility_matrix(), indent=2, ensure_ascii=False))"` 为准。

## 4. 稳定错误码

`ProviderError` 使用脱敏错误码与操作建议。认证/配置类错误**不**进入自动故障切换；短期限流可重试，长期配额走 failover。

| 错误码 | 含义 | 默认可重试 | 默认可 failover |
|---|---|---|---|
| `configuration_error` | Provider 或模型配置不完整 | 否 | 否 |
| `authentication_error` | 认证失败 | 否 | 否 |
| `permission_error` | 凭据无权访问模型/资源 | 否 | 否 |
| `model_not_found` | 模型不存在或端点不支持 | 否 | 是 |
| `quota_exceeded` | 配额用尽或长窗口限制 | 否 | 是 |
| `rate_limit_error` | 短期限流 | 是 | 是 |
| `timeout_error` | 请求超时 | 是 | 是 |
| `connection_error` | 无法连接 | 是 | 是 |
| `server_error` | 上游暂时不可用 | 是 | 是 |
| `context_length_error` | 超过安全上下文/输出限制 | 否 | 否 |
| `invalid_request_error` | 请求参数/格式不被接受 | 否 | 否 |
| `stream_interrupted` | 流式输出后中断 | 否 | 否（不自动重放） |
| `provider_error` | 其它 Provider 失败 | 是 | 是 |

展示层只暴露 `error_code`、用户可读消息和建议，不回传密钥或原始上游敏感头。

## 5. 安全边界（不是 OS/容器沙箱）

以下控制面**不是**沙箱，不得在 UI 或文档中写成“沙箱隔离”：

| 控制面 | 实际含义 | 明确不是 |
|---|---|---|
| 权限模式 `auto` / `approve` / `readonly` | 会话级工具门控 | 容器/OS 隔离 |
| `permissions.yaml` `deny`/`ask`/`allow` | 应用层授权决策 | 内核沙箱 |
| 命令白名单 + 无 shell 拼接 | 降低危险命令面 | 进程/网络隔离 |
| Worker 路径所有权 | 协作写入边界 | 多租户隔离 |
| Plugin `permissions` 列表 | 用户可见同意面 | 技术强制沙箱 |
| MCP / Hooks | 以 **MAO 同进程权限** 运行的第三方扩展 | 可信计算基外的隔离 |

**推荐**：默认 `approve`；不信任的项目用 `readonly`；启用插件/MCP 前审查来源与配置。  
详见根目录 [`SECURITY.md`](../SECURITY.md) 与 [`插件开发指南.md`](插件开发指南.md)。

## 6. 如何更新本矩阵

1. 只改 `src/models/catalog.py` 中的条目与模板。
2. 若某能力改为 `supported`：必须填写可追溯 `metadata_source`（官方文档等），且不得含 `unverified`。
3. 运行：
   ```bash
   python -m pytest -q tests/test_provider_matrix.py tests/test_model_catalog.py tests/test_explainable_model_routing.py tests/test_provider_errors.py
   ```
4. 同步更新本文对应表格与「更新日期」。
5. 真实 smoke 通过后，在 `docs/acceptance/` 追加脱敏记录，再升级能力状态。

## 7. 变更规则

- 矩阵与目录冲突时以 **catalog 代码** 为准，并修文档。
- 不得把 `unverified` 能力写进对外“已支持”列表或自动路由节省文案。
- 新增 Provider 预设时：先加 catalog 条目 → 模板 `supported_models` → 测试 → 本文表格。

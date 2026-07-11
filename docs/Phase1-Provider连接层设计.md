# Phase 1 设计：Provider 与模型连接层简化

> 目标：让当前 Multi-Agent Orchestrator 的模型连接变得像 OpenCode / CCswitch 一样简单。  
> 状态：设计 + 初版实现

---

## 一、当前痛点

1. **手动编辑 YAML**：用户需要手动写 `config/providers.yaml`，容易出错。
2. **模型名不确定**：不知道 `glm-ark` 到底对应上游什么 `model_id`，也不知道有哪些可用模型。
3. **无法测试连通**：配置完只能直接跑任务，失败时不知道是连接问题还是任务问题。
4. **主模型选择不直观**：Orchestrator 和 Reviewer 的模型分别配置，容易遗漏或错配。

---

## 二、目标体验

```text
$ python run.py setup

欢迎使用模型连接向导 🌐

请选择 Provider 类型：
  ▸ 火山方舟 (Volcengine Ark)
    OpenAI
    Anthropic
    Kimi 转发
    自定义 OpenAI 兼容服务

请输入 API Key：••••••••
正在测试连接... ✅ 连接成功
发现以下可用模型：
  ▸ ark-code-latest
    ark-chat-latest
    deepseek-v3

请选择主模型（用于对话和任务拆分）：
  ▸ ark-code-latest

是否添加更多 Provider？ [y/N]

配置已保存到 config/providers.yaml
主模型：glm-ark
```

---

## 三、架构设计

### 3.1 核心概念

| 概念 | 说明 | 对应 OpenCode |
|------|------|---------------|
| **Provider** | 模型服务提供方，如火山方舟、OpenAI、Kimi 转发 | `Provider.Info` |
| **Model** | 一个具体可调用的模型，包含 model_id、capabilities、cost | `Model` |
| **Model Alias** | 给用户看的短名，如 `glm-ark` | `modelID` |
| **Connection Profile** | 一个 Provider 实例，包含 base_url、api_key、timeout | `Provider.options` |
| **Model Pool** | 所有连通模型的集合 | `Provider.list()` |
| **Main Model** | 用户选择的主模型，用于对话和任务规划 | `config.model` |

### 3.2 配置结构

保持 `config/providers.yaml` 兼容现有格式，但增加可选的 `model_pool` 和 `main_model`：

```yaml
main_model: glm-ark

providers:
  ark:
    name: 火山方舟 Coding Plan
    type: anthropic
    base_url: https://ark.cn-beijing.volces.com/api/coding
    api_keys:
      - ${ARK_API_KEY}
    timeout: 120
    rpm_limit: 60

models:
  glm-ark:
    provider: ark
    model_id: ark-code-latest
    input_price_per_1m: 1.0
    output_price_per_1m: 1.0
    capabilities:
      - tool_use
      - coding
```

### 3.3 内置模型目录

新增 `src/models/catalog.py`，内置常见中文模型配置：

```python
BUILTIN_MODELS = {
    "glm-ark": {
        "provider_type": "anthropic",
        "model_id": "ark-code-latest",
        "name": "火山方舟 Coding",
        "capabilities": ["tool_use", "coding", "reasoning"],
    },
    "kimi-for-coding": {
        "provider_type": "openai",
        "model_id": "kimi-for-coding",
        "name": "Kimi Coding",
        "capabilities": ["tool_use", "coding"],
    },
}
```

### 3.4 连通性测试

新增 `src/gateway/connection_test.py`：

- 对每个 Provider 发一个极短/低成本的请求（如 "hi" 或拉取模型列表）。
- 支持 Anthropic Messages API、OpenAI Chat API、通用 OpenAI 兼容 API。
- 返回：`ok`、`available_models`、`error_message`。

---

## 四、实现清单

| 文件 | 作用 |
|------|------|
| `src/models/catalog.py` | 内置模型目录 |
| `src/gateway/connection_test.py` | Provider 连通性测试 |
| `src/cli/agent_setup.py` | 新的连接向导（TUI） |
| `src/cli/setup_wizard.py` | 保留旧版，后续迁移 |
| `config/providers.yaml` | 新增 `main_model` 字段 |

---

## 五、关键流程

### 5.1 添加 Provider

1. 选择 Provider 类型。
2. 根据类型询问必要信息：
   - API Key
   - Base URL（可选，使用默认值）
   - Timeout（可选）
3. 调用连通性测试。
4. 如果成功，列出可用模型。
5. 如果失败，显示错误并允许重试。

### 5.2 选择主模型

1. 从所有已连通 Provider 的模型中列出。
2. 用户选择一个作为主模型。
3. 保存到 `config/providers.yaml` 的 `main_model`。

### 5.3 运行任务时

1. `GatewayClient` 读取 `main_model`。
2. 默认所有 Agent/Orchestrator/Reviewer 使用 `main_model`，除非用户显式覆盖。

---

## 六、与旧版的兼容

- 保留 `providers.yaml` 现有字段。
- `main_model` 是新增可选字段；不存在时，默认使用第一个 model。
- 旧的 `setup_wizard.py` 仍可运行，但新用户推荐使用 `agent_setup.py`。

---

## 七、后续可扩展

- **模型能力标签**：根据 capability 自动选择 Agent 模型。
- **模型别名映射**：支持 CCswitch 式转发，一个上游模型名映射多个逻辑名。
- **多 Provider 负载均衡**：多 key 轮询、失败自动切换 Provider。
- **模型池可视化**：在 TUI 中显示已连接模型和状态。

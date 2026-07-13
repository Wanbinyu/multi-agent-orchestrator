# 模型连接配置 UI 工具计划书

> 目标：把当前需要手动编辑 YAML / 回答 CLI 问题的模型连接配置流程，升级为像 CCswitch 一样直观的图形化配置界面。  
> 日期：2026-07-12  
> 当前状态：Stage 1/2/3 均已完成并端到端验证通过  
> 关联文档：`任务书-Agent工具进化.md` Phase 1

---

## 一、背景与痛点

当前配置模型连接有两种方式：

1. **手动编辑 `config/providers.yaml`**：容易写错缩进、模型名、provider 类型。
2. **`python run.py agent-setup` CLI 向导**：需要逐行回答问题，体验不够直观，且无法在同一界面查看、编辑、测试多个 Provider。

用户期望的体验：

- 打开一个窗口/页面。
- 选择预设 Provider（火山方舟 / OpenAI / Anthropic / Kimi 转发 / 自定义）。
- 粘贴 API Key，可选改 Base URL / 模型映射。
- 点击`测试连接`，自动列出可用模型。
- 勾选主模型，保存。
- 所有已连通模型进入`模型池`，供 Orchestrator / Worker 使用。

---

## 二、目标

打造一个**本地运行的模型连接配置 UI**，作为 `agent-setup` 的图形化替代方案（CLI 版保留作为 fallback）。

核心目标：

1. **降低出错率**：表单校验、预设模板、自动补全。
2. **提升效率**：一次界面内完成添加 → 测试 → 选主模型 → 保存。
3. **可视化模型池**：已连接 Provider、可用模型、当前主模型一目了然。
4. **安全本地运行**：不依赖外部服务器，API Key 只保存在本地 `.env` / YAML。

---

## 三、功能需求

### 3.1 预设 Provider 模板

内置常用 Provider 模板，用户选择后自动填充大部分字段：

| 预设 | 默认 Base URL | 协议类型 | 默认模型映射 |
|---|---|---|---|
| 火山方舟 | `https://ark.cn-beijing.volces.com/api/v3/` | openai | glm-ark 等 |
| OpenAI | `https://api.openai.com/v1` | openai | gpt-4o, gpt-4o-mini |
| Anthropic | `https://api.anthropic.com` | anthropic | claude-fable-5, claude-sonnet-5 |
| Kimi 转发 | `https://api.va11.icu/` | anthropic | kimi-for-coding |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4/` | openai | glm-4, glm-4-flash |
| DeepSeek | `https://api.deepseek.com/` | openai | deepseek-v3, deepseek-r1 |
| 自定义 | 用户填写 | 用户选择 | 用户填写 |

### 3.2 添加 / 编辑 Provider

表单字段：

- **Provider 名称**（唯一标识，如 `kimi`）
- **显示名称**（如 `Kimi 转发`）
- **协议类型**：Anthropic / OpenAI 兼容
- **Base URL**
- **API Key**（密码框，支持多个 key 用换行/逗号分隔）
- **模型映射表**（逻辑名 → 上游真实模型名）
- **超时时间**（可选，默认 60s）

校验：

- Provider 名称不能重复。
- Base URL 必须以 `http(s)://` 开头。
- 至少填写一个 API Key。

### 3.3 连通性测试

点击`测试连接`后：

1. 用当前表单信息实例化 Provider。
2. 发送一个极小的测试请求（如 `{messages: [{role: user, content: hi}], max_tokens: 1}`）。
3. 如果成功，返回 ✅ 并列出可用模型。
4. 如果失败，返回 ❌ 和具体错误（网络 / 鉴权 / 协议不匹配 / 模型不存在）。

### 3.4 模型池与主模型选择

- 左侧/上方列出所有已保存 Provider。
- 选中 Provider 后，右侧显示该 Provider 下的可用模型别名列表。
- 每个 Provider 可勾选`启用/禁用`。
- 从所有启用模型中选择一个作为 **主模型（main_model）**。
- 支持为每个模型配置价格（input/output per 1M tokens），用于后续计费。

### 3.5 保存与加载

- 保存时生成/更新 `config/providers.yaml` 和 `.env`。
- 启动 UI 时自动读取现有配置，支持继续编辑。
- 提供`导出配置`和`重置为默认`按钮（可选）。

### 3.6 安全与隐私

- UI 只在本地运行（`127.0.0.1`）。
- API Key 输入框使用密码掩码。
- Key 只写入本地 `.env` 文件，不会被打印到日志或前端网络请求。
- 测试连接请求由后端直接发出，避免 key 泄漏到浏览器前端（如果选择 Web 方案）。

---

## 四、技术方案选型

候选方案：

| 方案 | 优点 | 缺点 | 推荐度 |
|---|---|---|---|
| **A. FastAPI + Jinja2 + Vanilla JS** | 与现有 Python 栈一致；轻量；可控；可后续扩展为 API Server | 需要写少量前端代码 | ⭐⭐⭐⭐⭐ |
| **B. NiceGUI（Python 原生 UI）** | 几乎不用写 JS；快速出界面；自动处理前后端通信 | 生态较小；定制性受限；打包体积大 | ⭐⭐⭐⭐ |
| **C. Textual（TUI）** | 终端内运行，无需浏览器；与 CLI 风格一致 | 不够`像 CCswitch`；交互控件有限 | ⭐⭐⭐ |
| **D. PyQt / Flet / Streamlit** | 组件丰富；可打包成 EXE | 依赖重；Streamlit 隐私/性能一般；PyQt 授权复杂 | ⭐⭐ |

**推荐方案：A（FastAPI + 轻量前端）**

理由：

- 与现有 `src/gateway/` 代码天然集成。
- 未来可直接复用为 API Server，为 Web UI / VS Code 插件打基础。
- 前端只需要一个 HTML 页面 + 少量 JS，维护成本低。
- 不需要引入新的 UI 框架依赖。

---

## 五、UI 设计草稿

```text
┌─────────────────────────────────────────────────────────────┐
│  Multi-Agent Orchestrator - 模型连接配置                      │
├────────────────────┬────────────────────────────────────────┤
│                    │                                        │
│  Provider 列表      │   Provider 详情 / 编辑表单              │
│  ─────────────     │   ─────────────────────────────        │
│  ➕ 添加 Provider   │   预设: [火山方舟 ▼]                    │
│                    │   名称: [kimi-ark        ]              │
│  ◉ 火山方舟         │   显示名: [火山方舟       ]             │
│  ○ OpenAI          │   协议:  [OpenAI兼容 ○] [Anthropic ○]  │
│  ○ Anthropic       │   Base URL: [https://... ]              │
│  ○ Kimi 转发        │   API Key: [••••••••    ]              │
│                    │   超时:   [60  ] 秒                     │
│                    │                                        │
│                    │   模型映射:                            │
│                    │   ┌──────────────┬──────────────┐      │
│                    │   │ 逻辑名        │ 上游模型名    │      │
│                    │   │ glm-ark      │ ark-code-latest│      │
│                    │   │ glm-chat     │ ...          │      │
│                    │   └──────────────┴──────────────┘      │
│                    │                                        │
│                    │   [测试连接]  [保存]  [删除]            │
│                    │                                        │
│                    │   测试结果: ✅ 连通，可用模型 8 个       │
│                    │                                        │
├────────────────────┴────────────────────────────────────────┤
│  模型池                                                       │
│  [✓] 火山方舟 / glm-ark  [✓] 火山方舟 / glm-chat ...         │
│  主模型: [glm-ark ▼]                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 六、数据流

```text
用户操作 UI
    │
    ▼
FastAPI 后端
    │
    ├── 读取/写入 config/providers.yaml
    ├── 读取/写入 .env
    ├── 调用 src/gateway/client.py 进行连通性测试
    └── 返回结果给前端
    │
    ▼
前端展示 Provider 列表、可用模型、主模型
```

---

## 七、新增/修改的文件

### 新增

- `src/ui/` 目录：
  - `app.py`：FastAPI 应用入口。
  - `routers/providers.py`：Provider CRUD、测试连接、保存配置 API。
  - `templates/index.html`：主页面。
  - `static/{css,js}/`：样式和前端逻辑。
  - `presets.py`：内置 Provider 预设数据。
- `scripts/run_ui.py`：一键启动 UI 的脚本。
- `docs/模型连接配置UI工具计划书.md`：本计划书。

### 修改

- `src/gateway/client.py`：
  - 增加一个 `test_connection(provider_name)` 方法，用于不发真实聊天的连通性检测。
  - 或者复用现有 `provider.chat()`，但用最小请求。
- `src/cli/agent_setup.py`：
  - 保留 CLI 版，作为无 UI 环境的 fallback。
- `requirements.txt`：
  - 新增 `fastapi`, `uvicorn`, `jinja2`（如果选方案 A）。
- `README.md`：
  - 增加`图形化配置模型`章节。

---

## 八、实现阶段

### Stage 1：最小可用 UI（MVP）

状态：**已完成（2026-07-11）**

1. ✅ 搭建 FastAPI 骨架，渲染 `index.html`。
2. ✅ 实现 Provider 列表读取 API（从 `providers.yaml`）。
3. ✅ 实现前端表单：名称、协议、Base URL、API Key、模型映射。
4. ✅ 实现`保存`按钮，写回 `providers.yaml` 和 `.env`。
5. ✅ 实现`测试连接`按钮，调用后端最小请求验证。

验收标准：

- 用户能在浏览器里添加一个 Provider 并保存。
- 保存后 `python run.py "需求"` 能直接使用新配置。
- 测试连接成功/失败都有明确提示。

### Stage 2：预设模板 + 模型池 + 状态可视化

状态：**已完成（2026-07-11）**

1. ✅ 内置 15+ 常用 Provider 预设（Anthropic / OpenAI / DeepSeek / 火山方舟 / 火山方舟 Coding / Kimi / 智谱 GLM / MiniMax / 阶跃星辰 / 通义千问 / 百度千帆 / SiliconFlow / OpenRouter / Azure OpenAI / 自定义 Anthropic / 自定义 OpenAI）。
2. ✅ 选择预设后自动填充 Base URL、协议、默认模型映射。
3. ✅ 右侧/底部显示所有已保存 Provider 的模型列表（模型池）。
4. ✅ 每个 Provider 支持一键启用/禁用；禁用后其模型自动从模型池和主模型候选中移除。
5. ✅ Provider 卡片显示连通状态：绿色=已连通、黄色=已保存待测试、灰色=未配置 Key。
6. ✅ 测试状态持久化到 `config/ui_state.yaml`，刷新页面后仍可看到上次测试结果。
7. ✅ 编辑 Provider 时 API Key 输入框留空即可保留原 Key，避免误清空。
8. ✅ 支持选择 `main_model`。

验收标准：

- 新用户 3 步内完成 Provider 添加并设置主模型。
- 配置结果与 `config/providers.yaml` 完全一致。
- 启用/禁用 Provider 后，模型池与 `GatewayClient` 行为同步。

### Stage 3：体验与安全打磨

状态：**已完成（2026-07-12）**

1. ✅ API Key 掩码输入。
2. ✅ 表单校验：名称唯一、URL 格式、至少一个 key（新增时）。
3. ✅ 一键启动脚本 `python scripts/run_ui.py`（自动打开浏览器、Windows UTF-8 适配）。
4. ✅ 错误提示已覆盖网络 / 鉴权 / 协议不匹配 / 模型不存在等场景。
5. ✅ 模型回退策略：当 `workers.yaml` 中配置的 Orchestrator / Reviewer / Worker 默认模型不可用时，自动回退到 `GatewayClient` 的主模型，再回退到第一个可用模型，避免`未知模型`崩溃。
6. ✅ README 使用说明已更新，推荐图形化界面配置。
7. ✅ 端到端验证通过：`python run.py "用一句话总结 Python" --max-workers 1` 成功执行并输出结果。

验收标准：

- 常见错误配置能在保存前被拦截。
- 不暴露 key 到前端日志/网络。
- 保存后 CLI 可立即使用新配置。
- 禁用部分 Provider 后，运行命令仍能自动回退到可用模型。

---

## 九、风险与对策

| 风险 | 对策 |
|---|---|
| 前端通过 HTTP 传输 API Key | 后端直接发测试请求，key 不离开后端；生产环境若需要 HTTPS，可用 `localhost` + 自签名证书 |
| 不同 Provider 的`可用模型`接口不统一 | 不自动枚举，改为用户手动填写模型映射；后续可针对 OpenAI 兼容服务做 `/models` 接口支持 |
| 多个 key 轮询配置复杂 | UI 中 API Key 用多行文本框，一行一个 key；后端保存为列表 |
| 自定义 Provider 容易配错 | 提供`自定义`预设模板，默认给出示例字段；测试连接时给出详细错误 |
| UI 与 CLI 配置格式不一致 | 共用同一套 `providers.yaml` 读写逻辑，确保双向兼容 |

---

## 十、验收标准（整体）

- [ ] 运行 `python scripts/run_ui.py` 后浏览器自动打开配置界面。
- [ ] 用户可以选择预设 Provider，填写 API Key，点击测试连接，3 秒内得到结果。
- [ ] 测试成功后，界面显示可用模型列表。
- [ ] 用户可以选择主模型并保存。
- [ ] 保存后 `python run.py "开发一个登录功能"` 能直接使用新配置跑通。
- [ ] API Key 不暴露在浏览器开发者工具的 Network / Console 中。
- [ ] 无 UI 环境下，`python run.py agent-setup` 仍可正常使用。

---

## 十一、下一步动作

1. 进入 `任务书-Agent工具进化.md` Phase 2：对话式交互改造。
2. 将 `python run.py "需求"` 的单次命令模式升级为持续对话界面/会话。
3. 在主模型中支持工具调用循环（读文件、写文件、执行命令、调用子模型）。

---

*本文档为项目计划，Stage 1/2/3 均已实现并验证通过。*

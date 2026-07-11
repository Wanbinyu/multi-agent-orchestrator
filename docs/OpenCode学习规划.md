# OpenCode 学习规划

> 目标：从 OpenCode 开源项目（https://github.com/anomalyco/opencode）中学习可复用的设计，用于将当前 Multi-Agent Orchestrator 进化为一个实用的 Agent 工具。  
> 仓库位置：`E:\multi-agent-orchestrator\reference-opencode`  
> 状态：规划阶段

---

## 一、OpenCode 项目概览

OpenCode 是一个 **TypeScript + Effect** 编写的开源 AI Coding Agent，定位是 "The open source AI coding agent"。它同时提供：

- **CLI 终端工具**
- **Desktop 桌面应用（Beta）**
- **VS Code 扩展**

核心特点：

- 多 Provider 支持（OpenAI、Anthropic、Gemini、Bedrock、Azure、OpenRouter、Kimi 转发等）
- 内置多个 Agent 角色（build / plan / general / explore 等）
- 丰富的本地工具集（read / write / edit / shell / grep / glob / apply_patch 等）
- 细粒度的权限系统（按工具、按路径、按模式配置 allow / ask / deny）
- 持久化的 Session 运行时和上下文管理
- 工具调用循环 + 子 Agent 委派（Task tool）

---

## 二、学习原则

因为 OpenCode 项目体量大、依赖 Effect 函数式框架，直接全量阅读成本高。**我们的目标不是复刻 OpenCode，而是借鉴它的设计模式，用 Python 实现一个更轻量、更适合我们需求的多模型 Agent 工具。**

学习原则：

1. **先学思想，后学实现**：优先理解它为什么这样设计，而不是具体 TypeScript/Effect 语法。
2. **按需深入**：只深入和我们目标强相关的模块，跳过 infra、desktop、plugin、LSP 等暂时无关部分。
3. **先跑通，再抽象**：第一阶段先理解它的最小可运行单元（配置 → 模型 → 工具 → 会话循环）。
4. **做笔记，画迁移图**：每学完一个模块，记录“这个设计如何映射到我们的 Python 项目”。

---

## 三、学习阶段规划

| 阶段 | 主题 | 目标 | 预计优先级 |
|------|------|------|-----------|
| **Phase 1** | Provider 与模型连接层 | 理解如何配置、连接、测试多个模型服务 | ⭐⭐⭐ 最高 |
| **Phase 2** | 工具系统 | 理解工具定义、注册、执行、权限控制 | ⭐⭐⭐ 最高 |
| **Phase 3** | Agent 与会话循环 | 理解主 Agent 如何思考、调用工具、多轮对话 | ⭐⭐⭐ 最高 |
| **Phase 4** | 子 Agent 与任务委派 | 理解 Task tool 如何启动子 Agent 并行工作 | ⭐⭐ 高 |
| **Phase 5** | TUI / UI 层 | 理解终端界面如何渲染对话、进度、工具结果 | ⭐⭐ 高 |
| **Phase 6** | 权限与安全 | 理解 allow/ask/deny 权限模型和外部目录访问 | ⭐⭐ 高 |
| **Phase 7** | Session 上下文与持久化 | 理解 CONTEXT.md 中的 durable session runtime | ⭐ 中 |

---

## 四、第一阶段详细路径：Provider 与模型连接层

### 为什么先学这个

当前我们项目的最大痛点就是 **连接模型太麻烦**（手动编辑 YAML、选模型名、容易配错）。OpenCode 的 Provider 层设计得很成熟：用户添加 Provider → 自动测试连通 → 枚举可用模型 → 选择主模型。这正是我们 Phase 1 要做的。

### 第一阶段要学习的文件

| 文件 | 学习内容 |
|------|----------|
| `packages/llm/README.md` | LLM 包的公共 API、Provider facade、Model 概念 |
| `packages/llm/DESIGN.md` | AI Library 的重新设计草案，理解 `generate` vs `generateTurn`、Model Run vs Provider Turn |
| `packages/llm/src` | Route、Protocol、Provider 的实现方式（可选，先粗略看） |
| `packages/opencode/src/provider/provider.ts` | OpenCode 如何管理 Provider 列表、模型解析、默认模型 |
| `packages/opencode/src/config/config.ts` | 配置文件如何加载 Provider、Agent、权限等 |
| `packages/opencode/src/auth/auth.ts` | API Key / OAuth 等认证方式如何管理 |

### 第一阶段要回答的问题

1. OpenCode 如何表示一个 Provider？配置项有哪些（apiKey、baseURL、headers、model map 等）？
2. OpenCode 如何表示一个 Model？模型名和 Provider 之间是如何关联的？
3. 添加 Provider 后，OpenCode 如何测试连通性？是发一个低价测试请求，还是拉取模型列表？
4. 用户如何选择“主模型”？默认模型如何决定？
5. 它如何处理模型能力不匹配（如某模型不支持 tool use、不支持 vision）？

### 第一阶段输出物

- 一份 Provider/Model 配置设计草案，用于我们的 Python 项目。
- 明确我们第一阶段要实现的最小功能：
  1. 图形/TUI 添加 Provider
  2. 自动连通检测
  3. 列出可用模型
  4. 选择主模型

---

## 五、关键文件索引

下面是按模块整理的关键文件，后续学习时可直接定位。

### 1. Provider / LLM 层

| 路径 | 说明 |
|------|------|
| `packages/llm/README.md` | LLM 包 API 文档 |
| `packages/llm/DESIGN.md` | 下一代 AI Library 设计草案 |
| `packages/llm/src/providers/` | 各 Provider 实现 |
| `packages/opencode/src/provider/provider.ts` | OpenCode Provider 服务 |
| `packages/opencode/src/provider/auth.ts` | 认证管理 |
| `packages/opencode/src/provider/transform.ts` | Provider 选项转换 |

### 2. 工具系统

| 路径 | 说明 |
|------|------|
| `packages/opencode/src/tool/tool.ts` | Tool 定义接口（id / description / parameters / execute） |
| `packages/opencode/src/tool/registry.ts` | 工具注册表，初始化所有内置工具 |
| `packages/opencode/src/tool/read.ts` / `read.txt` | 读文件工具实现和模型使用说明 |
| `packages/opencode/src/tool/write.ts` / `write.txt` | 写文件工具 |
| `packages/opencode/src/tool/edit.ts` / `edit.txt` | 编辑文件工具 |
| `packages/opencode/src/tool/shell.ts` / `shell/shell.txt` | 执行命令工具 |
| `packages/opencode/src/tool/glob.ts` / `glob.txt` | 文件匹配工具 |
| `packages/opencode/src/tool/grep.ts` / `grep.txt` | 内容搜索工具 |
| `packages/opencode/src/tool/task.ts` / `task.txt` | 启动子 Agent 工具 |
| `packages/opencode/src/tool/apply_patch.ts` | 应用代码补丁工具 |

### 3. Agent 系统

| 路径 | 说明 |
|------|------|
| `packages/opencode/src/agent/agent.ts` | Agent 定义、build/plan/general/explore 等角色 |
| `packages/opencode/src/agent/generate.txt` | 自动生成新 Agent 的提示词 |
| `packages/opencode/src/agent/prompt/*.txt` | compaction / explore / summary / title 等提示词 |

### 4. Session / 对话循环

| 路径 | 说明 |
|------|------|
| `CONTEXT.md` | Session Runtime 详细设计文档 |
| `packages/opencode/src/session/prompt.ts` | `SessionPrompt` 服务，`prompt()` / `loop()` / `runLoop()` |
| `packages/opencode/src/session/processor.ts` | 流事件处理器、part 持久化、重试/清理 |
| `packages/opencode/src/session/llm.ts` | LLM 运行时封装（AI-SDK 默认 + native 实验） |
| `packages/opencode/src/session/tools.ts` | 将注册表工具转为 AI-SDK `Tool` 对象 |
| `packages/opencode/src/session/run-state.ts` | Session 并发保护 |
| `packages/opencode/src/session/compaction.ts` | 上下文溢出时的压缩/摘要 |
| `packages/opencode/src/cli/cmd/run/runtime.ts` | 本地交互模式启动、生命周期 |
| `packages/opencode/src/cli/cmd/run/runtime.queue.ts` | 交互式 prompt 队列 |

### 5. 权限系统

| 路径 | 说明 |
|------|------|
| `packages/opencode/src/permission/` | 权限规则实现 |
| `packages/opencode/src/agent/agent.ts` | Agent 级别的 permission ruleset 配置 |

### 6. TUI / CLI

| 路径 | 说明 |
|------|------|
| `packages/opencode/bin/opencode` | 原生二进制启动器（选择平台对应可执行文件） |
| `packages/opencode/src/index.ts` | yargs CLI 入口，注册所有命令 |
| `packages/opencode/src/cli/cmd/run.ts` | `opencode run` 命令，支持 `--mini` / `--interactive` / `--attach` |
| `packages/opencode/src/cli/cmd/run/runtime.ts` | 本地交互模式生命周期 |
| `packages/opencode/src/cli/cmd/run/runtime.queue.ts` | prompt 队列 |
| `packages/opencode/src/cli/cmd/tui.ts` | 完整 TUI 命令（启动 worker） |
| `packages/tui/src/index.tsx` / `app.tsx` | SolidJS TUI 应用入口 |
| `packages/tui/src/context/*` | 各类上下文（SDK、project、theme、permissions、editor） |
| `packages/tui/src/routes/home.tsx` / `session.tsx` | 主界面路由 |
| `packages/tui/src/keymap.tsx` / `config/keybind.ts` | 键盘绑定 |
| `packages/cli/` | **注意**：这是 `lildax` 包装器 CLI，不是主 `opencode` CLI |

---

## 六、可迁移到我们 Python 项目的要点

| OpenCode 设计 | 我们项目如何借鉴 |
|---------------|------------------|
| Provider.configure({ apiKey, baseURL }) | 我们的 `providers.yaml` 可以改为向导式配置，支持测试连通 |
| Model 是 Provider 上的可执行值 | 我们的 `models` 映射可以简化为：Provider + model_id |
| Tool = { id, description, parameters, execute } | 我们可以用 Python dataclass/Pydantic 定义工具，统一注册到 ToolRegistry |
| 工具说明用 `.txt` 文件拼接到 prompt | 我们也可以为每个工具写 Markdown/文本说明，动态拼接 |
| Agent 是有权限和模型的角色 | 我们的 Worker 可以升级为 Agent，每个 Agent 绑定模型和权限 |
| `task` tool 启动子 Agent | 我们的主模型可以调用子模型作为工具 |
| allow / ask / deny 权限模型 | 我们的 `run_command` / `read_file` 可以增加权限配置 |
| 持久化 Session | 我们的对话可以保存为 SQLite/JSON，支持多轮恢复 |

---

## 七、下一步行动

1. **先读完第一阶段文件**：`packages/llm/README.md`、`DESIGN.md`、`packages/opencode/src/provider/provider.ts`、`src/config/config.ts`。
2. **画出我们项目的 Provider/Model/Agent 配置新架构草图**。
3. **实现一个最小 Demo**：在 Python 中做一个简单的 Provider 配置向导（TUI），支持添加火山方舟 Provider 并测试连通。
4. 之后再进入 Phase 2 学习工具系统。

---

## 八、注意事项

- OpenCode 重度使用 **Effect**（函数式效果库），阅读时不必纠结语法细节，重点看数据流和设计。
- OpenCode 的 `AGENTS.md` 是贡献指南，不是 Agent 架构文档，不要混淆。
- 项目默认分支是 `dev`，阅读源码时以 `dev` 分支为准。
- 我们不要复制 OpenCode 的所有功能，而是优先实现：**连接简单 + 对话交互 + 工具调用 + 多模型协同**。

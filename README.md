# 多模型 Agent 编排工具 —— CLI MVP

一个**总工模型 + 多外部模型并发协作**的命令行原型工具。目标：解决所有问题都用好用且贵的模型导致token消耗过快的问题，总工用贵模型，其他的分工可以连接便宜但是听话的模型。并且现在很多模型的优势并不相同，未来差异可能更大（也可能更小），如果模型差异化更大那就可以让每个擅长不同工作和方向的模型相互配合，发挥它们各自最大的作用。
主要目的就是为了省token。

A **Chief Engineer Model + Multi-External Model Concurrent Collaboration** command-line prototype tool. **Goal**: Solve the problem of excessive token consumption caused by using only good but expensive models for all tasks. The Chief Engineer uses the expensive model, while other divisions can connect to cheaper but obedient models. Moreover, different models currently have distinct advantages, and future differences may become even greater (or smaller). If model differentiation increases further, each model can be assigned to tasks and directions it excels at, maximizing their individual strengths.

**Primary purpose**: Save tokens.

## 目录结构

```
multi-agent-orchestrator/
├── config/
│   ├── providers.yaml        # Provider、模型、价格、主模型配置
│   └── workers.yaml          # Worker 角色与 Orchestrator / Reviewer 提示词
├── docs/                     # 设计文档与开发记录
├── output/                   # 默认输出目录
├── sessions/                 # 对话会话存储
├── src/
│   ├── cli/
│   │   ├── agent_setup.py    # 新版 Provider / 主模型连接向导
│   │   ├── setup_wizard.py   # 旧版场景化配置向导
│   │   ├── chat_command.py   # CLI 对话 REPL
│   │   └── provider_presets.py
│   ├── core/
│   │   ├── orchestrator.py   # 总工：拆任务
│   │   ├── dispatcher.py     # 调度器：DAG 并发执行
│   │   ├── reviewer.py       # 审查收口
│   │   ├── worker.py         # Worker：执行单任务
│   │   ├── session.py        # 多轮会话持久化
│   │   └── agent.py          # 对话 Agent（工具循环）
│   ├── gateway/
│   │   ├── provider.py       # Provider 抽象与 Anthropic/OpenAI 实现
│   │   ├── router.py         # 模型路由
│   │   ├── client.py         # 网关客户端 + 计费 + 重试
│   │   ├── connection_test.py
│   │   └── model_catalog.py
│   ├── models/
│   │   └── schemas.py        # Pydantic 数据模型
│   ├── tools/
│   │   ├── file_tools.py     # 代码块解析与文件写入
│   │   └── worker_tools.py   # read_file / run_command 工具
│   └── ui/                   # 图形化界面
│       ├── app.py
│       ├── routers/
│       │   ├── providers.py  # 模型连接配置 API
│       │   └── chat.py       # 对话 API
│       ├── presets/
│       ├── templates/
│       │   ├── index.html    # 配置页
│       │   └── chat.html     # 对话页
│       └── static/
│           ├── css/style.css
│           ├── js/app.js     # 配置页逻辑
│           └── js/chat.js    # 对话页逻辑
├── tests/                    # pytest 测试
├── scripts/
│   └── run_ui.py             # 一键启动 UI
├── run.py                    # CLI 入口
├── requirements.txt
├── 项目计划书.md
└── TESTING.md                # 测试指南
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 Provider 和主模型（推荐图形化界面）

```bash
python scripts/run_ui.py
```

浏览器会自动打开 `http://127.0.0.1:8123`，界面支持：

1. 从 15+ 常用 Provider 预设中选择（Anthropic / OpenAI / DeepSeek / 火山方舟 / Kimi / 智谱 GLM / 自定义等）。
2. 粘贴 API Key，自动填充 Base URL 与默认模型映射。
3. 点击`测试连接`，实时查看连通状态。
4. 启用/禁用任意 Provider；模型池自动过滤只显示启用 Provider 的模型。
5. 选择主模型并保存。
6. 在对话页工作区中按需展开项目目录并只读预览文本文件。

配置会同步写入 `config/providers.yaml` 与 `.env`，与 CLI 完全兼容。

> 如果不方便使用浏览器，也可以继续用命令行向导：
>
> ```bash
> python run.py agent-setup
> ```

### 3. 配置 Worker 角色（旧版向导，可选）

```bash
python run.py setup
```

该向导会引导你：
1. 选择使用场景（软件开发 / 小说创作 / 游戏二次开发 / 软件测试 / 自定义）
2. 配置总指挥（Orchestrator）模型
3. 配置子工程师（Worker）名字、模型、工作内容
4. 生成 `config/workers.yaml`

### 4. 运行

```bash
python run.py "开发一个前后端登录功能，前端用 React，后端用 FastAPI"
```

完整命令选项：

```bash
python run.py "开发一个登录页面" \
  --output output \
  --config config \
  --max-workers 4 \
  --orchestrator-model glm-ark
```

| 选项 | 简写 | 说明 |
|---|---|---|
| `--output` | `-o` | 输出目录，默认 `output` |
| `--config` | `-c` | 配置目录，默认 `config` |
| `--max-workers` | `-w` | 最大并发 Worker 数，默认 `4` |
| `--orchestrator-model` | `-m` | 运行时覆盖总指挥模型 |

> 如果没有指定子命令，`run.py` 会自动把第一个非命令参数当作 `run` 命令的请求参数。

### 5. 进入持续对话模式（CLI）

完成连接配置后，可以直接在命令行与主模型持续多轮对话：

```bash
python run.py chat
```

常用 REPL 命令：

进入对话后输入 `/` 会显示命令候选和说明，继续输入字母可实时过滤；完整列表可用 `/help` 查看。

| 命令 | 说明 |
|---|---|
| `/new [标题]` | 创建新会话 |
| `/load <session_id>` | 加载已有会话 |
| `/save` | 手动保存当前会话 |
| `/context` | 本地显示模型映射、上下文预算、当前估算和自动压缩阈值，不调用模型 |
| `/tree [路径] [深度]` | 本地显示项目结构，不调用模型、不产生 token |
| `/plan <需求>` | 调用 Orchestrator 执行一次性任务计划 |
| `/tools` | 显示当前可用工具 |
| `/exit` | 退出 |

对话产物保存在 `sessions/<session_id>/output/`。

助手回答会在有界的临时区域中**逐块流式预览**，完成后只向终端滚动记录写入一次最终正文，避免长回答把累计渲染帧重复留在控制台。项目分析和工具任务按“探索项目 / 检索代码 / 生成交付物 / 执行验证”分阶段展示；每阶段只展开前 4 项，后续同类操作折叠，并在结束时汇总目录、文件、检索、重复操作和失败数量。使用工具后仍会在控制台显示完整最终答案，不需要再手动打开 `response.md` 才能查看结论。

Agent 系统提示会注入当前模型别名、上游请求模型 ID、本地上下文预算和自动压缩阈值。配置中的 `anthropic` 表示兼容协议，不代表实际模型是 Claude；需要查看实时估算时使用 `/context`，不要让模型自行猜测运行配置。

后续上下文能力将按“模型窗口真值 → 动态安全预算 → 分层压缩 → 持久项目上下文 → 长任务基准”推进，详见 [`docs/上下文扩展与长任务稳定性计划.md`](docs/上下文扩展与长任务稳定性计划.md)。在上游限制未经确认前，默认预算保持 32K。

项目计划在 Phase 7.4 完成后进入开源发布验收，发布定位为 `v0.1.0-beta.1`；准备项和发布门见 [`docs/开源发布准备计划.md`](docs/开源发布准备计划.md)。

### 6. 打开 Web 对话页面

```bash
python scripts/run_ui.py
```

浏览器打开 `http://127.0.0.1:8123/chat`：

- 桌面端默认突出主对话区，上下文面板按需展开；移动端会话列表为横向选择条，上下文以抽屉显示。
- 配置页按“服务连接 / 认证与运行 / 模型映射”分组，移动端模型映射自动切换为纵向卡片。
- 主消息区支持 **SSE 流式显示**，助手回答逐字出现，并保持输入区在当前视口内。
- 支持 Markdown、代码块、工具调用结果和生成文件展示。
- 主模型自动调用 `read_file` / `write_file` / `run_command` 工具。
- 旧的同步接口 `POST /api/chat/sessions/{id}/messages` 仍然保留；新增流式接口 `POST /api/chat/sessions/{id}/messages/stream`。

### 7. 切换总指挥模型

默认总指挥（Orchestrator）在 `config/workers.yaml` 的 `orchestrator.model` 中配置。当前示例配置默认使用 `glm-ark`（你接入的火山方舟模型）。

**方式一：运行时指定**

```bash
python run.py "开发一个登录功能" --orchestrator-model glm-ark
```

**方式二：修改默认配置**

编辑 `config/workers.yaml`：

```yaml
orchestrator:
  model: glm-ark
```

> 注意：总指挥负责拆任务和验收，模型越强拆得越准。便宜模型可以当总指挥，但任务拆分质量可能下降。

### 8. 手动配置（可选）

如果你不想用向导，也可以手动创建 `.env`：

```env
ANTHROPIC_API_KEY=你的 Anthropic Key
OPENAI_API_KEY=你的 OpenAI Key
GLM_API_KEY=你的智谱 Key
DEEPSEEK_API_KEY=你的 DeepSeek Key
ARK_API_KEY=你的火山方舟 Key
```

并编辑 `config/providers.yaml` 和 `config/workers.yaml`。

## Worker 工具

Worker 在执行任务时可以使用以下工具：

- **write_file / edit_file**：使用明确路径创建或精确修改文件
- **project_tree / read_file / list_dir / glob_files / grep_content**：生成受限项目树、读取文件、探查目录和搜索内容，支持绝对路径
- **run_command**：运行白名单内的命令
- **web_search / fetch_url**：搜索网页和抓取 URL 内容
- **search_project_files / search_memory**：检索项目索引与长期记忆

工具调用支持原生 `tool_use` 和 ```` ```tool:xxx ```` Markdown 兜底。协作 Worker 会把工具结果返回模型继续执行，最多 5 轮。

项目文件必须通过 `write_file` 使用明确文件名创建，不再从正文代码块生成 `generated_N`。普通文本结果仍兜底保存为 `output/<type>_<id>/content.txt`。

## 当前支持的模型

- **Anthropic**: Fable 5 / Sonnet 5 / Haiku 4.5
- **OpenAI**: gpt-4o / gpt-4o-mini
- **智谱 GLM**: glm-4 / glm-4-flash
- **DeepSeek**: deepseek-v3 / deepseek-r1
- **自定义 OpenAI 兼容服务**: 通过 `agent-setup` 配置

> 实际可用模型取决于 `config/providers.yaml` 中的配置。`src/models/catalog.py` 内置了常见模型模板。

## 当前功能

- [x] 可配置模型自动拆分子任务
- [x] **场景感知编排**：小说类顺序生成，软件类先架构后并行开发
- [x] **依赖任务输出注入**：下游任务自动获取前置任务输出内容
- [x] 总指挥模型运行时动态切换
- [x] 多模型并发执行
- [x] 任务依赖 DAG 调度与失败级联
- [x] Worker 多轮工具调用与工具权限校验
- [x] 多层模型故障切换、健康冷却和 CLI/Web 通知
- [x] Hooks、MCP stdio/SSE 适配器与本地 LLM Provider
- [x] 代码块自动保存到 output 目录
- [x] Provider 连接向导与连通性测试
- [x] 模型别名与 Provider `model_map`
- [x] **图形化模型连接配置 UI**（FastAPI + 浏览器界面）
- [x] 常用 Provider 预设一键填充与扩展
- [x] Provider 启用/禁用与模型池自动过滤
- [x] API Key 本地 `.env` 存储，编辑时留空保持不变
- [x] 连通性测试状态持久化，页面刷新后仍可见
- [x] 多 key 轮询
- [x] Token 计费和成本统计
- [x] 失败重试与指数退避
- [x] Windows 控制台 UTF-8 自动适配
- [x] 无 Markdown 代码块时自动保存 `content.txt`
- [x] 多轮会话持久化（YAML）
- [x] 对话 Agent 工具循环（最多 5 轮）
- [x] CLI 持续对话 REPL（`python run.py chat`）
- [x] Web 对话页面（`/chat`）
- [x] Web 项目文件树：懒加载目录、隐藏文件开关与受限文本预览
- [x] **流式回答**：Web 与 CLI 均支持逐块输出（SSE）
- [x] 工具循环场景下多轮流式拼接

## 运行测试

见 [TESTING.md](TESTING.md)。

## 后续计划

见 `项目计划书.md`。

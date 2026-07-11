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
├── src/
│   ├── cli/
│   │   ├── agent_setup.py    # 新版 Provider / 主模型连接向导
│   │   ├── setup_wizard.py   # 旧版场景化配置向导
│   │   └── provider_presets.py
│   ├── core/
│   │   ├── orchestrator.py   # 总工：拆任务
│   │   ├── dispatcher.py     # 调度器：DAG 并发执行
│   │   ├── reviewer.py       # 审查收口
│   │   └── worker.py         # Worker：执行单任务
│   ├── gateway/
│   │   ├── provider.py       # Provider 抽象与 Anthropic/OpenAI 实现
│   │   ├── router.py         # 模型路由
│   │   ├── client.py         # 网关客户端 + 计费 + 重试
│   │   ├── connection_test.py
│   │   └── model_catalog.py
│   ├── models/
│   │   └── schemas.py        # Pydantic 数据模型
│   └── tools/
│       ├── file_tools.py     # 代码块解析与文件写入
│       └── worker_tools.py   # read_file / run_command 工具
├── tests/                    # pytest 测试
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

### 2. 配置 Provider 和主模型（推荐新版向导）

```bash
python run.py agent-setup
```

该向导会引导你：
1. 选择或添加 Provider（Anthropic / OpenAI 兼容 / 自定义）
2. 配置 API Key 与 base_url
3. 选择主模型（main_model）
4. 生成 `config/providers.yaml` 和 `.env`

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

### 5. 切换总指挥模型

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

### 6. 手动配置（可选）

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

- **write_file**：自动提取 Markdown 代码块并保存到 `output/<type>_<id>/`
- **read_file**：读取已有文件内容，格式 ````tool:read_file\n{"path": "relative/path"}\n````
- **run_command**：运行白名单内的命令，格式 ````tool:run_command\n{"command": "pytest"}\n````

工具调用通过模型输出中的 ```` ```tool:xxx ```` 代码块触发，执行结果会嵌入到最终 content 中。

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
- [x] Worker 工具调用（read_file / run_command）
- [x] 代码块自动保存到 output 目录
- [x] Provider 连接向导与连通性测试
- [x] 模型别名与 Provider `model_map`
- [x] 多 key 轮询
- [x] Token 计费和成本统计
- [x] 失败重试与指数退避

## 运行测试

见 [TESTING.md](TESTING.md)。

## 后续计划

见 `项目计划书.md`。

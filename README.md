# 多模型 Agent 编排工具 —— CLI MVP

一个**总工模型（Fable 5）+ 多外部便宜模型并发协作**的命令行原型工具。

## 目录结构

```
multi-agent-orchestrator/
├── config/
│   ├── providers.yaml        # API Provider、模型、价格配置
│   └── workers.yaml          # Worker 角色与 Orchestrator 提示词
├── src/
│   ├── core/
│   │   ├── orchestrator.py   # 总工：拆任务
│   │   ├── dispatcher.py     # 调度器：并发执行
│   │   └── worker.py         # Worker：执行单任务
│   ├── gateway/
│   │   ├── provider.py       # Provider 抽象与实现
│   │   ├── router.py         # 模型路由
│   │   └── client.py         # 网关客户端 + 计费
│   ├── models/
│   │   └── schemas.py        # Pydantic 模型
│   └── tools/
│       └── file_tools.py     # 文件写入工具
├── output/                   # 默认输出目录
├── run.py                    # CLI 入口
├── requirements.txt
└── 项目计划书.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行配置向导（推荐）

```bash
python run.py setup
```

向导会引导你：
1. 选择使用场景（软件开发 / 小说创作 / 游戏二次开发 / 软件测试 / 自定义）
2. 配置主工程师（总指挥）模型
3. 配置子工程师（Worker）名字、模型、工作内容
4. 填写所需 API Key

配置完成后自动生成 `config/workers.yaml` 和 `.env`。

### 3. 运行

```bash
python run.py "开发一个前后端登录功能，前端用 React，后端用 FastAPI"
```

指定输出目录：

```bash
python run.py "帮我写一个虐恋的小说" --output "E:\小说"
```

### 4. 切换总指挥模型

默认总指挥（Orchestrator）在 `config/workers.yaml` 中配置，开箱默认使用 `glm-ark`（你接入的火山方舟模型）。  
你可以像 CCswitch 一样随时换成自己已有的、更好用的模型。

**方式一：运行时指定**

```bash
python run.py "开发一个登录功能" --orchestrator-model glm-ark
```

**方式二：修改默认配置**

编辑 `config/workers.yaml`，把 `orchestrator.model` 改成你想要的模型：

```yaml
orchestrator:
  model: glm-ark
```

### 5. 手动配置（可选）

如果你不想用向导，也可以手动创建 `.env`：

```env
ANTHROPIC_API_KEY=你的 Anthropic Key
OPENAI_API_KEY=你的 OpenAI Key
GLM_API_KEY=你的智谱 Key
DEEPSEEK_API_KEY=你的 DeepSeek Key
ARK_API_KEY=你的火山方舟 Key
```

并编辑 `config/workers.yaml` 修改总指挥和子工程师配置。

> 注意：总指挥负责拆任务和验收，模型越强拆得越准。便宜模型可以当总指挥，但任务拆分质量可能下降。

## 当前支持的模型

- **Anthropic**: Fable 5 / Sonnet 5 / Haiku 4.5
- **OpenAI**: gpt-4o / gpt-4o-mini
- **智谱 GLM**: glm-4 / glm-4-flash
- **DeepSeek**: deepseek-v3 / deepseek-r1

## 当前功能

- [x] 可配置模型自动拆分子任务
- [x] 总指挥模型运行时动态切换
- [x] 多模型并发执行
- [x] 代码块自动保存到 output 目录
- [x] Token 计费和成本统计
- [x] 失败重试
- [x] 多 key 轮询

## 后续计划

见 `项目计划书.md`。

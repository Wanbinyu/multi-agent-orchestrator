# Phase 5：长期记忆与项目上下文

**状态**：迭代 1/2/3/4 全部完成（含 Web 聊天页右侧记忆/上下文侧边栏）。

---

## 已交付能力

### 1. 记忆存储与检索 (`src/core/memory.py`)

- `MemoryEntry`：记忆条目（分类、内容、来源、标签、重要性、时间戳）
- `MemoryStore`：YAML 持久化，支持增删改查、关键词倒排索引搜索
- `MemoryContextBuilder`：根据当前输入查询相关记忆，注入 Prompt
- `ProjectIndexer`：遍历项目文件，提取代码符号，支持增量更新
- 配置：`config/memory.yaml`

### 2. Prompt 注入

记忆上下文会注入到以下位置：

- `Agent` 系统提示
- `Orchestrator.plan()` 系统提示
- `Worker.execute()` 用户任务描述顶部
- `Dispatcher.dispatch()` 透传 `memory_context`

### 3. 工具

- `search_project_files(query)`：基于项目文件索引搜索源码文件
- `search_memory(query)`：搜索已保存的长期记忆

工具已在 `worker_tools.py` 注册，`workers.yaml` 中已为相关 Worker 启用。

### 4. CLI 命令 (`/memory`)

在 `python run.py chat` 中可用：

```
/memory add <分类> <内容>
/memory list [分类]
/memory search <查询>
/memory forget <id>
/memory index
/memory summarize
```

### 5. Web API (`src/ui/routers/memory.py`)

- `GET    /api/memory/entries`
- `POST   /api/memory/entries`
- `DELETE /api/memory/entries/{id}`
- `POST   /api/memory/search`
- `POST   /api/memory/files/search`
- `GET    /api/memory/files/status` — 返回项目文件索引状态
- `POST   /api/memory/index`
- `POST   /api/memory/summarize/{session_id}`

### 6. Web 聊天页右侧边栏

在 `/chat` 页面新增可折叠的“上下文 / 记忆”侧边栏：

- **当前会话**：会话 ID、权限模式、创建/更新时间、一键总结当前会话
- **长期记忆**：列出记忆、添加记忆、删除记忆、实时搜索记忆
- **项目索引**：显示索引状态（是否已索引、更新时间、文件数）、一键重建索引
- **本轮记录**：根据 SSE `done` 事件展示本轮工具调用和已写入文件

新增/修改文件：

- `src/ui/templates/chat.html`
- `src/ui/static/css/style.css`
- `src/ui/static/js/chat.js`
- `src/ui/routers/memory.py`（新增 `/api/memory/files/status`，修复 `GatewayClient` 导入）

### 7. 会话自动总结 (`src/core/summarizer.py`)

- `SessionSummarizer` 读取会话历史，屏蔽 system/工具结果
- 调用主模型提取 `[preference]`、`[decision]`、`[fact]`、`[project_structure]` 条目
- 自动保存到 `MemoryStore`，标签 `auto_summary`

### 7. CLI 输出样式优化

- `src/cli/chat_command.py` 的 `_stream_turn` 使用 `rich.live.Live` 实时渲染 Markdown
- **不再用 Panel 包裹 Live 内容**，避免面板边框在快速增量输出时堆叠/闪烁
- `vertical_overflow="visible"` 防止内容过长时被截断或滚动异常
- 助手回复使用 Markdown 实时渲染，代码块自动高亮
- 协作计划、权限请求、审查结果以独立面板/事件形式展示
- **思考与工具执行动态提示**：
  - 模型开始生成前显示 `🧠 思考中 ⠋ (0.0s)`，并随时间累加秒数
  - 检测到 `read_file` / `write_file` / `run_command` 等工具调用后，Live 区域切换为 `🛠️ 正在调用工具 ⠋ (X.Xs)`，避免把整段代码直接吐在命令行
- **工具调用结果以 Update/Read/Run/Search 行展示**，仿 Claude Code 风格：
  ```
  🔧 工具调用
  ✅ Update(G:\MAO_test\login.html)  287 行
  ✅ Read(G:\MAO_test\index.html)
  ```
- **权限模式颜色区分**：
  - `auto`：红色（危险/自动执行）
  - `approve`：黄色（需要确认）
  - `readonly`：绿色（只读安全）
  - 底部工具栏、命令提示符、模式切换提示、权限批准提示均按模式着色
- **权限请求只展示关键数据**：路径、命令、内容字符数，不再展开代码预览
- 文件列表、工具调用、Token 成本分区显示
- **底部显示本次使用的模型**：单轮回复显示主模型，协作流程显示主模型 + 参与协作的 Worker 模型
- **修复模型“只说不做”**：在 `src/core/agent.py` 的 `TOOL_INSTRUCTIONS` 中明确要求，当助手说要“查看/读取/探查”文件时，必须在同一轮输出 `read_file` / `search_project_files` 工具调用，不能只回复文字
- **修复读完文件后对话中断**：在 `Agent.run_turn()` / `run_turn_stream()` 的工具循环中，每次拿到工具结果后会追加提示“请继续完成用户请求”；即使达到 `max_tool_iterations`，也会再调用一次模型让其基于已有信息直接完成请求，而不是直接结束。默认 `max_tool_iterations` 从 `5` 上调到 `8`
- **修复流式 token 为 0 的问题**：在 `src/gateway/provider.py` 中，若上游流式接口没有返回 usage 或返回全 0，会用字符数做兜底估算，避免 footer 显示 `0 / 0 / $0.000000`
- **对话中切换权限模式**：
  - `/mode` 无参数时循环切换：`approve → readonly → auto → approve`
  - 新增快捷命令：`/auto`、`/approve`、`/readonly`
  - 权限询问时输入 `auto` / `always` / `a` 可立即切换到自动模式并批准当前请求

---

## 如何测试

### 单元测试

```bash
python -m pytest -q
```

当前通过数：**215 passed**。

新增测试文件：

- `tests/test_memory.py`
- `tests/test_memory_tools.py`
- `tests/test_agent_memory.py`
- `tests/test_memory_router.py`
- `tests/test_summarizer.py`

### CLI 手动验证

1. 进入对话：

```bash
python run.py chat
```

2. 添加记忆并验证注入：

```
/memory add preference 用中文回复
/new
你好
```

观察系统提示中是否包含“用中文回复”。

3. 索引项目并搜索文件：

```
/memory index
/search_project_files SessionStore
```

（实际通过工具调用触发，可直接问 Agent：“项目中 SessionStore 在哪里？”）

4. 总结当前会话：

```
/memory summarize
/memory list
```

### Web API 手动验证

启动 UI：

```bash
python scripts/run_ui.py
```

或直接用 `curl`：

```bash
# 添加记忆
curl -X POST http://127.0.0.1:8000/api/memory/entries \
  -H "Content-Type: application/json" \
  -d '{"category": "preference", "content": "用中文回复"}'

# 搜索记忆
curl -X POST http://127.0.0.1:8000/api/memory/search \
  -H "Content-Type: application/json" \
  -d '{"query": "中文"}'

# 重建索引
curl -X POST http://127.0.0.1:8000/api/memory/index \
  -H "Content-Type: application/json" \
  -d '{"root_dir": ".", "force": true}'

# 搜索项目文件
curl -X POST http://127.0.0.1:8000/api/memory/files/search \
  -H "Content-Type: application/json" \
  -d '{"query": "SessionStore"}'

# 总结指定会话
curl -X POST http://127.0.0.1:8000/api/memory/summarize/<session_id>
```

---

## 注意事项

- 未引入向量库/新依赖，检索基于简单关键词倒排索引。
- `MemoryStore.storage_dir` 已解析为绝对路径，避免运行时 `chdir` 导致写错位置。
- 项目文件索引会自动排除 `memory.yaml` 和记忆存储目录。
- UI 侧边栏已实现：在 `/chat` 页面右侧展示当前会话、长期记忆、项目索引、本轮工具/文件记录。

---

## 验证与清理

Phase 5 收尾时已完成端到端真实验证：

- 启动 `python -m src.ui.app` 后，Web `/chat` 页面可正常加载右侧边栏。
- 通过 UI 添加/删除/搜索记忆、重建项目索引、总结当前会话均正常。
- 流式 SSE 对话中，工具调用与已写入文件会记录到“本轮记录”区域。
- CLI `python run.py chat` 的权限模式颜色、思考/工具动画、Markdown 渲染正常。
- 全量回归测试：`python -m pytest -q` 通过 **215 passed**。

清理工作：

- 删除了 `sessions/` 下的历史测试会话文件。
- 删除了 `config/memory/` 下的测试索引与记忆缓存。
- 删除了 `.pytest_cache` 与所有 `__pycache__` 目录。
- `output/` 目录已清空保留。

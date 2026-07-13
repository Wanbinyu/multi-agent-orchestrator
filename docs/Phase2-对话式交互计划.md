# Phase 2：对话式交互改造记录

**状态**：已完成（2026-07-12）

## 目标回顾

把 `python run.py "需求"` 的单次命令模式，升级为可持续多轮对话的交互方式：

1. 会话（Session）抽象并持久化。
2. Agent 工具循环：模型 → 工具执行 → 模型，最多 5 轮。
3. CLI REPL：`python run.py chat`。
4. Web 对话页：`/chat`。

## 已实现模块

| 文件 | 职责 |
|---|---|
| `src/core/session.py` | `Session` 数据模型 + `SessionStore`（YAML 持久化） |
| `src/core/agent.py` | `Agent.run_turn()`，工具解析与循环调用 |
| `src/cli/chat_command.py` | REPL 与 `/new`、`/load`、`/save`、`/plan`、`/tools`、`/exit` 命令 |
| `src/ui/routers/chat.py` | Web 对话 API（会话增删改查、发送消息） |
| `src/ui/templates/chat.html` | 对话页面 HTML |
| `src/ui/static/js/chat.js` | 前端会话列表、消息渲染、发送消息 |
| `src/ui/static/css/style.css` | 追加聊天消息气泡、工具标签、输入区等样式 |
| `src/ui/templates/index.html` | 顶部导航增加“对话”入口 |
| `tests/test_session.py` | 会话存储单元测试 |
| `tests/test_agent.py` | Agent 工具循环单元测试 |
| `tests/test_chat_router.py` | Web 路由单元测试 |

## 关键设计

### 会话模型

```python
class Session(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[ChatMessage]
    output_dir: str
    config_dir: str = "config"
```

- 存储位置：`sessions/<session_id>.yaml`
- 每个会话独立输出目录：`sessions/<session_id>/output/`
- 新增消息时自动更新 `updated_at`

### Agent 工具循环

1. 把用户输入追加为 `user` 消息。
2. 调用 `GatewayClient.chat_with_main_model()`。
3. 若回复包含 ` ```tool:name ... ``` ` 代码块，则调用 `worker_tools.execute_tool_call()`。
4. 把工具结果以 `user` 消息追加，再次调用主模型。
5. 最多循环 `max_tool_iterations`（默认 5）次。
6. 最终回复通过 `file_tools.write_output_files()` 保存产物；若没代码块则保存 `response.md`。

### CLI REPL

```bash
python run.py chat
```

命令：

- `/new [标题]`
- `/load <session_id>`
- `/save`
- `/plan <需求>`：复用 `Orchestrator` + `Dispatcher` 执行一次性任务。
- `/tools`
- `/exit`

### Web 对话

- `GET /chat`：渲染对话页。
- `GET /api/chat/sessions`：会话列表。
- `POST /api/chat/sessions`：创建会话。
- `GET /api/chat/sessions/{id}`：获取会话详情与消息。
- `POST /api/chat/sessions/{id}/messages`：发送消息，返回 `AgentTurnResult`。
- `DELETE /api/chat/sessions/{id}`：删除会话。

通信采用同步整轮返回，Phase 2 不引入 SSE/流式。

## 已确认决策

| 问题 | 决策 |
|---|---|
| 对话入口 | CLI 优先实现，完成后立刻扩展 Web 页面。 |
| 主模型自动调用其他模型 | Phase 2 不做；用户可用 `/plan` 触发一次性多模型任务。 |
| 会话输出目录 | `sessions/<session_id>/output/` |
| 流式输出 | Phase 2 不做，后续视需求决定是否引入 SSE。 |

## 验证结果

```bash
python -m pytest -q
# 153 passed
```

## 使用方式

```bash
# CLI 对话
python run.py chat

# Web 对话
python scripts/run_ui.py
# 浏览器打开 http://127.0.0.1:8000/chat
```

## 后续可扩展

- 流式回复（SSE / WebSocket）。
- 对话消息中的代码块语法高亮。
- `/plan` 结果直接注入当前会话上下文。
- 多模型协作 Agent（自动拆分子任务并调度）。

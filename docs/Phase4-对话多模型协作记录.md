# Phase 4：对话中的多模型自动协作记录

**完成时间**：2026-07-12

**目标**：在持续对话 `/chat` 中，让主模型自动判断请求复杂度，并在需要时调用多个 Worker 模型协作完成，最后把整合结果返回给用户。

---

## 核心流程

```
用户输入
  ↓
Agent.run_turn_stream()
  ├─ _should_collaborate(user_input) 让主模型判断是否需要协作
  │     └─ false → 走原有单模型流式工具循环
  │     └─ true  → _run_collaboration_stream()
  ↓
_run_collaboration_stream()
  ├─ Orchestrator.plan()      → yield plan
  ├─ Dispatcher.dispatch()    → yield task_start / task_complete
  ├─ Reviewer.review()        → yield review_complete
  └─ 汇总成本与文件           → yield done
```

---

## 关键实现

### 1. 自动判断

- 文件：`src/core/agent.py`
- 方法：`Agent._should_collaborate()`
- 实现：使用独立判断 prompt，要求主模型输出 JSON `{"collaborate": true/false}`。
- 失败时保守回退到单模型路径。

### 2. 复用现有流水线

- `Orchestrator.plan()` 拆分任务
- `Dispatcher.dispatch()` 并发调度
- `Worker.execute()` 执行子任务
- `Reviewer.review()` 整合结果

为了让前端/CLI 能看到进度：

- `Worker.execute()` 与 `Dispatcher.dispatch()` 增加可选 `progress_callback` 参数。
- 回调事件：`task_start`、`task_complete`。
- 不破坏原有非回调路径的 `print` 行为。

### 3. 异步事件透传

`Dispatcher` 在后台线程运行，回调通过 `asyncio.run_coroutine_threadsafe(queue.put(...))` 把事件推到 `asyncio.Queue`，`Agent` 的 async generator 从 Queue 中取出并 yield。

### 4. 数据模型扩展

文件：`src/models/schemas.py`

`ChatStreamEvent` 新增事件类型与 payload：

- `plan`：协作计划摘要与子任务列表
- `task_start` / `task_complete`：任务状态、模型、文件
- `review_complete`：审查通过状态、问题、最终输出

### 5. 前端展示

文件：`src/ui/static/js/chat.js`、`src/ui/static/css/style.css`

- 新增可折叠的“多模型协作”面板。
- 显示计划摘要、任务列表与状态、审查结果。
- 最终答案正常渲染在消息气泡中。

### 6. CLI 支持

文件：`src/cli/chat_command.py`

- `_stream_turn()` 解析 `plan`、`task_start`、`task_complete`、`review_complete` 事件。
- 终端打印协作进度与最终答案。

---

## 测试

新增测试文件：

- `tests/test_agent_collaboration.py`：Agent 协作分支单元测试（判断、事件流、失败处理、成本计算）。
- `tests/test_dispatcher_callback.py`：Dispatcher `progress_callback` 事件测试。

全量测试结果：

```powershell
cd E:\multi-agent-orchestrator
python -m pytest -q
# 164 passed
```

---

## 使用方式

### Web

```powershell
python scripts/run_ui.py
```

打开 `http://127.0.0.1:8123/chat`，发送复杂需求如：

> 帮我开发一个前后端登录功能，前端 React，后端 FastAPI。

若主模型判断需要协作，会自动展示“多模型协作”折叠面板。

### CLI

```powershell
python run.py chat
> 帮我开发一个前后端登录功能，前端 React，后端 FastAPI
```

终端会依次打印：协作计划、各任务执行状态、审查结果、最终答案。

---

## 风险与后续优化

- **误判**：简单问题可能被判为需要协作。当前通过明确 JSON 输出要求控制，后续可加入关键词启发式或用户开关。
- **成本**：协作判断本身消耗一次主模型调用，但 token 很少（max_tokens=64）。
- **Reviewer 失败**：即使 review 未通过，仍返回 `final_output` 给用户，并在面板中展示问题。
- **后续**：Phase 5 长期记忆可让 Agent 在多次协作中记住项目结构，减少重复拆分。

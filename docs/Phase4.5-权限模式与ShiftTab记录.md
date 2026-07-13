# Phase 4.5：对话权限确认与 Shift+Tab 模式切换

**日期**：2026-07-12

## 背景

在之前的对话模式测试中，用户要求 Agent“帮我写一个前端登录界面”，结果 Agent 只输出了 `response.md`，没有真正写入页面文件。根本原因是：

1. 系统提示对“必须使用 `write_file`”不够强硬。
2. Agent 一旦检测到工具块就会直接执行，缺乏类似 Claude Code 的权限确认。
3. 写入目录被限制在会话输出目录内，但用户未感知到文件实际落盘位置。

因此引入权限模式：用户可在 `auto`（自动执行）、`approve`（需批准）、`readonly`（只读）之间切换。

## 设计

### 权限模式

```python
ApprovalMode = Literal["auto", "approve", "readonly"]
```

- **auto**：检测到 `read_file` / `write_file` / `run_command` 直接执行，保留旧行为。
- **approve**：执行工具前通过 SSE 发送 `permission_request` 事件，暂停流式输出，等待用户批准或拒绝。
- **readonly**：所有工具调用直接拒绝，不产生权限请求。

### 数据流

```
用户输入
  ↓
Agent.run_turn_stream()
  ├─ 主模型生成工具块
  ├─ 解析工具调用
  │     ├─ readonly → 拒绝
  │     ├─ approve  → yield permission_request → 等待 asyncio.Event
  │     └─ auto     → 直接执行
  ↓
CLI/Web 收到 permission_request
  ├─ CLI：终端打印 y/n
  └─ Web：聊天区渲染 Approve/Deny 按钮
  ↓
Agent.respond_to_permission(request_id, approved)
  ├─ approved=True → 执行工具，继续流
  └─ approved=False → 返回拒绝信息，继续流
```

### 关键实现

- `src/core/agent.py`：
  - `_register_permission_request()` 生成 `request_id` 并创建 `asyncio.Event`。
  - `_wait_for_permission()` 暂停工具循环。
  - `respond_to_permission()` 设置结果并触发 Event。
  - `run_turn_stream()` 仅在 `auto` 模式下自动写 `response.md`。
- `src/cli/chat_command.py`：
  - `prompt_toolkit.PromptSession` + `Keys.BackTab` 实现 Shift+Tab 切换。
  - 底部工具栏显示当前模式。
  - `/mode <auto|approve|readonly>` 命令。
- `src/ui/routers/chat.py`：
  - 内存 `active_agents: dict[str, Agent]` 保存当前流式 Agent。
  - `POST /api/chat/sessions/{id}/mode`：更新会话模式。
  - `POST /api/chat/sessions/{id}/permission/{request_id}`：响应权限请求。
- `src/ui/static/js/chat.js` / `chat.html` / `style.css`：
  - 模式指示器、Shift+Tab 切换、权限卡片 UI。

## 验证

```powershell
# CLI
cd E:\multi-agent-orchestrator
python run.py chat
# Shift+Tab 切换模式；输入“帮我写一个 hello.txt”，应出现 y/n 提示

# Web
python scripts/run_ui.py
# 打开 http://127.0.0.1:8000/chat
# 发送“帮我写一个 hello.txt”，聊天区出现权限卡片
```

## 测试

新增 `tests/test_agent_permission.py`：

- `readonly` 拒绝工具调用。
- `approve` 产出权限请求，批准后执行。
- `approve` 拒绝后不执行。
- `auto` 不产生权限请求并自动落盘。
- `approve` 无明确 `write_file` 时不自动写 `response.md`。

全量测试：`169 passed`。

## 遗留与后续

- 多模型协作（Worker 子任务）仍自动执行文件写入，避免一次协作产生大量逐条确认。
- 未来可考虑“协作开始前一次性确认”或“按任务批量确认”。

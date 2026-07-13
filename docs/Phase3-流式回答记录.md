# Phase 3：流式回答改造记录

**状态**：已完成（2026-07-12）

## 目标

让助手回答在 Web 对话页和 CLI REPL 中**逐块流式显示**，减少用户等待感，同时保留原有同步接口与工具循环。

## 关键决策

| 问题 | 决策 |
|---|---|
| 协议 | **Server-Sent Events (SSE)**：单向、轻量、与现有 HTTP 架构兼容。 |
| 入口范围 | **Web + CLI 同时做**：两者共用 `Agent.run_turn_stream()`。 |
| 旧接口 | **保留**：`POST /api/chat/sessions/{id}/messages` 仍返回完整 JSON。 |
| Provider 实现 | Provider SDK 调用保持同步，新增 `chat_stream()` 生成器；Gateway 用 `asyncio.Queue` + 后台线程包装为 async generator。 |
| 工具循环 | 每轮流式输出完整响应后，解析并执行工具，再进入下一轮流式输出；最终 `done` 事件携带完整结果与元数据。 |

## 新增/修改模块

| 文件 | 变更 |
|---|---|
| `src/models/schemas.py` | 新增 `StreamChunk`、`ChatStreamEvent`。 |
| `src/gateway/provider.py` | `BaseProvider.chat_stream()`；Anthropic / OpenAI-compatible 流式实现。 |
| `src/gateway/client.py` | `chat_stream()`、`chat_with_main_model_stream()`、`Billing.record_stream()`；同步生成器转异步包装。 |
| `src/core/agent.py` | `Agent.run_turn_stream()` 异步生成器；工具执行与文件写入使用 `asyncio.to_thread()`。 |
| `src/ui/routers/chat.py` | 新增 `POST /api/chat/sessions/{id}/messages/stream` 返回 `StreamingResponse`。 |
| `src/ui/static/js/chat.js` | `sendMessage()` 改为 SSE 消费；增量渲染 Markdown；`done` 后展示工具/文件。 |
| `src/ui/static/css/style.css` | `.streaming` 脉冲光晕、`.streaming-cursor` 闪烁光标、`.error-text`。 |
| `src/cli/chat_command.py` | REPL 通过 `asyncio.run(_stream_turn(...))` 逐块打印到终端。 |
| `tests/test_agent_stream.py` | Agent 流式单元测试。 |
| `tests/test_chat_router_stream.py` | SSE 路由单元测试。 |

## SSE 事件约定

```text
event: delta
data: {"type":"delta","delta":"逐块文本"}

event: done
data: {"type":"done","assistant_message":"...","tool_calls":[...],"files_written":[...],"input_tokens":10,"output_tokens":5,"cost_usd":0.0001}

event: error
data: {"type":"error","error":"错误信息"}
```

## 验证结果

```bash
python -m pytest -q
# 159 passed
```

## 使用方式

```bash
# CLI 流式对话
python run.py chat

# Web 流式对话
python scripts/run_ui.py
# 浏览器打开 http://127.0.0.1:8123/chat
```

## 已知限制

- OpenAI 兼容服务若在流式响应中不返回 usage，则按 UTF-8 字节数估算 token；成本为近似值。
- 流式中途出错时，已显示的部分不会保存到会话历史（最终 `done` 才会持久化）。
- 工具循环的每一轮必须等完整响应生成后才能判断并执行工具，因此工具块本身也会流式显示给用户。

## 后续可扩展

- 为 CLI 添加 `--no-stream` 参数切换回整段输出。
- 使用 `tiktoken` 或 provider 自带 tokenizer 提高流式 usage 估算精度。
- 在 Web 端支持中止当前流式生成（AbortController）。
- 流式输出时代码块语法高亮（避免高频重渲染）。

# 对标 Claude 差异升级路线

> 基于《MAO 与 Claude Code 对比》中的差距清单，制定分阶段升级计划。
> 对每项差距标注 **可行性**（✅ 可行 / ⚠️ 部分可行 / ❌ 不可行或不建议）及原因，并给出实施顺序。
> 起始时间：2026-07-13。

---

## 一、差距清单与可行性评估

| # | 差距项 | 可行性 | 原因 | 优先级 | 工作量 |
|---|---|---|---|---|---|
| 1 | 自动压缩（auto compaction） | ✅ 可行 | 已有 `SessionSummarizer` 基础，改为"摘要替换旧历史"即可；加 token 计数触发 | P0 | 中 |
| 2 | 上下文窗口感知 | ✅ 可行 | `ModelConfig` 加 `max_context_tokens`，发送前裁剪；各模型保守默认+配置覆盖 | P0 | 小 |
| 3 | token 精确计数 | ✅ 可行 | 可选 `tiktoken`，无则字符估算（已有字节估算兜底） | P0 | 小 |
| 4 | Edit 局部编辑工具 | ✅ 可行 | 纯本地工具，`edit_file(path, old, new)` 注册进 registry | P1 | 小 |
| 5 | Glob/Grep 增强工具 | ✅ 可行 | `glob_files`/`grep_content`，标准库 `fnmatch`/`re` 或 `subprocess rg` | P1 | 小 |
| 6 | 后台任务 / Monitor / 通知 | ✅ 可行 | `subprocess.Popen` 不等待；流式监控；系统通知 | P2 | 中 |
| 7 | 原生工具调用（部分模型） | ⚠️ 部分可行 | Anthropic/OpenAI SDK 支持原生 tool_use，但需重构消息历史；国产模型 function calling 不稳，必须保留 Markdown 兜底 | P2 | 大 |
| 8 | MCP 适配器 | ✅ 可行 | MCP 有 Python SDK，适配器把 MCP 工具注册进 `ToolRegistry` | P2 | 中 |
| 9 | Hooks（工具调用前后拦截） | ✅ 可行 | 在 `ToolRegistry.execute` 前后加钩子，配置化 | P3 | 小 |
| 10 | 子 Agent 并行抽象 | ✅ 可行 | 复用 Dispatcher 做"临时派生子任务"，不经过完整 Orchestrator 拆分 | P3 | 中 |
| 11 | 达到 Claude 200K/1M 上下文 | ❌ 不可行 | 受接入模型硬限制：国产模型窗口多 32K-128K；MAO 无法改变模型本身，只有接 Claude 才享 200K | — | — |
| 12 | 所有模型统一原生 tool_use | ❌ 不可行 | 部分国产模型 function calling 不稳定或不支持，必须保留 Markdown 块兜底 | — | — |
| 13 | 默认开启完整 shell（去白名单） | ❌ 不建议 | 违背 MAO 安全保守定位，风险高；只能作为 opt-in 的 `unsafe` 工具 | — | — |
| 14 | 复制 Claude 官方托管/分发 | ❌ 不可行 | MAO 是自研项目，无 Anthropic 官方资源与生态；属定位差异非功能差距 | — | — |

---

## 二、不可行 / 不建议项详细说明

### ❌ #11 达到 Claude 200K/1M 上下文
- **原因**：上下文窗口是模型层硬限制。MAO 接入的 GLM / Kimi / DeepSeek / Qwen 等国产模型窗口普遍 32K-128K，MAO 作为客户端无法突破。
- **替代方案**：通过 #1 自动压缩 + #2 窗口感知，在有限窗口内实现"长任务可持续"，等效缓解而非突破上限。若接入 Claude 模型则自然享有 200K。

### ❌ #12 所有模型统一原生 tool_use
- **原因**：MAO 的核心价值是多厂商接入。部分国产模型 function calling 支持差或不稳定（参数丢失、格式漂移）。强制全原生会导致这些模型不可用。
- **替代方案**：#7 对**声明了 tool_use 能力且验证稳定**的模型走原生，其余保留 Markdown 块兜底，双轨并存。

### ❌ #13 默认开启完整 shell
- **原因**：MAO 当前 `run_command` 用白名单前缀 + `shell=False`，是刻意的安全设计。默认放开等于把"任意命令执行"暴露给 LLM，与 `readonly`/`approve` 的安全语义冲突。
- **替代方案**：作为 `category="unsafe"` 的 opt-in 工具，仅在显式配置 + `auto` 模式下启用，`approve` 模式逐条确认。

### ❌ #14 复制 Claude 官方托管/分发
- **原因**：MAO 是本地自研项目，无官方分发渠道与托管服务。这是定位差异（自托管 vs 官方托管），不应作为功能目标。

---

## 三、分阶段实施计划

按"先解决生存性短板，再补工具，最后扩生态"的顺序。每个阶段独立可交付、可测试。

### Phase 6.1 — 上下文生存能力（P0，最高优先）
**目标**：让长会话不再撞上下文上限报错。

- token 计数（#3）：`src/core/token_counter.py`，可选 tiktoken，无则字符估算。
- 上下文窗口感知（#2）：`ModelConfig` 加 `max_context_tokens`，默认保守值；`config/providers.yaml` 可覆盖。
- 自动压缩（#1）：`src/core/compactor.py`，在 `Agent.run_turn` 前检查消息总 token，超阈值时：
  - 保留 system + 最近 N 轮；
  - 对旧消息调用 summarizer 生成摘要；
  - 用摘要消息替换旧历史（真正压缩，而非仅写记忆）。
- 触发阈值：默认 75% 窗口；可配置。
- 测试：`tests/test_compactor.py`、`tests/test_token_counter.py`。

**验收**：构造超长会话，自动压缩后续接不中断；`pytest` 全绿。

### Phase 6.2 — 工具增强（P1）
**目标**：补齐高频工具，减少整文件重写。

- `edit_file`（#4）：`old_string`/`new_string` 精确替换，校验唯一性。
- `glob_files`（#5）：模式匹配列出文件。
- `grep_content`（#5）：正则搜索文件内容（优先 `rg`，无则 Python `re`）。
- 测试：`tests/test_edit_file.py`、`tests/test_search_tools.py`。

**验收**：Agent 能局部编辑大文件、按模式找文件、按内容搜代码。

### Phase 6.3 — 原生工具调用（P2，部分模型）
**目标**：对稳定支持 tool_use 的模型走原生结构化调用。

- `ModelConfig.capabilities` 已有 `tool_use` 标签；provider 检测后走原生 `tools` API。
- 重构 Agent 消息历史：原生 `tool_use`/`tool_result` 角色支持。
- 保留 Markdown 块作为不支持模型的兜底。
- 测试：mock 原生 tool_use 流程。

**验收**：Claude/GLM 等支持 tool_use 的模型走原生；其余模型行为不变。

### Phase 6.4 — 扩展生态（P2/P3）
**目标**：接入外部工具与可扩展机制。

- MCP 适配器（#8）：`src/tools/mcp_adapter.py`，把 MCP server 工具注册进 `ToolRegistry`；`config/mcp.yaml` 配置 server 列表。
- Hooks（#9）：`src/core/hooks.py`，`ToolRegistry.execute` 前后钩子；`pre_tool`/`post_tool` 配置。
- 测试：mock MCP server；hook 触发验证。

**验收**：能挂载一个 MCP server 并调用其工具；hook 能拦截/记录工具调用。

### Phase 6.5 — 子 Agent 并行抽象（P3）
**目标**：单 Agent 内临时派生并行子任务，不依赖完整协作流水线。

- `spawn_subagent` 工具或 Agent 内置方法：复用 `Dispatcher` 单任务执行，并行多任务。
- 结果合并回主对话。
- 测试：并行子任务执行与合并。

**验收**：Agent 可在单轮内派生并行子任务并合并结果。

---

## 四、不在计划内（明确放弃）

- ❌ 突破模型上下文上限（#11）—— 模型层硬限制。
- ❌ 全模型原生 tool_use（#12）—— 多厂商兼容性。
- ❌ 默认完整 shell（#13）—— 安全定位。
- ❌ 官方托管/分发（#14）—— 定位差异。

---

## 五、实施状态

| 阶段 | 状态 | 备注 |
|---|---|---|
| Phase 6.0 工具注册表 + 网页工具 | ✅ 已完成 | 237 passed |
| Phase 6.1 上下文生存能力 | ✅ 已完成 | 自动压缩 + 窗口感知 + token 计数；250 passed |
| Phase 6.2 工具增强 | ✅ 已完成 | edit_file/glob_files/grep_content；265 passed |
| 本地 LLM + 扩展点 | ✅ 已完成 | Ollama/llama.cpp provider + ToolSource(MCP槽位)；284 passed |
| Phase 6.3 原生工具调用 | ✅ 已完成 | tools= 透传 + schema 生成 + native_tools 开关；297 passed；开发者工具指南 + contrib 目录 |
| Phase 6.4 扩展生态 | ✅ 已完成 | Hooks（pre/post 拦截）+ MCP 适配器（stdio/sse）+ 启动加载器；329 passed |
| Phase 6.5 子 Agent 并行 | ⏳ 计划中 | 复用 Dispatcher；SubagentSpawner 槽位已预留 |

---

*本计划随实施进度滚动更新。每阶段完成后回归 `python -m pytest -q` 全绿方可推进下一阶段。*

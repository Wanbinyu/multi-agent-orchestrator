# v0.1.0-beta.4 执行清单

**状态**：进行中，B4.1-B4.2 已完成，B4.3 进行中

**目标**：工程透明度、会话恢复与长任务上下文——用户无需询问模型，就能看懂任务计划、执行证据、验证结果、阻塞原因和上下文行为

**规划基线提交**：`cf36fad`（`v0.1.0-beta.3` 发布后）

**基线测试**：`558 passed, 1 warning`

## 0. 开始前检查

- [x] `git status --short --branch` 干净。
- [x] 阅读：`docs/版本计划-v0.1.0-beta.3至beta.6.md`（2026-07-17 修订版）、`docs/项目进度与关键操作.md`。
- [x] 确认 beta.4 新范围：干扰度指标、L0/L1/L2 分层、Reviewer 信息限制验证已写入版本计划。
- [ ] 未获得所有者确认前，不执行真实付费模型调用；离线基准一律使用固定转录文本。

## 1. B4.1 工程记录可视化

### 目标

CLI 与 Web 无需调用模型即可展开查看 WorkPlan、Evidence、VerificationGate、RequirementCheck、CompletionAudit 和 residual_risks。

### 主要文件

- `src/ui/static/js/chat.js`
- `src/ui/static/css/style.css`
- `src/cli/chat_command.py`
- `tests/test_ui.py`、`tests/test_run_cli.py`

### 任务

- [x] Web 工程记录条目增加"详情"展开：计划步骤（含状态）、证据列表、验证门、需求核对、完成审计、残余风险和指标；数据来自已有 `GET /api/chat/sessions/{id}/runs/{run_id}`，点击时才加载。
- [x] 默认折叠保持界面简洁；长列表（证据/验证门）有界显示并标注总数。
- [x] 390px 移动视口展开后无横向溢出（响应式 CSS：`overflow-wrap: anywhere`，无固定宽度；真机视觉验收待人工 smoke）。
- [x] CLI 新增 `/runs [run_id]`：无参数列出本会话最近运行，带参数展示该运行的完整工程记录；纯本地读取，不调用模型。

### 验收

- [x] 展开的字段与 RunJournal 持久化内容一致，证据条数与摘要行一致。
- [x] `node --check` 与 UI 契约测试通过；CLI 新命令有帮助与补全。

### B4.1 完成记录（2026-07-17）

- Web：`chat.js` 工程记录条目新增"展开详情/收起详情"按钮，点击时经 `/api/chat/sessions/{id}/runs/{run_id}` 懒加载完整记录；详情按目标、分类与边界、工作计划、证据、验证门、需求核对、完成审计、决策、修改文件、残余风险和指标分区渲染；证据/验证门/决策最多显示 50 条并在标题标注总数；运行状态变化后缓存自动失效，下次展开重新加载。
- CLI：新增 `/runs [run_id]`，列出最近 10 条运行或展示单条完整工程记录；纯本地读取 RunJournal YAML，不调用模型；帮助与补全由 `SLASH_COMMANDS` 统一生成。
- 测试：`test_chat_runs_command.py` 新增 4 个用例（列表、完整详情、缺失 run、空会话）；`test_chat_router.py` 扩展详情端点契约，锁定前端消费的 11 个顶级字段。
- 验证：`python -m pytest -q` 为 `562 passed, 1 warning`；`compileall`、`node --check` 和 `git diff --check` 通过。
- 剩余风险：390px 视口只实现了响应式规则，未在真实移动视口做视觉验收。

## 2. B4.2 压缩事件与上下文透明度

### 目标

上下文占用、压缩次数、预算来源、估算误差和最近压缩事件在 CLI/Web 可见。

### 主要文件

- `src/core/compactor.py`
- `src/core/agent.py`（`get_context_status`）
- `src/core/session.py`
- `tests/test_compactor*.py`、`tests/test_agent*.py`

### 任务

- [x] 压缩事件持久化（时间、前后 token 估算、丢弃消息数、使用层级），有界保存在会话侧。
- [x] `get_context_status` 暴露压缩次数与最近事件；Provider 返回 usage 时记录估算 vs 实际 prompt token 误差（有界）。
- [x] CLI `/context` 与 Web context 端点展示上述字段。

### 验收

- [x] 触发一次压缩后事件记录与消息数变化一致；事件不写入会话消息流。
- [x] 无压缩时界面无新增噪音。

### B4.2 完成记录（2026-07-17）

- `Session` 新增 `compaction_events` 与 `usage_observations`（各有界 20 条），旧会话 YAML 无此字段时按默认空表加载。
- Agent 在每次实际压缩时记录时间、前后 token 估算、合并消息数和层级（当前为 `summary`，B4.4 分层后扩展）；事件只进会话观测字段，不写入消息流。
- `StreamChunk` 新增 `usage_estimated`：Anthropic/OpenAI/llama.cpp 的兜底估算置为 True，真实 Provider usage 保持 False；同步 3 处、流式 3 处在收到真实 usage 时记录估算 vs 实际 prompt token，同一请求只记一次。
- `get_context_status` 暴露 `compaction_count`、`recent_compactions`（最近 3 条）和 `usage_observations`（最近 3 条，含 `error_pct`）。
- CLI `/context` 仅在存在压缩或观测时追加对应行；Web 上下文面板新增"压缩"与"估算误差"两行，无数据时隐藏（悬停显示估算/实际值）。
- 测试：`test_context_observability.py` 新增 8 个用例（有界性、旧会话兼容、压缩事件、真实 usage 观测、StreamChunk 默认值、状态暴露、无噪音）。
- 验证：`python -m pytest -q` 为 `570 passed, 1 warning`；`compileall`、`node --check` 和 `git diff --check` 通过。
- 剩余风险：估算误差依赖 Provider 返回真实 usage；本地模型（llama.cpp）的 input usage 为 0 时不产生观测。

## 3. B4.3 会话恢复确认

### 目标

加载会话时识别 `running`、`blocked` 和未完成计划，用户显式确认后才继续。

### 主要文件

- `src/cli/chat_command.py`（`/load`）
- `src/ui/routers/chat.py`（会话详情端点）
- `src/ui/static/js/chat.js`
- `tests/test_session_recovery.py`（新增）

### 任务

- [ ] 检测中断会话：最新 RunJournal 为 `running`/`blocked`，或计划存在未完成步骤。
- [ ] CLI `/load` 与 Web 打开会话时显示恢复横幅（状态、阻塞原因、未完成步骤数）。
- [ ] 用户确认后才继续；确认/放弃决策写入 RunJournal `decisions`。
- [ ] 恢复绝不自动重放已完成任务或重复写入。

### 验收

- [ ] 中断夹具下 CLI/Web 均出现提示且默认不继续执行。
- [ ] 确认后续跑时，已完成步骤的写入文件不重复生成。

## 4. B4.4 Context 3 分层压缩

### 目标

实现去重、局部摘要、旧回合摘要和任务检查点的分层压缩，压缩质量可测量。

### 主要文件

- `src/core/compactor.py`
- `src/core/summarizer.py`
- `src/core/context_budget.py`
- `tests/test_compaction_layers.py`（新增）、`scripts/bench_compaction.py`（新增）

### 任务

- [ ] L0/L1/L2 分层：L0 索引/占位（单行引用）、L1 结构化摘要、L2 近期全文；摘要保留会话输出文件与 run_id 引用，需要时可经工具按需展开。
- [ ] 压缩前去重：重复工具结果与文件读取只保留一份。
- [ ] 摘要 Schema：需求、决策、证据、修改文件、待办、风险；解析失败回退现有纯文本行为并记录。
- [ ] 质量门：Schema 校验 + 关键实体（需求关键词、文件名）保留率；结果写入压缩事件。
- [ ] 干扰度指标：压缩后任务相关 token 占比（目标与 files_changed 实体覆盖率），定义可离线回放。
- [ ] 任务检查点在压缩中保持固定，不被摘要吸收。

### 验收

- [ ] 连续三次压缩后仍保留核心需求、文件变更和证据引用（固定转录离线回放）。
- [ ] 32K/64K/128K/200K 四档窗口基准通过约定门槛，干扰度可测量、可回放。
- [ ] 摘要 Schema 不合法时回退安全且不留孤立工具块。

## 5. B4.5 项目索引增量复用

### 目标

项目树、文件摘要和内容哈希索引增量复用，重复侦察零重读。

### 主要文件

- `src/core/memory.py`（或新 `src/core/project_index.py`）
- `src/tools/`（`project_tree`、`search_project_files`）
- `tests/test_project_index.py`（新增）

### 任务

- [ ] 项目树 + 文件摘要 + 内容哈希索引持久化到项目本地缓存。
- [ ] 增量刷新：仅哈希变化的文件重新读取；结构变化局部更新。
- [ ] 侦察与检索优先命中索引；缓存读取不重复计证据（保持既有规则）。

### 验收

- [ ] 未变更项目二次侦察读取数为零；单文件变更只重读该文件。
- [ ] 索引损坏时回退全量扫描且不阻塞对话。

## 6. B4.6 Reviewer 信息限制验证

### 目标

Reviewer 对照需求与证据独立验证，不阅读 Worker 自述。

### 主要文件

- `src/core/reviewer.py`
- `src/core/collaboration.py`
- `tests/test_reviewer.py`

### 任务

- [ ] 新增受限验证模式：输入为原始需求、计划、证据、验证门和写入文件清单，排除 Worker 输出正文。
- [ ] 验证模式写入 RunJournal；配置可切回完整模式。
- [ ] 确定性审计约束保持不变（Reviewer 输出不能覆盖审计）。

### 验收

- [ ] 受限模式 prompt 不含 Worker 正文（契约测试）。
- [ ] RunJournal 记录验证模式；两种模式均通过现有评审回归。

## 7. B4.7 发布收口

- [ ] 更新 `CHANGELOG.md`、版本号 `0.1.0b4`、`RELEASE_NOTES_v0.1.0-beta.4.md`。
- [ ] 全量测试、compileall、JavaScript 语法、diff hygiene、pip-audit、gitleaks 通过。
- [ ] 构建 wheel/sdist 并 `twine check`；空目录隔离安装与 `/health` 通过。
- [ ] 远端 Windows/Ubuntu CI 通过。
- [ ] 所有者单独确认后才创建 Tag 和 GitHub pre-release。

## 8. 推荐提交边界

1. `feat: expand engineering run details in CLI and Web`
2. `feat: expose compaction events and context estimates`
3. `feat: confirm interrupted session recovery`
4. `feat: layer context compaction with quality gates`
5. `feat: reuse incremental project index`
6. `feat: restrict reviewer verification inputs`
7. `docs: prepare beta.4 release`

每个提交必须独立通过针对性测试，不等到最后一次性修复所有回归。

## 9. 当前下一步

B4.1（工程记录可视化）与 B4.2（压缩事件与上下文透明度）已完成，`570 passed`。执行 **B4.3 会话恢复确认**：检测 `running`/`blocked` 运行与未完成计划，CLI `/load` 与 Web 打开会话时显示恢复横幅，用户显式确认后才继续，决策写入 RunJournal。

## 10. 使用反馈修复记录（2026-07-17）

beta.3 真实使用中暴露的连锁问题：relay（聚合转发）对新目录模型 ID `kimi-k2.7-code` 返回空响应；空响应被误判为 `completed`；句中"帮我先做/把……搭建好"被分类为 `unclassified` 进入只读。已修复：

- **空响应守卫补洞**（`fix: fail silent empty model responses`）：无可解析文本且无工具调用时，有 token（任意轮）或首轮零 token 均按 `failed` 处理并给出可操作提示（检查 Provider 连接与模型 ID）；工具轮之后的零 token 空响应保持原有收尾行为。空 assistant 消息不再写入会话历史。回归：`test_empty_response_guard.py` 4 例。
- **分类器句中形式**（`fix: recognize mid-sentence build phrasing`）：`_EXPLICIT_WRITE_PATTERNS` 新增"帮我……做一个/套/份"和"把……搭建好/做出来"模式；排除"帮我看看怎么做""做版本对比""把搭建的事告诉我"等只读问法。回归：`test_task_intent_classifier.py` 8 例。
- **Kimi K3 加入目录**（`feat: add kimi k3 to model catalog`）：模型 ID `kimi-k3`，1M 上下文；元数据来自 2026-07-16 发布报道，`metadata_source="unverified"`、`context_window_source="unverified_press_2026-07"`，等待官方文档逐项核实。
- 遗留：用户本地 relay（`api.va11.icu`）是否支持 `kimi-k3`/`kimi-k2.7-code` 需用户与 relay 提供方确认；MAO 目录按官方 moonshot.cn 模型 ID 维护。全量回归 `582 passed, 1 warning`。

# v0.1.0-beta.4 执行清单

**状态**：已完成；2026-07-19 发布 `v0.1.0-beta.4` pre-release

**目标**：工程透明度、会话恢复与长任务上下文——用户无需询问模型，就能看懂任务计划、执行证据、验证结果、阻塞原因和上下文行为

**规划基线提交**：`cf36fad`（`v0.1.0-beta.3` 发布后）

**基线测试**：`558 passed, 1 warning`；当前工作树最新全量结果见本文末完成记录

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

## 2.5 B4.S 真实任务稳定性前置（当前）

### 目标

根据 `sessions/20260718-070404-246880-770695` 的真实前端任务，把“生成很多文件”收口为“正确分类、多模型执行、首轮可运行、自动验证和报告可信”。完整证据、操作流程和六个实现切片见 [`真实任务稳定性改进计划.md`](真实任务稳定性改进计划.md)。

### 当前问题

- [x] “给我做一个纯前端项目”已稳定分类为 `build/high/deep`，具备 Plan/协作资格。
- [x] `unclassified` 实际写入项目文件后动态提升有效类型与审计深度，不再 `audit: not_required`。
- [x] 缺页、错误路由目标和相对 import 现在由 B4.S3 确定性闭包门拦截；真实脱敏夹具回放留到 B4.S6。
- [x] 错误 Mock、登录失败、空数据、控制台错误与移动布局问题现在由 B4.S4 真实浏览器门稳定拦截。
- [x] 结构化 cwd、跨平台命令、闭包检查和运行时 smoke 已完成；真实任务整链回放留到 B4.S6。
- [x] 全部 RunJournal 现在可聚合创建/修改/验证/风险和 190,289/69,121 等真实 token 数据，不再依赖压缩消息重建。

### 执行顺序

- [x] B4.S1：意图分类与 observed mutation 动态风险/审计升级。
- [x] B4.S2：带 cwd 的可移植验证执行器和脚本发现。
- [x] B4.S3：高风险前端项目的多模型任务合同和 import/route 闭包。
- [x] B4.S4：登录、主要路由、数据、控制台和 390px 的浏览器 smoke。
- [x] B4.S5：基于全部 RunJournal 的真实报告与 token 指标。
- [x] B4.S6：智慧矿区脱敏夹具回放和发布门。

### 验收

- [x] 真实原句进入 `build/high`，Plan/协作策略可见。
- [x] 任意实际项目写入都不能以 `audit: not_required` 完成，Session 根 `response.md` 排除。
- [x] 固定前端夹具首轮构建、命令门和浏览器 smoke 通过。
- [x] 错误 Mock 与缺页/错误 import 失败变体稳定 blocked；缺失脚本依赖由 S2 继续覆盖。
- [x] 最终总结完整覆盖创建、修复、验证、失败、token/成本与剩余风险。

### B4.S6 完成记录（2026-07-18）

- `tests/fixtures/smart_mining/` 是公开脱敏固定样例；`StabilityReplayRunner` 离线串联分类、四职责多模型合同、闭包、真实 npm 命令、Playwright、完成审计和本地报告，Provider 调用数为 0。
- 正常样例 `completed` 且四级验证门全过；错误 Mock 和缺失路由样例均 `blocked`，首轮可运行率为 0。
- Windows `npm.CMD` 只在直接执行触发 `FileNotFoundError` 后通过 `shutil.which` 解析，仍保持 `shell=False`。
- CI 已加入 `python scripts/replay_smart_mining.py`。全量回归 `683 passed, 1 warning`；`compileall`、JavaScript 语法和 diff hygiene 通过。

## 3. B4.3 会话恢复确认

### 目标

加载会话时识别 `running`、`blocked` 和未完成计划，用户显式确认后才继续。

### 主要文件

- `src/cli/chat_command.py`（`/load`）
- `src/ui/routers/chat.py`（会话详情端点）
- `src/ui/static/js/chat.js`
- `tests/test_session_recovery.py`（新增）

### 任务

- [x] 检测中断会话：最新 RunJournal 为 `running`/`blocked`，或计划存在未完成步骤。
- [x] CLI `/load` 与 Web 打开会话时显示恢复横幅（状态、阻塞原因、未完成步骤数）。
- [x] 用户确认后才继续；确认/放弃决策写入 RunJournal `decisions`。
- [x] 恢复绝不自动重放已完成任务或重复写入。

### 验收

- [x] 中断夹具下 CLI/Web 均出现提示且默认不继续执行。
- [x] 确认后只创建新 run 并领取未完成步骤检查点；已完成步骤和既有文件只作为禁止自动重放的证据。

### B4.3 完成记录（2026-07-18）

- 新增 `SessionRecoveryManager`：只检查最新 RunJournal，`running`、`blocked` 或任何未完成计划进入待确认状态；旧 Session 无恢复字段时按默认空历史兼容。
- CLI `/load` 显示状态、原因和未完成步骤；新增 `/resume continue|abandon`。Web 会话详情返回同一恢复状态，横幅在确认前禁用输入与发送，同步/流式消息端点均以 409 硬阻断。
- 继续/放弃本身只写本地 Session 与 RunJournal decision，不调用 Provider、不执行工具。中断的 running run 被封存为 blocked；放弃只阻断未完成步骤，不回滚完成步骤或既有文件。
- 继续后的第一条消息创建新 run，领取一次性恢复检查点；检查点明确列出完成/未完成步骤和既有文件，系统提示禁止自动重放，RunJournal `metrics.recovery` 可审计。
- 测试：恢复、CLI、Web、Agent 和相邻回归 `77 passed, 1 warning`；全量 `689 passed, 1 warning`。真实浏览器在 1280×720 与 390×844 下无横向溢出，确认前控件禁用、确认后恢复，console error 为 0。

## 4. B4.4 Context 3 分层压缩

### 目标

实现去重、局部摘要、旧回合摘要和任务检查点的分层压缩，压缩质量可测量。

### 主要文件

- `src/core/compactor.py`
- `src/core/summarizer.py`
- `src/core/context_budget.py`
- `tests/test_compaction_layers.py`（新增）、`scripts/bench_compaction.py`（新增）

### 任务

- [x] L0/L1/L2 分层：L0 索引/占位（单行引用）、L1 结构化摘要、L2 近期全文；摘要保留会话输出文件与 run_id 引用，需要时可经工具按需展开。
- [x] 压缩前去重：重复纯文本工具结果与文件读取只保留一份；结构化工具块不做危险去重。
- [x] 摘要 Schema：需求、决策、证据、修改文件、待办、风险；解析失败回退现有纯文本行为并记录。
- [x] 质量门：Schema 校验 + 关键实体（需求标记、文件名、run_id）保留率；结果写入压缩事件。
- [x] 干扰度指标：压缩后任务相关 token 占比与实体覆盖率，支持离线回放。
- [x] 任务检查点在压缩中保持固定，不被摘要吸收。

### 验收

- [x] 连续三次压缩后仍保留核心需求、文件变更和证据引用（固定转录离线回放）。
- [x] 32K/64K/128K/200K 四档窗口基准通过约定门槛，干扰度可测量、可回放。
- [x] 摘要 Schema 不合法时回退安全且不留孤立工具块。

### B4.4 完成记录（2026-07-18）

- `ContextCompactor` 现将历史稳定收口为单一 L0 旧摘要索引、单一 L1 摘要和 L2 最近全文。L1 用内容哈希持久化到 `output/context/compaction-*.json`；L0 保存 artifact、文件和 run_id 引用，可通过既有读取工具按需展开。
- L1 Schema 固定覆盖 requirements、decisions、evidence、files_changed、todos、risks、run_refs 和 output_files。JSON/Schema 非法时保留模型原纯文本并标记 fallback；摘要调用失败或为空时完全保留旧消息。
- 压缩前只对无 content blocks/provider payload 的同角色同正文消息去重。原生 tool_use/tool_result 继续按配对边界切分，不对结构化块做可能破坏协议的去重。
- 从直接历史提取 `KEEP:` 需求、文件路径和 run_id；摘要遗漏时确定性补回。事件记录 Schema 状态、回退原因、实体保留率、相关 token 比例、去重数、artifact 和 checkpoint 数。
- Agent 从当前 RunJournal 自动生成有界 `[MAO_TASK_CHECKPOINT]` JSON，包含 objective、run_id、未完成/已完成步骤、证据、文件和风险；每轮压缩替换旧 checkpoint，不交给摘要吸收。
- `scripts/bench_compaction.py` 在 32K/64K/128K/200K 四档分别执行三次压缩。全部 Provider 调用为 0、关键事实保留率 1.0、最终层级 L0/L1/L2；最终任务相关 token 比例为 0.002339–0.003694。目标回归 `52 passed`，全量 `695 passed, 1 warning`。

## 5. B4.5 项目索引增量复用

### 目标

项目树、文件摘要和内容哈希索引增量复用，重复侦察零重读。

### 主要文件

- `src/core/memory.py`（或新 `src/core/project_index.py`）
- `src/tools/`（`project_tree`、`search_project_files`）
- `tests/test_project_index.py`（新增）

### 任务

- [x] 项目树 + 文件摘要 + 内容哈希索引持久化到本地缓存。
- [x] 增量刷新：快速元数据未变零内容读取；元数据变化时按内容 hash 决定是否重建摘要，结构变化局部更新。
- [x] 侦察与检索优先命中索引；缓存读取通过既有 cached 规则不重复扩大侦察证据。

### 验收

- [x] 未变更项目二次侦察读取数为零；单文件变更只重读该文件。
- [x] 索引损坏时回退全量扫描且不阻塞对话。

### B4.5 完成记录（2026-07-18）

- `FileIndex` 升级为 v2：记录规范化项目根、完整目录/树路径、各文本文件 mtime、size、SHA-256、符号、摘要、snippet 和最近刷新统计；旧 v1 索引因缺 root/hash 会安全重建。
- 未变 mtime+size+hash 的条目直接复用，内容读取数为 0；元数据变化只读该文件，hash 未变则只更新元数据，hash 变化才重建符号/摘要。新增、删除、根切换和强制刷新分别计数。
- 索引 YAML 使用临时文件原子替换。读取损坏 YAML 时标记 `cache_recovered` 并全量刷新；单文件读取失败保留可用旧条目并计入 errors，不阻断对话。
- `project_tree` 默认先增量刷新并从缓存目录树渲染；显式显示隐藏文件时回退实时扫描。`search_project_files` 每次廉价刷新并新增 `path` 项目根参数，防止会话输出目录或另一项目的索引串用。
- 工具结果通过 `metadata.cached` 将跨轮零读取命中传入 Agent/Worker 既有缓存证据规则。Web 索引状态新增 root 和 last_refresh；CLI 显示实际读取/复用数。
- 验收覆盖二次 `read=0`、单文件 `read=1`、hash 相同的元数据更新、删除、损坏恢复、项目根切换和树/搜索缓存。目标与相邻回归 `141 passed, 1 warning`，全量 `701 passed, 1 warning`。

## 6. B4.6 Reviewer 信息限制验证

### 目标

Reviewer 对照需求与证据独立验证，不阅读 Worker 自述。

### 主要文件

- `src/core/reviewer.py`
- `src/core/collaboration.py`
- `tests/test_reviewer.py`

### 任务

- [x] 新增受限验证模式：输入为原始需求、计划、证据、验证门和写入文件清单，排除 Worker 输出正文。
- [x] 验证模式写入 RunJournal；配置可切回完整模式。
- [x] 确定性审计约束保持不变（Reviewer 输出不能覆盖审计）。

### 验收

- [x] 受限模式 prompt 不含 Worker 正文（契约测试）。
- [x] RunJournal 记录验证模式；两种模式均通过现有评审回归。

### B4.6 完成记录（2026-07-18）

- Reviewer 新增 `input_mode: restricted|full`，示例配置默认 restricted；无字段和非法字段均保守回退 restricted，旧私有配置兼容。
- restricted prompt 保留原始需求、TaskPlan/前端合同、职责/模型/状态、文件清单、确定性 acceptance evidence、真实命令证据，以及 RunJournal Evidence、VerificationGate、RequirementCheck 和 CompletionAudit；不拼接 `TaskResult.content` 或 `response.content`。
- full 模式仅供明确需要整合 Worker 正文的工作流，保留原行为。两种 prompt 都显式标记实际模式。
- RunJournal `metrics.collaboration.reviewer_input_mode` 和 reviewer role 条目记录实际模式。Reviewer 即使返回 passed，失败 Worker 或 `audit.can_complete=false` 仍确定性改为未通过。
- 哨兵契约验证 restricted prompt 不含 Worker 正文但含文件、命令和直接证据，full prompt 可见正文。目标与相邻回归 `88 passed`，阶段全量 `703 passed, 1 warning`。

## 7. B4.7 发布收口

- [x] 更新 `CHANGELOG.md`、版本号 `0.1.0b4`、`RELEASE_NOTES_v0.1.0-beta.4.md`。
- [x] 全量测试、compileall、JavaScript 语法、diff hygiene、pip-audit、gitleaks 通过。
- [x] 构建 wheel/sdist 并 `twine check`；空目录隔离安装与 `/health` 通过。
- [x] 远端 Windows/Ubuntu CI 通过。
- [x] 所有者确认后创建 Tag 和 GitHub pre-release。

### B4.7 本地完成记录（2026-07-18，2026-07-19 发布前复审）

- 版本已提升为 `0.1.0b4`；`python run.py --version` 输出 `MAO 0.1.0b4`。
- 完整测试集合为 `722 passed, 1 warning`；受当前执行宿主单命令约 30 秒限制，本地按核心 `705`、真实浏览器 `12`、稳定性回放 `4+1` 三组运行，测试收集总数与三组合计均为 722。唯一 warning 是 Starlette/httpx 的上游弃用提示；远端 CI 仍执行单次完整 pytest。
- `scripts/replay_smart_mining.py` 通过：正常夹具 completed，损坏 Mock 与缺失路由夹具 blocked，Provider 调用为 0。
- `scripts/bench_compaction.py` 通过：32K/64K/128K/200K 各三次压缩，标记关键事实保留率均为 1.0，Provider 调用为 0。
- `scripts/verify_distribution.py` 通过：wheel/sdist 内容合同、`twine check`、不继承系统包的干净虚拟环境依赖安装、空目录 CLI 和 Web `/health` 均通过。
- `pip-audit -r requirements.txt` 未发现已知漏洞。gitleaks 8.24.3 官方 SHA-256 校验通过；60 个历史提交、当前 tracked diff 以及新增源码/脚本/测试/文档/权限示例均未发现泄露。
- Python compileall、JavaScript 语法和 `git diff --check` 已通过；版本与文档收口后的最终快速复验也已通过。
- 首轮远端 CI 在 Ubuntu 暴露路径分隔符断言差异，在 Windows 3.12 暴露系统浏览器冷启动超时；`c0caecb` 统一诊断路径、固定安装 Chromium 并放宽公开回放的动作超时。
- 修复后的 [CI 29672684859](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29672684859) 在 Windows/Ubuntu、Python 3.11/3.12 和 security job 全部通过。

### 发布前差异复审修复（2026-07-19）

- 权限确认只接受当前待处理 request ID，并在完成/取消后清理，避免长会话泄漏和未知 ID 污染。
- 恢复管理器会把“run 已完成但计划未完成”的矛盾记录收口为 blocked；原生 tool-use block 中的路径进入压缩实体保留，纯文本 fallback 使用 `.txt` artifact。
- Reviewer 严格校验 JSON 字段类型并在失败路径保留真实 usage；协作计划最多 24 个子任务，防止模型输出造成无界 Provider 扇出。
- 前端闭包拒绝非法 dependency 结构和越出项目根的 HTML 资源；smoke 拒绝 404 就绪、缺失视口、无原因失败和解释器内联 server 代码。
- 离线回放任一确定性前置门失败时保持 blocked；今日报告不再跨会话套用 Provider 已配置事实。
- Web 拒绝同一会话并发消息和活跃删除，模式切换同步持久 Session；失败的前端乐观切换会回滚显示。
- 发行验收改为不继承系统包的真实干净安装；CI 下载 gitleaks 后先校验官方 SHA-256 再执行扫描。

## 8. 推荐提交边界

1. `feat: complete beta.4 engineering stability contracts`（代码、配置、脚本和测试作为一个可运行边界，避免 Agent/Journal/工具合同被拆断）
2. `docs: prepare beta.4 release candidate`（README、CHANGELOG、架构、计划、验证和 Release Notes）

每个提交必须独立通过针对性测试，不等到最后一次性修复所有回归。

## 9. 当前下一步

B4.1-B4.7、Grok Build 基础行为契约、上游吸收首切片和 B4.S1-B4.S6 均已完成并发布。下一步进入 [`Beta5-执行清单.md`](Beta5-执行清单.md) 的 B5.1：先建立可复现基准合同和离线 harness，不先写未经数据验证的路由策略。

## 10. 使用反馈修复记录（2026-07-17 至 2026-07-18）

beta.3 真实使用中暴露的连锁问题：relay（聚合转发）对新目录模型 ID `kimi-k2.7-code` 返回空响应；空响应被误判为 `completed`；句中"帮我先做/把……搭建好"被分类为 `unclassified` 进入只读。已修复：

- **空响应守卫补洞**（`fix: fail silent empty model responses`）：无可解析文本且无工具调用时，有 token（任意轮）或首轮零 token 均按 `failed` 处理并给出可操作提示（检查 Provider 连接与模型 ID）；工具轮之后的零 token 空响应保持原有收尾行为。空 assistant 消息不再写入会话历史。回归：`test_empty_response_guard.py` 4 例。
- **分类器句中形式**（`fix: recognize mid-sentence build phrasing`）：`_EXPLICIT_WRITE_PATTERNS` 新增"帮我……做一个/套/份"和"把……搭建好/做出来"模式；排除"帮我看看怎么做""做版本对比""把搭建的事告诉我"等只读问法。回归：`test_task_intent_classifier.py` 8 例。
- **Kimi K3 加入目录**（`feat: add kimi k3 to model catalog`）：模型 ID `kimi-k3`，1M 上下文；元数据来自 2026-07-16 发布报道，`metadata_source="unverified"`、`context_window_source="unverified_press_2026-07"`，等待官方文档逐项核实。
- **权限模式解耦**：真实使用中 `[auto] > 帮我创建好` 被第二层 `unclassified` 保守策略隐藏了写工具。现在 `auto` 可直接执行非只读工具，`approve` 只对非只读工具询问，`readonly` 自动读取但拒绝写入/命令；明确不修改的任务仍保持只读。未知任务通过 `permission_follows_session` 跟随会话权限，但不会被当成工程修改触发错误的验证门；“帮我创建好”直接识别为 `build`。同步非流式 `approve` 因无法交互等待，仍安全拒绝非只读调用并提示改用流式 CLI/Web。
- 遗留：用户本地 relay（`api.va11.icu`）是否支持 `kimi-k3`/`kimi-k2.7-code` 需用户与 relay 提供方确认；MAO 目录按官方 moonshot.cn 模型 ID 维护。全量回归 `589 passed, 1 warning`。

## 11. Grok Build 基础行为契约前置（2026-07-18）

- 项目规则：层级发现 `AGENTS.md`、`CLAUDE.md`、`.mao/rules` 及 Grok/Claude/Cursor 兼容目录；20 文件、8K/文件、32K 总量上限；来源与诊断进入 RunJournal；同一规则包传给 Agent/Orchestrator/Worker/Reviewer。
- 权限规则：新增 `deny > ask > allow > 会话默认` 引擎和 `config/permissions.yaml.example`；规范化 Windows 路径，复合命令逐段覆盖，复杂 shell 降级询问；Agent 与 Worker 共用执行边界。
- Plan 模式：Session 持久化 `inactive/pending/active/awaiting_approval` 和方案 artifact；批准前禁止写入、命令、MCP 写操作、写入型 Worker 和自动 response 文件。
- 多模型 Council：主 Agent 真实只读侦察后，由 reconnaissance/architect/critic/synthesizer 四角色无工具评议；单角色失败保留草案并记录诊断。
- CLI/Web：CLI 新增 `/plan enter/show/revise/approve/cancel`，旧 `/plan <需求>` 保持兼容；Web 增加 Plan 状态带与同等 API/控件，批准后自动交回正常多模型执行链。
- 浏览器验收：1280×720 与 390×844 无横向溢出，Plan 状态带不覆盖输入区，控制台无错误；修复 pending 状态提前显示修订/批准按钮的问题。
- 验证：`python -m pytest -q` 为 `615 passed, 1 warning`；`compileall`、`node --check`、`git diff --check` 通过；精确 Key 片段扫描无结果；未调用真实付费模型。
- 详细契约、未照搬风险和后续 Skills/Plugins/Hooks 路线见 [`Grok-Build行为契约融合.md`](Grok-Build行为契约融合.md)。

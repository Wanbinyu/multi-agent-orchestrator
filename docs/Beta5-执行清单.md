# v0.1.0-beta.5 执行清单

**状态**：B5.1-B5.3 已完成；B5.4 离线基础设施已完成、真实评测暂停；B5.5 对抗测试与本地模型路由合同已完成

**目标**：用公开、可复现的数据说明何时单模型更合适，何时多模型协作能提高完成率或降低成本，再把结论固化为有界、可解释、可回退的路由策略。

**发布基线**：`v0.1.0-beta.4`

## 0. 执行原则

- 先建立测量合同，再修改路由行为；不能用路由实现反向定义成功指标。
- 默认基准必须离线、脱敏、零 Provider 调用；真实付费对比需要所有者单独确认模型、次数和费用上限。
- 单模型与 MAO 使用同一任务输入、工作区快照、验证门和完成判定。
- 公开数据不得包含公开编码基准原题、私有项目、密钥或不可再分发内容。
- 每次只推进一个切片；失败结果和“多模型没有优势”的结果同样保留。

## 1. B5.1 可复现基准合同与离线 harness

- [x] 定义任务 Schema：类别、输入、夹具、允许修改、验证命令、成功条件、风险和来源。
- [x] 覆盖问答、诊断、小修改、构建、审查和迁移六类最小任务。
- [x] 定义结果 Schema：输入/输出 token、估算成本、工具调用数、耗时、完成率、误修改率和验证通过率。
- [x] 单模型与 MAO 共用同一 runner、隔离工作区和确定性验收器。
- [x] 默认 fixture 策略使 CI 零费用运行，并验证重复执行不会污染下一轮结果。
- [x] 输出机器可读 JSON 和简洁 Markdown 报告，保留任务、运行和证据 provenance。

### B5.1 完成门

- [x] 同一夹具连续运行至少三次，成功判定与指标字段稳定。
- [x] 失败、超时、无输出和越界修改均进入失败结果，不被平均值掩盖。
- [x] harness 不读取真实 Key，不调用付费 Provider，不依赖开发机绝对路径。
- [ ] Windows/Ubuntu、Python 3.11/3.12 CI 通过（本地完成，等待提交后远端 CI）。

### B5.1 完成记录（2026-07-19）

- `src/core/engineering/benchmark.py` 新增版本化任务/结果 Schema、策略协议、隔离工作区、确定性验收、重复签名、聚合指标及 JSON/Markdown 报告。
- `benchmarks/engineering_v1/` 提供六类程序化脱敏任务；验证命令限制在项目内白名单可执行文件，拒绝绝对路径、父目录、解释器内联代码和符号链接夹具。
- `fixture-single` 与 `fixture-mao` 通过同一 harness 运行三次，共 36 个结果：全部通过、签名稳定、误修改率 0、Provider 调用 0。数据明确标记为 `synthetic_contract`，不能用于宣传真实模型优势。
- wheel 包含 benchmark 核心模块；sdist 包含公开 suite、运行脚本和六个任务项目。`twine check` 与发行 archive contract 通过，源码包可直接复现离线基准。
- 失败合同覆盖越界修改、空响应、超时、Provider 调用泄漏、不稳定指标、非法路径和不安全命令；针对性测试 `13 passed`。
- 扩大回归按宿主时限拆分为核心 `718`、真实浏览器 `12`、稳定性回放 `5`，合计 `735 passed, 1 warning`。唯一 warning 仍为 Starlette/httpx 上游弃用提示。
- CI 新增 `Offline engineering benchmark gate`；远端矩阵结果只能在提交推送后记录。

## 2. B5.2 执行深度合同

- [x] 定义 `fast`、`standard`、`deep` 的工具、Worker、Reviewer、上下文和验证预算。
- [x] 简单任务默认不启动 Worker；高风险任务不能用 `fast` 绕过确定性验证。
- [x] 用户显式选择优先于自动建议，实际深度与原因写入 RunJournal。

### B5.2 完成记录（2026-07-19）

- `ExecutionDepthDecision` 同时保存用户请求、自动建议、实际深度、来源、理由和预算；RunJournal 升级为 v4，旧记录仍可加载。
- `fast` 限 3 个主 Agent 工具轮次、50% 上下文预算且禁用 Worker；`standard` 限 6 轮、75% 上下文、2 个 Worker；`deep` 限 8 轮、完整上下文、4 个 Worker。发生协作时 `standard/deep` 都必须进入 Reviewer。
- CLI 新增 `/depth auto|fast|standard|deep`，Web 提供同一会话偏好 API；Web 工程记录显示请求、建议、实际深度和预算。
- 显式选择优先于自动建议；小修改可用 `fast` 降低工具和 Worker 开销，但仍保留原任务的 `standard` 验证门。高风险与 `deep` 合同构成不可降低的安全下限，真实多文件、依赖或新目录写入会重新评估并提升到 `deep`，不扩大原工具权限。
- 执行深度已约束上下文压缩阈值、主 Agent/Worker 工具轮次、Worker 并发和变更验证下限。完整测试 `749 passed, 1 warning`；B5 工程 benchmark 36/36 稳定、智慧矿区正反回放、JavaScript/Python 语法、差异格式和分发验收全部通过，Provider 调用 0。唯一 warning 为 Starlette/httpx 上游弃用提示。

## 3. B5.3 可解释模型路由

- [x] 路由输入只使用任务类型、能力真值、价格、上下文、健康状态和用户约束。
- [x] 未验证能力不得作为自动升级依据；价格未知时不得宣称节省成本。
- [x] 路由失败回退到用户指定模型，并限制重试和升级次数。
- [x] CLI/Web 显示简洁原因，完整决策进入 RunJournal。

### B5.3 完成记录（2026-07-19）

- `ModelRouter.route()` 在 Provider 调用前确定性评估任务类型、执行深度、显式能力状态、价格来源、安全上下文预算、健康冷却、本地模型和用户约束；运行时 failover 仍是独立层，不能反向改写路由理由。
- 自动路由最多选择一个候选模型。只有 `supported` 能力可触发升级；旧 `capabilities` 列表在元数据来源未验证时仍按 `unverified` 处理。价格来源未知时 `price_comparison=unknown`、`savings_claim_allowed=false`，不得输出节省声明。
- 会话默认 `auto`；CLI `/routing fixed` 和 Web 会话 API 可锁定用户主模型。自动候选发生可切换故障时，Gateway 优先回退到用户主模型，再遵循既有 failover 合同；认证和非法请求等致命错误仍不会盲目换模型。
- RunJournal 升级为 v5：事件摘要只展示选择模型、来源和简洁理由，完整记录保留候选资格、能力状态、上下文、健康、价格、评分和淘汰理由。CLI/Web 均显示实际模型和原因。
- 完整测试 `763 passed, 1 warning`；B5 benchmark 36/36 稳定、智慧矿区正反回放、JavaScript/Python 语法、差异格式和分发验收全部通过，Provider 调用 0。唯一 warning 为 Starlette/httpx 上游弃用提示。

## 4. B5.4 单模型与多模型对比

- [x] **阶段启动提醒**：已向项目所有者说明“现在开始测试 MAO 的真实能力”；确认模型、次数、费用上限和可公开范围前不调用真实 Provider。
- [x] 同一 harness 已建立固定单模型、自动路由和多模型协作的独立控制变量，离线 54 条合成结果通过。
- [ ] 经授权后在同一 harness 上运行三种真实策略。
- [ ] 至少产出一个公开 token/成本优势案例。
- [ ] 至少产出一个多模型完成率优势案例，或明确记录不应使用多模型的任务类型。
- [x] 报告 Schema 独立记录模型集合、路由、执行深度和协作策略，合成数据明确标记 `synthetic_contract`。
- [x] 完成 `mao benchmark-agent` 无交互入口和 Harbor `BaseInstalledAgent` adapter，记录轨迹、token、成本、模型和工程审计。
- [ ] 授权后先跑一个串行 Terminal-Bench/Harbor 任务，检查 verifier、误修改和重复稳定性后再扩大。
- [ ] B5.4 稳定后再评估 SWE-bench Lite/Verified；Aider Polyglot 只作为代码编辑补充，不作为 MAO 综合 Agent 能力结论。

### 外部评测边界

- 目前没有可信的“一键上传 MAO 自动综合评分”服务；标准流程是适配 Agent 接口，在 Docker/隔离环境运行任务集并提交轨迹和结果。
- 官方入口：Terminal-Bench <https://www.tbench.ai/>、Harbor 运行说明 <https://harborframework.com/docs/running-tbench>、SWE-bench <https://www.swebench.com/>、Aider Leaderboard <https://aider.chat/docs/leaderboards/>。
- Terminal-Bench adapter 不打断 B5.2-B5.3；未确认费用前只完成适配器、离线合同和少量 mock/fixture 验证，不调用付费 Provider。

### B5.4 离线基础设施记录（2026-07-19）

- 三种 profile 在 6 类任务上各运行 3 次，共 54/54 条合成结果通过，稳定性签名一致，Provider 调用 0。
- `mao benchmark-agent` 经单元测试验证使用生产 Agent 流、受限工作区、新 Session、策略约束和机器可读结果。
- 当前完整回归 `787 passed, 1 warning`；wheel/sdist、`twine check`、干净安装、CLI 和 Web health 分发验收通过。唯一 warning 仍为 Starlette/httpx 上游弃用提示。
- Harbor adapter 已对齐官方 `0.20.x` `BaseInstalledAgent` 源码合同；当前开发机只有 Python 3.11，Harbor `0.20.x` 要求 3.12，因此真实 import/Docker 运行仍是授权后首个 smoke 的验收项。

### B5.4 首轮真实 smoke 记录（2026-07-19，private）

- 策略为 `glm-ark` 固定单模型、`glm-ark + kimi-for-coding` 自动路由/多模型；任务为公开程序化 `build-health-module`，串行、各一次。
- 首次执行发现 live-smoke 脚本没有像 `mao` 入口一样加载 `.env`，3 个策略在认证阶段失败，token/成本为 0。已补上 `.env` 加载、失败尝试计数和 fail-fast。
- `fixed-single` 外部 verifier 通过：3 次 Provider 调用，输入/输出 `2857/431`，成本 `$0.003288`，越界修改 0。MAO 内部仍标记 `blocked`，因为公开小夹具的 verifier 没有满足高风险 build 全套工程验证门。
- `auto-route` 两轮都只使用 `glm-ark`，符合“未验证能力不自动升级”合同；但发现 `project_tree` 的默认索引将 `config/memory/file_index.yaml` 写入被测工作区，因越界修改被 harness 正确拒绝。
- 索引存储已改为由 Agent/Worker 通过工具运行上下文注入评测 state 目录，相关离线回归通过；尚待下一次真实 smoke 确认。
- 所有者将累计 Provider 尝试上限从 20 提高到 35，结果继续保持 `private`，费用上限保持 `$0.20`。
- `auto-route` 在索引重定向后通过外部 verifier，实际模型仍只有 `glm-ark`，符合未验证能力不自动升级的保守合同。
- `multi-model` 依次暴露并修复：顶层任务数组解析、模型输出角色别名、列表型验收标准，以及软件任务误用创作 Worker。相关行为均已加入离线回归。
- 第三轮 `multi-model` 暴露停止门只在整轮结束后汇总的缺陷：本轮授权剩余 8 次但实际产生 13 次，累计达到 **40/35**，累计真实成本 `$0.032453`。发现后已停止全部真实调用。
- 调用门已改为每次 Provider 网络请求前原子预占额度，第 N+1 次会在请求发出前拒绝；并发 Worker 共享同一线程安全上限，网关同时累计成功与失败尝试。该修复已通过 mock/离线测试，但因授权已耗尽，未再做真实 Provider 复验。
- 当前 `multi-model` 仍未验收：最近报告 `bench-fb6c0b3bf4d0` 只实际使用 `glm-ark`，外部 verifier 未通过；不得据此声明双模型效果。

## 5. B5.5 实验能力

- [x] 对抗式测试 Worker 仅在实验档启用，尝试推翻实现结果并记录证据。
- [x] 本地/Ollama 模型可作为零边际成本候选，但健康检查和能力门不降低。
- [ ] 扩充模型目录时继续保持官方来源、`unverified` 回退和 CLI/Web 单一真值。

### B5.5 完成记录（2026-07-20）

- Session 新增默认关闭的 `adversarial_testing`。只有用户显式启用、实际执行深度为 `deep`、意图为 `change/build`、协作 Worker 全部成功且确定性完成审计已通过时，才运行只读 `AdversarialTester`；确定性审计已阻断时直接跳过，避免浪费 token。
- 对抗角色只接收原始需求、计划、文件/验收信息、真实命令证据和验证门，不接收 Worker 自述正文，也没有工具或写入权限。输出执行严格 JSON 解析、字段类型检查和长度/条数上限，异常或无效输出降级为 `inconclusive`。
- `refuted` 只能把原完成结论降级为 `blocked`，不能把失败结果升级；`inconclusive` 只记录剩余风险。结论、建议检查、模型/用量和 Evidence 写入 RunJournal，建议检查明确标记为“未执行”。
- CLI 新增 `/adversarial on|off`，Web 新增会话级实验开关和 `adversarial_complete` 状态；执行中修改返回 409。开关默认关闭、刷新持久化、320/390/1280px 布局及浏览器控制台无错误均已实测。
- 本地/Ollama 候选在已验证能力、健康、上下文均满足时可由 `fast` 以零估算成本选择；零成本加分不能绕过健康冷却、能力真值或上下文门。`deep build` 需要 reasoning 时，只有 coding 能力的本地模型会被拒绝并选择合格云模型。
- 完整回归 `798 passed, 1 warning`；54/54 离线工程基准稳定、Provider 调用/尝试 0，Python/JavaScript 语法、差异格式和分发验收通过。唯一 warning 仍为 Starlette/httpx 上游弃用提示。

## 6. B5.6 发布收口

- [x] 全量测试、安全扫描、分发验收和干净安装通过。
- [x] 基准任务来源、生成方式、运行命令和结果可公开复现。
- [x] CHANGELOG、Release Notes、版本号和升级说明完成。
- [x] Tag 和 GitHub pre-release 已由所有者确认并创建（`v0.1.0-beta.5` 指向 `6f95f27`）。

### B5.6 完成记录（2026-07-21）

- 模型目录单一真值审计：CLI（`provider_presets.py`、`agent_setup.py`）与 Web（`src/ui/presets/builtin/*`）均经 `BUILTIN_MODELS[alias].to_model_data()` 取值；发现并修复 CLI `ark` Coding Plan 预设硬编码 `glm-ark` 漂离 catalog 的小问题，使其与 Web `ark-coding` 预设和其余预设一致。新增 `test_preset_models_are_sourced_from_catalog` 防漂移回归测试。
- 公开基准可复现性：`benchmarks/engineering_v1/README.md` 与 `suite.yaml` 记录任务来源（`programmatic MAO fixture`）、运行命令（`python scripts/benchmark_engineering.py`）、`data_policy`（无公开原题/私有项目/密钥/Provider 调用）与 `synthetic_contract` 标记；sdist 含全套任务项目与运行脚本。
- 版本号：`src/version.py`、`pyproject.toml`、`tests/test_version.py` 同步升至 `0.1.0b5`；`python run.py --version` 输出 `MAO 0.1.0b5`。
- 文档：CHANGELOG `[Unreleased]` 转为 `[0.1.0-beta.5] - 2026-07-21` 并新增指向 beta.6 的 `[Unreleased]`；新增 `docs/RELEASE_NOTES_v0.1.0-beta.5.md`（Highlights、Install、Upgrade Notes、Verification、Known Limitations）；README 徽章与状态段落更新。
- 验证：全量回归 `799 passed, 1 warning`（唯一 warning 为 Starlette/httpx 上游弃用）；`pip-audit -r requirements.txt` 无已知漏洞；`python -m compileall`、`node --check`（app.js/chat.js）、`git diff --check` 通过；`python scripts/verify_distribution.py` 构建 wheel/sdist、校验归档合同、干净虚拟环境安装、空目录 CLI 与 Web `/health` 通过。
- 安全扫描边界：gitleaks 8.24.3 在本地 Windows 无法下载二进制（auto 模式拒绝外部下载），权威密钥扫描为远端 CI 作业，已在 [run 29829436563](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29829436563) 通过。
- 复核中发现 `cbcf056`（B5.5）远端 CI 实际失败但此前未记录：`build/` gitignore 规则误藏基准 `tasks/build/` 夹具，文件未提交导致 CI 失败而本地测试通过。`737ac8e` 将规则锚定为 `/build/` 并补齐 `tasks/build/project/{README.md,verify.py}` 后修复，远端 CI 全绿（Windows/Ubuntu × Python 3.11/3.12 与 security job）。
- 真实 Provider 调用：无人在场验收期间未调用付费 Provider；此前的 `multi-model` private live smoke 不计入公开发布，也不用于声明任何模型优势。
- Tag 和 GitHub pre-release：已由所有者确认并创建。`v0.1.0-beta.5` 指向 `6f95f27`，GitHub pre-release 使用仓库内 `RELEASE_NOTES_v0.1.0-beta.5.md`。

## 7. 当前下一步

B5.6 发布收口完成，`v0.1.0-beta.5` 已发布（Tag + GitHub pre-release）。下一步进入 `beta.6` Plugin API v0。B5.4 真实 `multi-model` 评测仍单独暂停；只有所有者重新给出新的累计次数边界后，才允许继续 private smoke。详见 [`B5.4-真实能力评测操作手册.md`](B5.4-真实能力评测操作手册.md)。

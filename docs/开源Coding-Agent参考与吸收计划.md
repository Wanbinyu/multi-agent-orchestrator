# 开源 Coding Agent 参考与吸收计划

**审计日期**：2026-07-18

**原则**：MAO 吸收经过验证的行为契约，不按热度堆功能。优先独立实现；只有直接复用明显降低风险时才复制源码，并保留原许可证、版权、NOTICE 和修改说明。

## 1. 候选项目与结论

| 项目 | 审计提交 | 许可证 | 成熟方案 | 对 MAO 的处理 |
|---|---|---|---|---|
| [Grok Build](https://github.com/xai-org/grok-build) | `98c3b2438aa922fbbe6178a5c0a4c48f85edc8ce` | Apache-2.0 | Plan/权限/规则、无头 JSON/JSONL、沙箱、后台任务、验证子 Agent | 基础契约已实现；继续吸收事件协议、验证循环和沙箱配置语义 |
| [Codex](https://github.com/openai/codex) | `5c0e582c59892dbec89af78ae62c784d3da6c9cb` | Apache-2.0 | execpolicy、规则自检样例、结构化审批、JSONL 事件、沙箱 | 当前吸收权限规则自检；后续吸收结构化命令与事件模型 |
| [OpenCode](https://github.com/anomalyco/opencode) | `fab213312927ea64cf968832c527206e8c944f9e` | MIT | Provider 能力层、Agent 预设、权限、压缩、插件与多端 | 已有专项审计；Provider 能力矩阵和系统 Agent 保留在后续路线 |
| [Aider](https://github.com/Aider-AI/aider) | `5dc9490bb35f9729ef2c95d00a19ccd30c26339c` | Apache-2.0 | Repo Map、架构模型/编辑模型分离、编辑后 lint/test | 吸收仓库结构摘要和按变更语言选择验证器，不复制其 Python 实现 |
| [Cline](https://github.com/cline/cline) | `557d725690024b7c12dfad7672c476de74bd1eac` | Apache-2.0 | Shadow Git 检查点、文件/会话分离恢复、分类 Auto Approve | 规划 MAO 检查点；保留权限规则优先级，不采用模型自报命令安全性 |
| [Goose](https://github.com/block/goose) | `8e78960e535ab7f34630e7c5921a42f146cbc9f4` | Apache-2.0 | Recipe、扩展和自动化工作流 | 等 Plugin API v0 稳定后再审，不进入当前稳定性关键路径 |
| [Qwen Code](https://github.com/QwenLM/qwen-code) | `adf2caea3928ed46eb61e97307ad6995dd5678f2` | Apache-2.0 | 多模型 CLI、规则/扩展、无头自动化 | 作为国产模型兼容和 CLI 交互对照，不重复实现已有能力 |

`Roo Code` 在本次审计时仓库已标记 archived，不作为新能力的首选上游。

## 2. 已吸收：权限规则加载期自检

来源行为：Codex execpolicy 的规则可带 `justification`、`match` 和 `not_match`，加载时用示例验证规则语义。MAO 已在 `src/core/permission_rules.py` 中独立实现对应能力：

```yaml
rules:
  - action: allow
    tool: run_command
    pattern: "python -m pytest *"
    justification: "允许项目测试"
    match:
      - "python -m pytest tests"
    not_match:
      - "python -m pip install pytest"
```

- `justification` 成为批准或拒绝的可读理由。
- `match` 中任一未命中的预期样例会让该规则失效。
- `not_match` 中任一错误命中的反例会让该规则失效。
- 失效规则不会进入 Agent/Worker 执行边界，并产生有来源和规则序号的诊断。
- 命令样例沿用 MAO 的复合命令拆分；路径样例沿用工作区规范化和 Windows 大小写规则。

这次只复制行为契约，没有复制 Codex、Grok Build 或其他上游源码。

验收：权限规则针对性测试 `16 passed`；相关 Agent/Worker/Reviewer 回归 `53 passed`；全量测试 `621 passed, 1 warning`。

## 3. 下一批吸收顺序

### U2：结构化命令与验证协议（B4.S2 已完成）

参考 Grok Build 的 `--cwd`、工具过滤和终止元数据，以及 Codex 审批事件中的 `command: string[]`、绝对 `cwd`、理由和可选批准决策。

- `run_command` 使用结构化 `cwd`，禁止通过 `cd &&` 拼接工作区。
- 命令记录包含参数、cwd、退出码、持续时间、截断状态和权限决策。
- 权限拒绝携带规则理由与安全替代方案。
- 不照搬 Grok Build 的 Unix 命令示例；Windows 和 Ubuntu 都必须有测试。

### U3：独立验证循环（并入 B4.S3-B4.S4）

参考 Grok Build `check-work` 的“任务清单 → 重建操作轨迹 → 检查当前状态 → 构建测试 → PASS/FAIL → 最多修复三轮”，并保留 MAO 的确定性 CompletionAudit：

- Reviewer 不读取 Worker 的完成自述，只读取需求、diff、Evidence 和 VerificationGate。
- 首次失败后按问题定位修复；上限三轮，禁止无限自我修复消耗 token。
- 前端任务必须增加浏览器运行时和窄屏 smoke，不能用 TypeScript/Vite 构建代替功能验收。

### U4：稳定的无头 JSON/JSONL 事件（并入 B4.S5）

参考 Grok Build `json/streaming-json` 和 Codex item started/updated/completed 事件：

- `mao run --output-format plain|json|streaming-json`。
- 事件至少覆盖 run、plan、model、tool、file change、command、verification、approval、compaction、usage、error 和 end。
- `end` 必须是最后事件；失败使用非零退出码。
- token 与成本增加 `usage_is_incomplete`、`cost_is_partial`，缺失成本不得展示为零。
- 多模型调用按角色和真实模型分别统计，不能只报主模型。

### U5：任务检查点（B4.S 通过后）

参考 Cline 的 Shadow Git，但先做兼容性验证：

- 检查点仓库必须与用户 Git 分离，不写入用户提交历史。
- 分开支持“恢复文件”“恢复会话”“同时恢复”。
- 记录未跟踪文件，同时明确忽略密钥、构建产物和超大文件。
- 创建或恢复前检查用户已有修改；任何恢复都必须显式确认并预览 diff。
- 大仓库提供关闭、容量上限和清理策略。

MAO 不会自动执行 `git reset --hard` 或覆盖用户修改。

### U6：仓库地图与分层上下文（beta.5）

参考 Aider Repo Map 的符号摘要和依赖排序：

- 优先使用语言解析器/LSP/AST，无法解析时退回文件级索引。
- 按任务、引用关系、最近改动和 token 预算选择结构，不把整个仓库塞进上下文。
- Repo Map 只提供导航证据，不能代替真实文件读取。
- 与 MAO 多模型融合：侦察模型生成候选结构，执行 Worker 只获得其任务需要的切片，Reviewer 获得需求相关 diff 和验证证据。

### U7：OS 级沙箱和后台任务（beta.6 以后）

参考 Grok Build 的 `workspace/read-only/strict` profile、会话固定沙箱和 fail-closed 自定义 deny：

- Windows、Linux、macOS 分别选用真实可验证的隔离后端；不能把路径字符串检查宣传为 OS 沙箱。
- 显式请求的自定义沙箱无法应用时拒绝启动，不能静默降级。
- 沙箱 profile 随 Session 固定；恢复会话不能悄悄扩大权限。
- 后台命令有 task id、状态、增量输出、超时、终止和会话清理；多模型 Worker 共用任务所有权边界。

## 4. 明确不采用

- 不直接复制 Rust/TypeScript 大型模块到 Python 项目，避免双运行时和不可维护的粘合层。
- 不采用“模型自己声明命令是否安全”作为最终权限依据。
- 不在没有签名、权限清单、隔离和撤销机制前建设插件市场。
- 不把 Shadow Git 当作无需确认即可覆盖用户文件的授权。
- 不用更多子 Agent 代替证据、测试和浏览器 smoke。
- 不以 Star 数量决定优先级；只按 MAO 真实失败样本和发布门排序。

## 5. 许可证处理

MAO 当前为 MIT。设计思想和公开行为契约采用独立实现，并在本文记录来源。未来若直接复制代码：

- MIT 代码保留原版权和许可证声明。
- Apache-2.0 代码保留许可证、版权、NOTICE 和显著修改说明；相关文件不能只标 MAO MIT。
- 上游 vendored/third-party 文件按其自身许可证处理，不能仅依据仓库根许可证判断。
- 每次直接复用都要在提交说明和第三方声明中记录上游仓库、提交、文件和修改范围。

## 6. 当前执行入口

B4.S1-B4.S3 与 U2 已完成，U3 已建立多模型前端合同、闭包门和真实命令证据。当前执行 [`真实任务稳定性改进计划.md`](真实任务稳定性改进计划.md) 的 B4.S4 浏览器运行时 smoke；U4 并入 B4.S5，U5-U7 不得插队。

## 7. 主要审计来源

- Grok Build：[Headless](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/14-headless-mode.md)、[Sandbox](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/18-sandbox.md)、[Background tasks](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/20-background-tasks.md)、[Permissions](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/22-permissions-and-safety.md)、[check-work](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-shell/skills/check-work/SKILL.md)。
- Codex：[execpolicy README](https://github.com/openai/codex/blob/main/codex-rs/execpolicy/README.md)、[JSONL event processor](https://github.com/openai/codex/blob/main/codex-rs/exec/src/event_processor_with_jsonl_output.rs)、[approval protocol](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/approvals.rs)。
- Aider：[Repo Map](https://github.com/Aider-AI/aider/blob/main/aider/website/docs/repomap.md)、[Architect mode](https://github.com/Aider-AI/aider/blob/main/aider/website/_posts/2024-09-26-architect.md)、[linter](https://github.com/Aider-AI/aider/blob/main/aider/linter.py)。
- Cline：[Checkpoints](https://github.com/cline/cline/blob/main/docs/core-workflows/checkpoints.mdx)、[Auto Approve](https://github.com/cline/cline/blob/main/docs/features/auto-approve.mdx)、[Permission handling](https://github.com/cline/cline/blob/main/docs/sdk/guides/permission-handling.mdx)。

# Grok Build 行为契约融合

**状态**：基础契约已落地，扩展生态待后续版本

**审计来源**：xAI 官方开源仓库 [`xai-org/grok-build`](https://github.com/xai-org/grok-build)，审计基线 `98c3b2438aa922fbbe6178a5c0a4c48f85edc8ce`，Apache-2.0。参考了配置、Skills、Plugins、Hooks、项目规则、Plan 模式、权限与安全文档；MAO 只吸收行为契约，不复制实现。

## 1. 本轮已实现

### 1.1 项目规则

- 从项目根到目标目录按层级发现 `AGENTS.md`、`Agents.md`、`CLAUDE.md`、`CLAUDE.local.md`。
- 支持 `.mao/rules/*.md`，兼容 `.grok/rules`、`.claude/rules`、`.cursor/rules`。
- 更深目录规则后加载、作用域更具体；Windows 下大小写不敏感去重。
- 单文件 8K、总量 32K、最多 20 文件；截断与读取问题记录诊断。
- 同一规则包注入主 Agent、Orchestrator、Worker、Reviewer；RunJournal 保存来源摘要。
- 项目规则不能覆盖系统安全、明确只读边界、Plan 模式或权限规则。

### 1.2 权限规则

用户级规则放在 `config/permissions.yaml`，项目级规则放在 `<project>/.mao/permissions.yaml`。格式见 `config/permissions.yaml.example`。

```yaml
rules:
  - action: deny
    tool: run_command
    pattern: "rm *"
  - action: ask
    tool: write_file
    pattern: "**/*.py"
  - action: allow
    tool: run_command
    pattern: "python -m pytest *"
```

决策优先级固定为 `deny > ask > allow > 会话模式默认`。`readonly`、明确“不修改/只做方案”和 Plan 模式是硬上限，任何 allow 规则都不能突破。路径先规范化再匹配，Windows 路径统一大小写和分隔符；复合命令拆分 `&&`、`||`、`;`、`|` 和换行，每个片段都被 allow 覆盖才可自动执行。重定向、替换、后台执行等复杂 shell 即使命中 allow 也降级为 ask。

主 Agent 和 Worker 在真实工具执行边界调用同一引擎。协作批量批准只能满足会话默认询问，显式 ask/deny 仍生效，子模型不得自行批准。

权限规则现支持 `justification` 和加载期 `match/not_match` 自检。该增量参考 Codex execpolicy 的可验证规则思想并独立实现；自检失败的规则会被排除并留下诊断。更完整的上游对比见 [`开源Coding-Agent参考与吸收计划.md`](开源Coding-Agent参考与吸收计划.md)。

### 1.3 持久化 Plan 模式

会话状态为 `inactive / pending / active / awaiting_approval`，方案内容、修订意见、版本号和 council 来源写入 Session YAML，重启后恢复。Plan 未批准前：

- 主 Agent 仅暴露和执行只读工具。
- 禁止写命令、MCP 写操作、自动 `response.md` 和写入型 Worker。
- 只允许更新当前会话的 Plan artifact。
- 项目规则和会话 `auto` 都不能放宽边界。

CLI：`/plan enter [目标]`、`/plan show`、`/plan revise <意见>`、`/plan approve`、`/plan cancel`。原 `/plan <需求>` 一次性协作命令保持兼容。Web 提供同等状态控件和 `GET/POST /api/chat/sessions/{id}/plan`。

### 1.4 多模型规划 Council

Plan 草案先由主 Agent 使用真实只读工具侦察，再进入无工具 council：

1. `reconnaissance`：核对证据、约束和未知项。
2. `architect`：形成有边界、可验收的实施方案。
3. `critic`：挑战越权风险、遗漏、依赖、回滚和测试不足。
4. `synthesizer`：主模型综合为唯一最终方案。

四个角色接收同一项目规则、权限摘要和证据边界，不携带工具定义。任一辅助角色失败只记录诊断；综合失败保留主 Agent 草案，不让单个模型故障破坏整个 Plan。

## 2. 明确没有照搬的风险

- 不能只隐藏编辑工具：MAO 在执行边界拦截 shell、MCP 和 Worker。
- 父 Plan 模式必须约束子模型，不能让 Worker 绕过。
- 路径规则不能直接匹配未规范化字符串。
- 权限/安全 Hook 不采用默认 fail-open。
- 当前不建设在线插件市场，先完成信任来源、签名和隔离边界。

## 3. 后续吸收顺序

1. B4.S：先用真实任务修复分类、动态审计、可移植验证和前端 smoke，详见 [`真实任务稳定性改进计划.md`](真实任务稳定性改进计划.md)。
2. B4：增加规则来源查看命令、恢复未完成 Plan、Reviewer 信息限制验证。
3. B5：设置注册表（类型、默认值、实时生效/需重启）、更丰富生命周期 Hooks。
4. B6：Skills/Plugins 的来源、信任、版本和能力声明；Plugin API v0。
5. 插件市场仅在签名、权限清单、隔离运行和撤销机制完成后评估。

## 4. 当前验收

- 项目规则、权限规则、Plan 状态、Council、CLI/Web 控制均有离线测试。
- 浏览器验收覆盖 1280×720 与 390×844：无横向溢出、Plan 状态带不覆盖输入区、控制台无错误。
- 未调用真实付费模型。

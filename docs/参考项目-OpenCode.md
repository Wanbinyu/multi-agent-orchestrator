# 参考项目审计：OpenCode

**审计日期**：2026-07-16

**候选结论**：X 搜索结果和 MAO 早期学习记录都指向 OpenCode；它高度可能是用户曾看到的多模型项目，但没有原帖截图或作者信息，无法百分之百确认。

## 1. 识别线索

X 高相关结果：

- 帖子：<https://x.com/VivekIntel/status/2063350729553936525>
- 描述：开源 Claude Code 替代方案、Terminal UI、Built-in Agents、Desktop App、Multi-Model Support。
- 链接仓库：<https://github.com/anomalyco/opencode>

MAO 早期 Git 历史中也曾有 `OpenCode学习规划.md`，指向同一仓库。该早期文档的 Provider、工具、Agent、权限和 Session 学习目标中，多数已经在 MAO Phase 1-7 中部分实现，因此不恢复为当前计划。

## 2. 是否开源

是。

截至审计时：

- GitHub 仓库公开且未归档。
- 许可证为 MIT。
- 默认分支为 `dev`。
- 主要语言为 TypeScript。
- 约 186,000 Stars、23,000 Forks。
- 最新稳定 Release 为 `v1.18.2`，发布于 2026-07-15。
- 审计源码提交为 `17544802c38a4d35834275526ccf38be1cdcfbf4`。

这些数字是时间点快照，不作为 MAO 的竞争目标。

## 3. 本次抽样看到的能力

### 多模型与 Provider

- Provider 与 Model 分离。
- 针对 Anthropic、OpenAI、xAI、Gemini、OpenRouter、Azure、GitHub Copilot 等维护适配。
- 根据模型能力处理 reasoning、缓存、输出限制、Schema 和 Provider 专属参数。
- 支持模型变体和 Provider 插件。

### Agent 与权限

- 内置 `build`、`plan`、`general`、`explore` 等 Agent。
- 隐藏的 `compaction`、`title`、`summary` Agent 负责系统任务。
- 权限规则使用 `allow / ask / deny`，并支持按工具和路径模式匹配。
- 会话内支持单次批准和持续批准。
- 子 Agent 继承必要的拒绝规则和外部目录边界。

### 会话与上下文

- 持久 Session 运行时。
- 独立的 compaction、overflow、retry、summary 和 run state 模块。
- TUI 显示上下文占比、token 和成本。

### 工具与扩展

- read、write、edit、apply patch、shell、glob、grep、web、LSP、task、skill 等工具。
- MCP、插件、LSP、SDK 和服务端接口。
- Terminal UI、桌面应用、Web、VS Code 扩展和多平台安装渠道。

## 4. 与 MAO 的关系

| 维度 | OpenCode | MAO 当前方向 |
|---|---|---|
| 产品成熟度 | 大型成熟项目，多端和生态完整 | 公开 Beta，聚焦稳定性和工程闭环 |
| 技术栈 | TypeScript、Bun、Effect、大型 monorepo | Python、Typer、FastAPI、轻量前端 |
| 多模型 | 广泛 Provider 与模型特例适配 | 多 Provider、模型映射、故障切换和 Worker 分工 |
| Agent | build/plan/subagent 等角色 | TaskIntent + Orchestrator/Worker/Reviewer |
| 权限 | 工具/路径规则 `allow/ask/deny` | 会话模式 + 任务写入策略 + Worker 路径所有权 |
| 上下文 | 成熟压缩与 TUI 指标 | 动态预算已完成，分层压缩和索引待推进 |
| 成本 | TUI 展示 token 与 cost | Gateway 计费、预算和后续基准 |
| 完成判定 | 本次抽样未发现与 MAO 同名的确定性完成门 | Evidence、VerificationGate、RequirementCheck、CompletionAudit |
| 分发 | 脚本、npm、brew、scoop、choco、桌面安装包 | 当前以 pipx 和源码安装为主 |

“未发现”只表示本次有限源码抽样，没有据此断言 OpenCode 完全不存在同类能力。

## 5. 建议借鉴

### P0：近期直接参考

1. **Provider 能力矩阵**
   - 把协议、工具、流式、视觉、reasoning、上下文、输出限制和验证日期变成结构化数据。
   - 将模型特例收敛到独立 transform/compatibility 层，避免散落在 Agent 中。

2. **权限规则表达**
   - 在现有 `auto/approve/readonly` 上增加按工具、类别和路径的 `allow/ask/deny`。
   - 保留 MAO 的任务写入授权和 Worker `owned_paths`，不以 OpenCode 规则替换现有边界。

3. **上下文和成本状态栏**
   - CLI/Web 同时显示当前模型、上下文占比、token、成本和压缩事件。

4. **安装体验**
   - 参考多平台安装文档和升级路径，但先保证 pipx 稳定，再增加独立安装脚本或二进制。

### P1：核心稳定后参考

- build/plan/explore 等清晰 Agent 预设与切换体验。
- 隐藏系统 Agent 承担标题、摘要和压缩，减少主 Agent 职责。
- Session 并发保护、重试状态和恢复模型。
- Provider 插件和模型变体配置。
- LSP 诊断作为验证证据来源。

### P2：有真实需求再参考

- 桌面应用、IDE 扩展、SDK 和服务端控制平面。
- 多语言文档自动化和更广泛包管理器分发。
- 插件市场或集中式服务。

## 6. 不建议照搬

- 不迁移到 TypeScript/Bun/Effect，只为模仿其内部结构。
- 不复制大型 monorepo、云服务和桌面端全部范围。
- 不为追赶 Provider 数量堆积未经验证的模型特例。
- 不取消 MAO 的 Evidence、VerificationGate、CompletionAudit 和 Worker 路径所有权。
- 不把 OpenCode 的 Star、功能数量或发布频率作为 MAO 的成功指标。

## 7. 许可证边界

MIT 允许使用、修改和分发代码，但复制 OpenCode 的实际代码或较大实现片段时，必须保留其版权和许可证声明。

MAO 当前优先借鉴公开设计思想并独立实现。只有在直接复用能显著降低风险且许可证处理明确时，才引入代码，并在提交和文档中标明来源。

## 8. 对 MAO 路线的影响

OpenCode 证明“多模型 Coding Agent”已有成熟需求，因此 MAO 不能把“支持多个模型”本身当作唯一卖点。MAO 应继续集中在：

- 面向多种现有套餐和国产 Provider 的低门槛接入。
- token、成本和上下文预算控制。
- 确定性证据、验证门和完成审计。
- 有依赖、路径所有权和验收标准的多模型协作。

对应里程碑见 [`MAO-产品方向与Beta路线图.md`](MAO-产品方向与Beta路线图.md)。

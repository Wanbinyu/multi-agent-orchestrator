# MAO 优化与后续开发规划

**状态**：当前执行入口

**更新日期**：2026-07-25

**基线**：`v0.1.0-beta.7`；O1 文档收口与 O2 U4 schema 示例已落地；**O3 Provider 兼容矩阵与安全边界已完成**；真实 Provider 评测仍暂停。
## 1. 目标

在继续增加功能前，先把 MAO 收口为一个可解释、可验证、可维护的 Beta 产品：

- 用户能安装、配置 Provider，并完成一次真实项目任务。
- CLI、Web 和无头接口对同一次运行给出一致的状态、事件和错误语义。
- 工具调用、文件变更、命令、验证和完成判断都有可追溯证据。
- 未实现 OS/容器级沙箱、真实 Provider 对比或外部用户验证时，不对这些能力作过度宣传。
- 新功能必须有明确用户场景、验收标准和回归测试，不能只增加模型角色或配置项。

## 2. 当前基线与明显落后项

### 已完成并应保持稳定

- Provider 配置、模型目录、CLI/Web 对话和多模型 Worker 协作。
- `auto`、`approve`、`readonly` 权限模式，以及 Plan、Evidence、VerificationGate、CompletionAudit 和 RunJournal。
- 上下文预算、压缩、项目侦察、命令验证、前端 smoke、工程 benchmark 和 Plugin API v0。
- U4 `plain`、`json`、`streaming-json` 输出；JSON/JSONL 已覆盖计划、模型、工具、文件变更、命令、验证、审批、usage、错误和结束状态。
- 文档已分为当前入口、使用指南、发布记录和 `docs/archive/` 历史归档。

### 需要优化或重新核实

1. **文档真值来源**：历史 Beta 清单、旧对标和旧稳定性计划不能继续作为当前任务入口；现行状态只维护在文档索引、项目进度、产品路线和本文。
2. **U4 事件边界**：补齐会话压缩、恢复和长任务中断等事件的统一语义，确认 JSON 与 JSONL 的 schema、顺序、退出码和版本兼容策略。
3. **Provider 兼容性**：为实际使用的 Provider 建立能力、上下文窗口、结构化工具、流式、视觉、价格来源、验证日期和已知限制矩阵；`unverified` 不得参与能力或节省声明。
4. **真实任务证据**：离线 fixture 只证明合同和回归稳定性，不能替代外部用户安装、真实项目任务和真实模型对比。
5. **安全边界表达**：当前工具和插件仍以本机进程权限运行，权限规则是授权控制面，不是 OS/容器沙箱。需要在 README、指南和 UI 中保持一致表述。
6. **长任务文档**：上下文计划保留为技术方向，但其中阶段状态和版本引用需要根据 U4、B5.4 与 v0.2.0 条件重新核对。

## 3. 优化顺序

### O1 文档与契约收口

**内容**：完成失效链接修复；每份现行文档标注状态和更新时间；历史记录只读归档；为 U4 事件建立最小 schema 示例和变更规则。

**验收**：仓库内现行 Markdown 链接全部有效；不存在指向已移动文档的当前入口；`docs/README.md` 能解释每类文档的用途；U4 schema 能由测试和示例共同验证。

### O2 U4 与运行可观察性

**内容**：统一 `mao run` 的事件名称、必填字段、时间戳、运行 ID、错误/退出状态和结束事件；保证并发 Worker 下 JSONL 不交叉、不丢失、不伪造 usage。会话级 compaction、resume、blocked 属于 Session/Web API，不与一次性 CLI 的 JSONL 混用。

**U4 事件 Schema 示例**（最小可验证版本，JSON Schema 风格，可直接用于文档或代码验证）：

```json
{
  "type": "object",
  "required": ["type", "ts", "run_id", "data"],
  "properties": {
    "type": { "type": "string", "enum": ["run", "plan", "model", "tool", "command", "file_change", "verification", "approval", "usage", "error", "cancel", "end"] },
    "run_id": { "type": "string" },
    "ts": { "type": "string", "format": "date-time" },
    "data": { "type": "object" }
  }
}
```

`end.data` 必含 `status`（`completed`、`failed` 或 `cancelled`）、`exit_code` 与 `elapsed_ms`；`usage` 和 `error` 事件提供运行中的计费与失败信息。`cancel` 仅表示执行前审批被拒绝，并以退出码 `130` 结束。

**验收**：离线测试覆盖成功、失败、取消、无 Provider 和多线程事件；`json` 可被标准 JSON 解析器读取，`streaming-json` 每行均为独立 JSON，所有事件共享同一 `run_id`；`end` 最后出现且退出状态一致。

### O3 Provider 兼容矩阵与安全边界 — ✅ 已完成（2026-07-25）

**内容**：先覆盖项目实际使用的 Provider，再扩展预设；把能力状态和价格来源与模型目录绑定；更新安全文档、插件指南和快速开始，明确同进程插件和无 OS 沙箱的风险。

**交付**：
- [`Provider兼容矩阵.md`](Provider兼容矩阵.md)：模板表、模型矩阵、错误码、安全边界、更新规则。
- `src/models/catalog.py`：`export_compatibility_matrix()` / `is_verified_metadata_source()` / 已知限制摘要。
- `tests/test_provider_matrix.py`：目录绑定、supported 需 verified 来源、unverified 不可升级、错误码完整。
- 更新 `SECURITY.md`、`README.md`、`QUICKSTART.en.md`、插件指南、本地 LLM 文档、`providers.yaml.example`。

**验收**：未知能力默认保守；连接失败、认证失败、限流和模型不支持有稳定错误码；自动路由不会选择未验证能力；文档没有把权限规则描述成沙箱。
### O4 外部用户与真实任务验证

**内容**：准备脱敏反馈模板和最小问题报告；邀请至少 10 个外部用户安装，推动至少 5 个真实项目任务；在获得明确次数、费用、模型和公开范围授权后恢复 B5.4 真实评测。

**验收**：`v0.2.0` 条件 #1 和 #3 有可复核证据；真实结果与 synthetic contract 分开存档；不把单次成功或未经授权的调用写成产品结论。

### O5 再决定产品扩展

只有 O1-O4 达到验收门，才评估 IDE 扩展、桌面端、远程执行、多用户协作、团队审计和插件生态。每个方向先写一页决策记录，再做最小原型。

## 4. 后续开发候选

按优先级保留以下候选：

| 优先级 | 方向 | 进入条件 |
|---|---|---|
| P0 | U4 事件 schema、恢复/压缩边界、退出码 | O1 完成且有离线回归 |
| P0 | Provider 兼容矩阵和错误语义 | 至少一个真实 Provider 有授权 smoke |
| P1 | 外部用户安装诊断、反馈导出和问题复现包 | 不上传密钥和项目内容 |
| P1 | 长任务 benchmark 与成本/完成率报告 | 与真实 Provider 结果分离 |
| P2 | IDE/桌面交互适配 | 外部用户明确提出稳定需求 |
| P2 | 远程执行、多用户、企业审计 | 先完成权限、身份、租户和隔离设计 |

## 5. 暂不开发

- 不先做插件市场、模型自动安装和无限扩展机制。
- 不先做“全自动”权限绕过、无确认写入或未经验证的自动路由节省承诺。
- 不把路径检查、Python 进程权限或插件启用门包装成容器/OS 沙箱。
- 不复制 OpenCode、Aider、Cline 或其他产品的完整功能清单。
- 不在没有真实用户反馈和运行证据前并行开发桌面端、IDE 扩展、云端服务。

## 6. 每个改动的完成门

任何后续改动都必须留下以下记录：

1. 目标用户场景和不解决的问题。
2. 受影响的接口、事件、配置或文档真值来源。
3. 针对性测试、相邻模块回归和必要的分发验证。
4. 失败、未验证能力、权限限制和真实 Provider 调用情况。
5. 当前进度文档的状态更新；完成的阶段资料移入 `docs/archive/`。

## 7. 下一步执行清单

- [x] 完成文档链接检查并保持 `docs/README.md` 为唯一文档导航（含 Provider 兼容矩阵入口）。
- [x] 为一次性 `mao run` 增加稳定事件信封、取消事件、并发 JSONL 原子性和退出状态合同测试；会话 compaction/resume/blocked 继续由 Session/Web API 测试覆盖。
- [x] 更新上下文计划、Provider 兼容矩阵和安全边界说明（O3）。
- [x] 运行完整测试、分发验收和 Markdown 链接检查（2026-07-28：`912 passed, 1 warning`；分发验收与 43 份现行 Markdown 本地链接检查通过）。
- [ ] 等待外部用户反馈和新的真实 Provider 授权，不自动恢复付费评测（O4）。
- [ ] O1-O4 完成后，再为后续产品方向建立单独决策文档。

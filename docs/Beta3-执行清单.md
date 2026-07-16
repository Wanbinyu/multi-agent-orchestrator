# v0.1.0-beta.3 执行清单

**状态**：进行中，B3.1-B3.2 离线验收已完成

**目标**：Provider/Claude 可信接入与首次使用稳定性

**规划基线提交**：`ac95647`

**B3.1 起始提交**：`67ac9a9`

**基线测试**：`506 passed, 1 warning`

## 0. 开始前检查

- [x] `git status --short --branch` 干净。
- [x] `git fetch origin` 后确认 `main` 没有未合并提交。
- [x] 阅读：
  - `docs/版本计划-v0.1.0-beta.3至beta.6.md`
  - `docs/Claude与插件接入决策.md`
  - `docs/项目进度与关键操作.md`
- [x] 不使用对话中曾出现过的旧密钥；真实 Key 必须在 Provider 控制台轮换后写入本地 `.env`。
- [x] 未获得所有者确认前，不执行真实付费 Claude 调用。

## 1. B3.1 Provider 能力真值

### 目标

把模型能力从散落的预设字符串升级为有来源、可验证、可回退的数据。

### 主要文件

- `src/models/catalog.py`
- `src/models/schemas.py`
- `src/ui/presets/builtin/*.py`
- `config/providers.yaml.example`
- 新增或扩展 Provider/Model catalog 测试

### 任务

- [x] 定义能力字段与状态：supported / unsupported / unverified。
- [x] 增加来源、验证日期、动态别名和最大输出字段。
- [x] 未验证能力不自动启用。
- [x] Web/CLI 能区分逻辑别名与上游模型 ID。
- [x] 修正示例配置和测试夹具。

### 验收

- [x] 旧配置仍可加载。
- [x] 未知模型回退保守上下文和能力。
- [x] 能力数据有单元测试，错误字段被拒绝。

### B3.1 实施记录（2026-07-16）

- 数据契约：`ModelConfig` 新增 `capability_status`、`metadata_source` 和 `metadata_verified_at`，状态只接受 `supported`、`unsupported`、`unverified`。
- 兼容规则：旧配置没有 `capability_status` 时继续按 `capabilities` 运行；新字段存在时，只有 `supported` 自动启用能力，显式 `native_tools` 仍是用户覆盖项。
- 配置链：模型目录、Web 预设展开、Web 保存/编辑、旧 CLI 预设生成器和示例 YAML 均保留新字段。
- 运行链：Agent 和 Worker 使用同一个能力判断，不再把显式 `unverified` 的 `tool_use` 当成可用。
- 验证：`python -m pytest -q` 为 `517 passed, 1 warning`；`compileall`、`node --check` 和 `git diff --check` 通过。
- 剩余风险：内置 Provider 的真实能力、模型 ID、价格和限制尚未逐项核实；在 B3.2 之前不得把未验证状态改成 `supported`。

## 2. B3.2 官方 Anthropic 预设与连接

### 目标

使官方 Claude 配置只包含有来源的模型和能力。

### 主要文件

- `src/ui/presets/builtin/anthropic.py`
- `src/gateway/connection_test.py`
- `src/gateway/provider.py`
- `src/models/catalog.py`
- Provider 配置与连接测试

### 任务

- [x] 从官方资料核实模型 ID、价格、上下文和输出限制。
- [x] 删除或标记无法确认的模型条目。
- [x] 明确 `ANTHROPIC_API_KEY` 配置提示。
- [x] 区分官方 Anthropic、Anthropic 兼容服务和 OpenRouter Claude。
- [x] 覆盖 401/403、404、429、超时和上下文超限。

### 验收

- [x] 离线 mock 覆盖所有错误类别。
- [x] 无 Key 时错误清晰，不打印 Key。
- [ ] 有所有者授权时执行一次最小真实连接 smoke，并记录费用。当前未授权、未执行，不阻塞离线验收。

### B3.2 实施记录（2026-07-16）

- 官方来源：模型数据使用 [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)，鉴权使用 [Get started](https://platform.claude.com/docs/en/get-started)，错误分类使用 [Claude API errors](https://platform.claude.com/docs/en/api/errors)。
- 模型 ID：Fable 5、Opus 4.8、Sonnet 5 使用官方无日期固定 ID；Haiku 4.5 使用 `claude-haiku-4-5-20251001`。
- 限制与价格：记录 1M/128K 与 Haiku 200K/64K 上下文/输出限制；价格使用官方标准价格，不把 Sonnet 5 限时优惠写成长期价格。
- 单一真值：`src/models/catalog.py` 作为官方 Anthropic 数据源，CLI 与 Web 预设由目录生成，不再各自复制模型元数据。
- 能力边界：`tool_use` 等待 B3.3 完整回合验证；`vision` 等待结构化图片消息，因此两者保持 `unverified`。
- 连接诊断：新增稳定 `error_code`，覆盖鉴权、权限、模型不存在、限流、超时、上下文超限、普通参数错误和连接失败；用户消息不拼接 SDK 原始异常。
- 验证：`python -m pytest -q` 为 `526 passed, 1 warning`；`compileall`、`node --check` 和 `git diff --check` 通过。
- 未执行：未读取或使用任何真实 Anthropic Key，未产生付费调用。

## 3. B3.3 Claude 原生工具完整回合

### 目标

验证工具定义、`tool_use`、本地执行和下一回合结果传递的完整语义。

### 主要文件

- `src/gateway/provider.py`
- `src/core/agent.py`
- `src/models/schemas.py`
- `tests/test_native_tool_use.py`

### 任务

- [x] 建立 Anthropic 多段内容/工具结果的结构化内部表示方案。
- [x] 保持不支持原生工具的 Markdown 兜底。
- [x] 流式和非流式路径行为一致。
- [x] thinking 内容不展示、不写日志，也不破坏必要状态。
- [x] 视觉能力在结构化图片消息完成前保持未验证。

### 验收

- [x] 至少覆盖一次 read 工具和一次受批准 write 工具回合。
- [x] 工具错误能返回模型并保留 Evidence。
- [x] 上下文压缩不会生成孤立工具块。

### 完成记录（2026-07-16）

- 消息内部增加安全可持久化的 `text`、`tool_use`、`tool_result` 块；旧字符串消息和旧 Session YAML 保持兼容。
- Anthropic 同步与流式响应均保留下一回合必需的 Provider 私有状态；thinking/signature 只存在于当前进程内，不显示、不写 Session YAML 或日志。
- 工具结果使用原始 `tool_use_id`，结果块排在后续文本之前，失败结果设置 `is_error: true`；达到工具上限时也会先返回配对错误结果。
- Agent、Worker、人工批准写入、工具失败 Evidence、流式状态和压缩边界均有离线契约测试；写文件意图同时覆盖带路径和内容的真实表达。
- 上下文预算按实际原生载荷估算，避免遗漏必须回传的私有块。
- 验证：`python -m pytest -q` 为 `536 passed, 1 warning`；`compileall`、`node --check` 和 `git diff --check` 通过。
- 未执行：未读取或使用真实 Anthropic Key，未产生付费调用；官方 Claude 的 `tool_use` 仍保持 `unverified`，等待所有者授权的真实端到端 smoke，`vision` 等待结构化图片消息。

## 4. B3.4 Provider 错误与恢复

### 目标

让所有 Provider 共享稳定的错误类别和用户操作建议。

### 主要文件

- `src/gateway/client.py`
- `src/gateway/connection_test.py`
- `src/gateway/provider.py`
- CLI/Web 错误显示模块

### 任务

- [ ] 定义结构化 ProviderError。
- [ ] 认证/配置错误不重试、不故障切换。
- [ ] 429、超时、连接失败和 5xx 按策略重试。
- [ ] 上下文超限优先触发本地预算说明，不伪装为网络错误。
- [ ] 错误消息脱敏并保留可调试错误码。

### 验收

- [ ] 同一错误在 CLI/Web 语义一致。
- [ ] 失败 RunJournal 可恢复且状态准确。
- [ ] 重试次数和最终模型写入 Evidence。

## 5. B3.5 扩展诊断和首次使用

### 目标

移除扩展静默失败，并验证全新安装的第一次使用。

### 主要文件

- `src/tools/extensions.py`
- `src/tools/mcp_adapter.py`
- `src/core/hooks.py`
- `run.py`
- `src/ui/cli.py`

### 任务

- [ ] Hooks/MCP 加载错误形成有界诊断结果。
- [ ] 没有扩展配置时保持安静。
- [ ] 错误扩展不阻塞核心启动。
- [ ] 干净目录验证 `mao` 首次向导。
- [ ] 干净目录验证 `mao web` 配置与 `/health`。
- [ ] 验证 pipx 安装、升级和卸载说明。

### 验收

- [ ] Windows/Linux CI 通过。
- [ ] wheel/sdist 元数据和归档内容通过。
- [ ] 扩展错误不泄露环境变量。

## 6. B3.6 发布收口

- [ ] 更新 `CHANGELOG.md`。
- [ ] 更新版本号为 `0.1.0b3`。
- [ ] 编写 `RELEASE_NOTES_v0.1.0-beta.3.md`。
- [ ] 全量测试、compileall、JavaScript 语法和 diff hygiene 通过。
- [ ] `pip-audit` 和 gitleaks 通过。
- [ ] 构建 wheel/sdist，`twine check` 通过。
- [ ] 空目录 pipx 安装与 `mao web /health` 通过。
- [ ] 远端 Windows/Ubuntu CI 通过。
- [ ] 所有者单独确认后才创建 Tag 和 GitHub pre-release。

## 7. 推荐提交边界

1. `feat: add verified provider capability metadata`
2. `fix: harden official anthropic provider integration`
3. `feat: preserve native anthropic tool rounds`
4. `fix: unify provider failures and recovery`
5. `fix: expose extension diagnostics and first-run checks`
6. `docs: prepare beta.3 release`

每个提交必须独立通过针对性测试，不等到最后一次性修复所有回归。

## 8. 当前下一步

从 **B3.4 Provider 错误与恢复** 开始。先定义结构化 ProviderError 和稳定错误码，再统一 CLI/Web 显示、重试、故障切换与 RunJournal Evidence；没有所有者授权时不进行真实付费调用。

# v0.1.0-beta.3 执行清单

**状态**：准备完成，尚未开始实现

**目标**：Provider/Claude 可信接入与首次使用稳定性

**基线提交**：`ac95647`

**基线测试**：`506 passed, 1 warning`

## 0. 开始前检查

- [ ] `git status --short --branch` 干净。
- [ ] `git fetch origin` 后确认 `main` 没有未合并提交。
- [ ] 阅读：
  - `docs/版本计划-v0.1.0-beta.3至beta.6.md`
  - `docs/Claude与插件接入决策.md`
  - `docs/项目进度与关键操作.md`
- [ ] 不使用对话中曾出现过的旧密钥；真实 Key 必须在 Provider 控制台轮换后写入本地 `.env`。
- [ ] 未获得所有者确认前，不执行真实付费 Claude 调用。

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

- [ ] 定义能力字段与状态：supported / unsupported / unverified。
- [ ] 增加来源、验证日期、动态别名和最大输出字段。
- [ ] 未验证能力不自动启用。
- [ ] Web/CLI 能区分逻辑别名与上游模型 ID。
- [ ] 修正示例配置和测试夹具。

### 验收

- [ ] 旧配置仍可加载。
- [ ] 未知模型回退保守上下文和能力。
- [ ] 能力数据有单元测试，错误字段被拒绝。

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

- [ ] 从官方资料核实模型 ID、价格、上下文和输出限制。
- [ ] 删除或标记无法确认的模型条目。
- [ ] 明确 `ANTHROPIC_API_KEY` 配置提示。
- [ ] 区分官方 Anthropic、Anthropic 兼容服务和 OpenRouter Claude。
- [ ] 覆盖 401/403、404、429、超时和上下文超限。

### 验收

- [ ] 离线 mock 覆盖所有错误类别。
- [ ] 无 Key 时错误清晰，不打印 Key。
- [ ] 有所有者授权时执行一次最小真实连接 smoke，并记录费用。

## 3. B3.3 Claude 原生工具完整回合

### 目标

验证工具定义、`tool_use`、本地执行和下一回合结果传递的完整语义。

### 主要文件

- `src/gateway/provider.py`
- `src/core/agent.py`
- `src/models/schemas.py`
- `tests/test_native_tool_use.py`

### 任务

- [ ] 建立 Anthropic 多段内容/工具结果的结构化内部表示方案。
- [ ] 保持不支持原生工具的 Markdown 兜底。
- [ ] 流式和非流式路径行为一致。
- [ ] thinking 内容不展示、不写日志，也不破坏必要状态。
- [ ] 视觉能力在结构化消息完成前保持未验证。

### 验收

- [ ] 至少覆盖一次 read 工具和一次受批准 write 工具回合。
- [ ] 工具错误能返回模型并保留 Evidence。
- [ ] 上下文压缩不会生成孤立工具块。

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

从 **B3.1 Provider 能力真值** 开始。先做数据模型和兼容读取测试，不先改 UI，也不进行真实付费调用。

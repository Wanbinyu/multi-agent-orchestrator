# Plugin API 兼容策略

**状态**：v0 稳定接口的兼容承诺与演进规则

**适用版本**：`v0.1.0-beta.6` 及后续，直至 Plugin API v1

**目的**：让插件作者知道 MAO 会在何时、以何种方式破坏插件兼容，以及如何声明和保持兼容。这是 v0.2.0 进入条件之一。

## 1. 什么是"Plugin API"

Plugin API 是 MAO 对第三方插件承诺稳定的公共接口面，仅包含以下内容：

- **入口点组**：`mao.plugins`（Python entry point）。
- **工厂约定**：entry point 指向 `() -> Plugin` 的零参工厂。
- **`Plugin` 协议**（`src/plugins/api.py`）：`manifest: PluginManifest`、`load(self, ctx: PluginContext) -> None`、`shutdown(self) -> None`。
- **`PluginManifest` 字段**：`id`、`name`、`version`、`mao_api_version`、`description`、`homepage`、`capabilities`、`permissions`、`source`。
- **`PluginContext` 方法**：`register_tool`、`add_tool_source`、`add_pre_hook`、`add_post_hook`、`register_provider_preset`、`register_model_capabilities`、`rollback`、`contributed_summary`。
- **能力常量**：`tools`、`tool_source`、`hooks`、`provider_preset`、`model_capabilities`。
- **权限常量**：`read_files`、`write_files`、`execute`、`network`。
- **启用态配置格式**：`config/plugins.yaml` 的 `enabled` / `disabled` 列表。
- **CLI 契约**：`mao plugin list/doctor/enable/disable` 的存在与退出码语义（输出格式不在此承诺内）。

**不在 Plugin API 内**（插件不得依赖，随时可能变）：`src/tools/registry.py`、`src/core/hooks.py`、`src/models/catalog.py` 等内部模块的具体实现、私有属性、未文档化的工具签名、RunJournal 内部结构、Web 路由返回体格式。插件应只通过 `PluginContext` 暴露的方法贡献，不直接操作内部注册表。

## 2. 版本号语义

`MAO_PLUGIN_API_VERSION` 采用 `MAJOR.MINOR`（当前 `0.1`）。

- **MINOR 升级（如 `0.1` -> `0.2`）**：仅追加式变更。新增可选的 `PluginContext` 方法、新的能力/权限常量、新的可选 manifest 字段、新的 CLI 子命令。**旧插件继续加载**，无需改动。
- **MAJOR 升级（如 `0.1` -> `1.0`，或 `0.x` -> `0.(x+1)` 中含破坏性变更）**：破坏性变更。包括但不限于：移除或重命名 `PluginContext` 方法、改变方法签名、移除能力/权限常量、改变 `Plugin` 协议方法、改变 entry point 组名、改变 manifest 必填字段、改变 `config/plugins.yaml` 格式。**旧插件被拒绝加载**。

在 `0.x` 阶段，MAJOR 与 MINOR 的界限由本文档定义的"破坏性变更"清单判定，而非数字大小；每次破坏性变更会在 Release Notes 与本文档修订记录中显式标注。

## 3. 兼容判定

- 插件在 `PluginManifest.mao_api_version` 声明它针对的 API 版本（一个字符串）。
- MAO 维护 `SUPPORTED_API_VERSIONS`（当前 `{"0.1"}`）。
- **加载规则**：`manifest.mao_api_version in SUPPORTED_API_VERSIONS` 时才加载；否则 `PluginManager` 记录 `plugin_api_incompatible` 诊断并跳过，不抛错、不阻塞其他插件。
- 判定在 `PluginManager.discover` 阶段完成，发生在任何 `plugin.load` 之前；不兼容插件绝不执行其 `load`。

## 4. MAO 演进承诺

- **追加式变更**：直接发布，`SUPPORTED_API_VERSIONS` 追加新 MINOR，旧版本仍保留在集合中。例：`0.1` -> 追加 `0.2`，集合变为 `{"0.1","0.2"}`，`0.1` 插件继续可用。
- **破坏性变更**：发布新 MAJOR，并在**一个发布周期**内同时支持新旧 MAJOR（过渡期）。过渡期结束后，旧 MAJOR 从 `SUPPORTED_API_VERSIONS` 移除，旧插件被拒绝。例：`0.x` -> `1.0`，过渡期集合 `{"0.x","1.0"}`，下一周期移除 `0.x`。
- **过渡期最短**：一个 MAO 版本。过渡期内 Release Notes 与 `mao plugin doctor` 提示插件作者升级。
- **紧急安全修复**：可不经过渡期移除某 API，但必须在 Release Notes 顶部以"安全破坏性变更"显式说明，并提供迁移路径。

## 5. 插件作者指南

- 始终在 manifest 声明 `mao_api_version` 为你开发时所针对的版本。
- 只使用 `PluginContext` 的公共方法；不要直接导入或修改 `tool_registry._tools`、`HookRegistry._pre` 等内部结构。
- 不要假设 CLI 输出格式稳定；如需程序化查询，用 `mao plugin list --config ...` 的退出码或自行调用 `PluginManager`。
- 锁定你的插件依赖的 MAO 版本范围（在你的包文档中说明），因为 `0.x` 阶段 API 仍可能破坏性演进。
- `load` 中只做注册；重资源在 `shutdown` 清理。`load` 抛错会被回滚并隔离，不影响其他插件。

## 6. 当前状态（2026-07-21）

- `MAO_PLUGIN_API_VERSION = "0.1"`，`SUPPORTED_API_VERSIONS = {"0.1"}`。
- 尚未发生破坏性变更；无过渡期版本。
- v0 阶段（`0.x`）API 仍可能随 MAO 演进而破坏性变更；v1 发布时会给明确迁移窗口。

## 7. 修订记录

- 2026-07-21：首版。定义 Plugin API 范围、`MAJOR.MINOR` 语义、兼容判定、过渡期承诺与插件作者指南。

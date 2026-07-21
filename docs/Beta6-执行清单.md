# v0.1.0-beta.6 执行清单

**状态**：beta.6 进行中；B6.1 开工

**目标**：把当前 ToolSource / MCP / Hooks / Provider 预设整理为可诊断、可版本约束、必须显式启用的 Plugin API v0。

**发布基线**：`v0.1.0-beta.5`

**依据**：[`版本计划-v0.1.0-beta.3至beta.6.md`](版本计划-v0.1.0-beta.3至beta.6.md) §5、[`Claude与插件接入决策.md`](Claude与插件接入决策.md) §8。

## 0. 执行原则

- 插件默认不启用，用户在本机显式允许后加载。
- 用标准 Python entry point 发现已安装插件，不扫描任意工作区代码。
- Python 插件是可信本机代码，与 MAO 进程同权限；不承诺沙箱；外部工具优先 MCP 进程边界。
- 加载失败隔离并报告，不得阻止 MAO 无插件启动。
- 一次只推进一个子任务；修改前记验收标准与针对性测试，修改后先跑针对性测试再扩大回归。
- 不调用真实付费 Provider；Tag/Release 待所有者确认。

## 1. B6.1 Plugin API v0 契约

- [x] `src/plugins/api.py`：`MAO_PLUGIN_API_VERSION`、`SUPPORTED_API_VERSIONS`、`PluginManifest`、`PluginContext`、`Plugin` 协议、能力/权限常量。
- [x] manifest 校验（id/name/version/mao_api_version 必填；能力/权限取值合法）。
- [x] API 版本兼容判定（不兼容明确拒绝）。
- [x] 针对性单元测试。

### B6.1 完成门
- [x] manifest 校验与版本兼容判定测试通过。
- [x] `PluginContext` 委托到 `tool_registry`/预设注册中心的方法签名稳定。

### B6.1 完成记录（2026-07-21）

- `src/plugins/api.py` 定义 v0 稳定接口：`MAO_PLUGIN_API_VERSION="0.1"`、`SUPPORTED_API_VERSIONS={"0.1"}`、`is_supported_api_version()`；`PluginManifest`（id 正则 `^[a-z][a-z0-9-]*$`、必填字段、能力/权限白名单校验）；`PluginContext`（register_tool/add_tool_source/add_pre_hook/add_post_hook/register_provider_preset/register_model_capabilities + `rollback()` 撤销全部贡献 + `contributed_summary()`）；`Plugin` Protocol（manifest/load/shutdown）。
- 为支持插件隔离/回滚，给 `ToolRegistry` 增 `unregister_tool()`/`remove_source()`，给 `HookRegistry` 增 `remove_pre()`/`remove_post()`（均为加法，不影响既有行为）。
- 能力常量：`tools`/`tool_source`/`hooks`/`provider_preset`/`model_capabilities`；权限常量：`read_files`/`write_files`/`execute`/`network`（声明+可见+启用即同意，不构成沙箱）。
- `tests/test_plugin_api.py` 23 条：manifest 校验（含参数化 bad id）、版本兼容、Context 注册/回滚（工具/工具源/hooks/预设/模型能力）、回滚不误伤既有工具、幂等回滚。
- 全量回归 `822 passed, 1 warning`（基线 799 + 新增 23），无回归。
- 已知既有问题（非 B6.1 引入）：`pytest tests/test_registry.py` 单独运行时 `test_global_registry_has_builtins` 命中 `replay`<->`worker_tools` 潜在循环 import；全量集合不受影响（CI 跑全量）。后续可单独修。

## 2. B6.2 插件管理器

- [x] `src/plugins/manager.py`：`PluginManager` discover（entry_points `mao.plugins`）/ 版本拒绝 / 启用态（`config/plugins.yaml`）/ 隔离加载 / shutdown / 诊断。
- [x] 失败插件不阻塞其他插件与无插件启动。
- [x] 与现有 `load_extensions()` 并存（独立模块，无插件时零行为变化；启动接线在 B6.3）。
- [x] 针对性测试（隔离、无插件、重复/幂等）。

### B6.2 完成记录（2026-07-21）

- `src/plugins/manager.py`：`PluginManager` 通过 `importlib.metadata.entry_points(group="mao.plugins")` 发现插件（支持注入 finder 便于测试），逐个 `ep.load()` 调工厂得 `Plugin`；duck-type 校验 manifest/load/shutdown；同 id 去重。
- 启用态：`config/plugins.yaml`（`enabled`/`disabled`，默认全关）；`enable/disable/is_enabled` 读写回；`disabled` 覆盖 `enabled`。
- 加载：`load_enabled()` 幂等；不兼容 API 版本拒绝并记 `plugin_api_incompatible` 诊断；未启用跳过；已启用逐个 `plugin.load(ctx)`，失败则 `ctx.rollback()` 清半加载状态并记 `plugin_load_error`，不阻塞其他插件或无插件启动。
- `shutdown()` 逐个 `plugin.shutdown()` + `ctx.rollback()` 注销贡献；`list_status()` 供 CLI/Web 展示 id/name/version/api 版本/兼容/启用/能力/权限/来源。
- 诊断复用 `extension_diagnostics` 有界脱敏（source=`plugin`）。
- `tests/test_plugin_manager.py` 15 条：发现（兼容/不兼容/去重/坏 entry point 隔离）、启用门控、不兼容拒绝、失败插件不阻塞其他且回滚半加载、无插件零变化、幂等加载、shutdown 注销工具与关闭工具源、enable/disable 往返、disable 覆盖 enable、list_status。
- 全量回归 `837 passed, 1 warning`，无回归。

## 3. B6.3 CLI `mao plugin`

- [ ] `mao plugin list` / `doctor` / `enable <id>` / `disable <id>`。
- [ ] `known_commands` 加入 `plugin`；命令名再审查 CLI 一致性。
- [ ] `config/plugins.yaml` 读写与 `.gitignore`。
- [ ] 针对性测试 + CLI 交互。

## 4. B6.4 示例插件

- [ ] `examples/plugins/mao_wordcount_plugin/` 独立可安装包 + entry point。
- [ ] 集成测试：discover -> enable -> load -> execute -> shutdown（真实 entry point）。
- [ ] 不兼容 API 版本插件被拒绝。

## 5. B6.5 Web 可见性

- [ ] `/api/plugins` 端点（清单 + 启用态 + 权限）。
- [ ] chat.html 只读插件/权限展示，320/390/1280px 无溢出。
- [ ] 针对性测试。

## 6. B6.6 发布收口

- [ ] `verify_distribution.py` 含示例插件发现/启用/执行/关闭。
- [ ] 全量回归、pip-audit、compileall/JS/diff、干净安装通过。
- [ ] CHANGELOG、Release Notes、版本号 `0.1.0b6`、升级说明完成。
- [ ] 远端 CI 全绿（含 gitleaks）。
- [ ] Tag 和 GitHub pre-release 仍需所有者单独确认。

## 7. 当前下一步

从 B6.1 Plugin API v0 契约开始：定义 manifest、context、Plugin 协议与 API 版本兼容判定，配套单元测试。

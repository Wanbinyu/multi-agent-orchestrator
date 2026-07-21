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

- [x] `mao plugin list` / `doctor` / `enable <id>` / `disable <id>`。
- [x] `known_commands` 加入 `plugin`；命令名再审查 CLI 一致性。
- [x] `config/plugins.yaml` 读写与 `.gitignore`。
- [x] 针对性测试 + CLI 交互。

### B6.3 完成记录（2026-07-21）

- `run.py` 新增 `plugin` typer 子应用：`list`（已发现插件 + 启用态/能力/权限/来源）、`doctor`（发现+兼容+加载健康，用临时 ToolRegistry/预设注册表做 dry-run，不影响运行中的注册表）、`enable <id>`/`disable <id>`（写 `config/plugins.yaml`）。`_maybe_insert_run_subcommand` 的 `known_commands` 加入 `"plugin"`。
- 命令名审查：`list/doctor/enable/disable` 与既有子命令风格一致（kebab-case、`--config/-c` 选项）；未发现冲突。
- `src/plugins/runtime.py`：进程级单例 `get_plugin_manager`/`load_plugins`/`get_plugin_status`/`shutdown_plugins`/`new_plugin_manager`（CLI 子命令用独立实例）。`load_plugins()` 幂等，发现+加载已启用插件到当前 `tool_registry`。
- 启动接线：`chat_command.py` 在 `load_extensions()` 后 `load_plugins()` 并打印加载/诊断；`app.py` lifespan 在扩展后加载插件、`finally` 中 `shutdown_plugins()` 再 `shutdown_extensions()`。
- `.gitignore` 新增 `config/plugins.yaml`（与 providers.yaml/workers.yaml 一致，用户本地启用态不入库）。
- `tests/test_plugin_cli.py` 10 条：help 列子命令、无插件 list/doctor、enable 写配置、enable/disable 往返、list 显示发现插件与启用态/权限、doctor 加载已启用插件、enable 未知 id 提示、运行时单例 load/shutdown 安全。
- 全量回归 `847 passed, 1 warning`，无回归。B6.1+B6.2 远端 CI `success`（[run 29837884580](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29837884580)）。

## 4. B6.4 示例插件

- [x] `examples/plugins/mao_wordcount_plugin/` 独立可安装包 + entry point。
- [x] 集成测试：discover -> enable -> load -> execute -> shutdown（真实 entry point）。
- [x] 不兼容 API 版本插件被拒绝（B6.2 单元测试覆盖；示例插件走兼容路径）。

### B6.4 完成记录（2026-07-21）

- `examples/plugins/mao_wordcount_plugin/`：独立可安装包，`pyproject.toml` 声明 `[project.entry-points."mao.plugins"]` `wordcount = "mao_wordcount_plugin:create_plugin"`；`mao_wordcount_plugin/__init__.py` 的 `WordCountPlugin` 实现 `Plugin` 协议（manifest id=`mao-wordcount`、API `0.1`、capabilities=`[tools]`、permissions=`[read_files]`；`load` 注册只读 `word_count` 工具；`shutdown` 空实现），`create_plugin()` 为 entry point 工厂。README 说明安装/启用/安全模型。
- `tests/test_plugin_example_integration.py` 4 条：用真实 `importlib.metadata.entry_points(group="mao.plugins")` 发现机制（临时 dist-info + sys.path，不 pip 安装）驱动示例插件 -- 发现、enable/load/execute（`word_count` 输出字符/单词/行数）/shutdown（工具注销）、list_status（能力/权限/来源可见）、manifest 声明 v0 API。wheel 安装环境验收留 B6.6 `verify_distribution.py`。
- 全量回归 `851 passed, 1 warning`，无回归。B6.3 远端 CI `success`（[run 29838695324](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29838695324)）。

## 5. B6.5 Web 可见性

- [x] `/api/plugins` 端点（清单 + 启用态 + 权限）。
- [x] chat.html 只读插件/权限展示，320/390/1280px 无溢出。
- [x] 针对性测试。

### B6.5 完成记录（2026-07-21）

- `src/ui/app.py` 新增 `GET /api/plugins`，返回 `get_plugin_status()`（`statuses` 列表 + `load` 摘要）；与 `/api/diagnostics/extensions` 一样不影响 `/health`。
- `chat.html` 右栏新增「插件」标签 + `rightbar-plugins-panel`（只读）：插件 id/名称/版本/启用/兼容徽章/能力/权限/来源，加载摘要，以及"可信本机代码、权限仅作同意展示"提示；`chat.js` 缓存版本升至 `20260721-plugins1`。
- `chat.js`：`setRightbarTab` 重构为通用 3 标签循环；新增 `loadPlugins()`（fetch `/api/plugins` -> `renderPlugins`）；`tab-plugins`/`btn-refresh-plugins` 点击监听。
- `style.css`：`.rightbar-tabs` 网格由 2 列改 3 列（容纳「上下文/文件/插件」短标签，窄视口不溢出）；新增 `.plugin-item/.plugin-badge/.plugin-meta/.plugin-hint` 等样式，`plugin-item-head` 用 `flex-wrap`。
- 视口：3 个 2 字短标签在 3 列网格于 320/390/1280px 均可容纳（结构 + CSS 验证，与 B5.5 一致未跑 MAO UI Playwright）。
- `tests/test_ui.py` 新增 2 条：`/api/plugins` 返回 `statuses` 列表与 `load`；`/chat` 页面含 `tab-plugins`/`rightbar-plugins-panel`。
- 全量回归 `853 passed, 1 warning`，无回归。B6.4 远端 CI `success`（[run 29839280653](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29839280653)）。

## 6. B6.6 发布收口

- [ ] `verify_distribution.py` 含示例插件发现/启用/执行/关闭。
- [ ] 全量回归、pip-audit、compileall/JS/diff、干净安装通过。
- [ ] CHANGELOG、Release Notes、版本号 `0.1.0b6`、升级说明完成。
- [ ] 远端 CI 全绿（含 gitleaks）。
- [ ] Tag 和 GitHub pre-release 仍需所有者单独确认。

## 7. 当前下一步

从 B6.1 Plugin API v0 契约开始：定义 manifest、context、Plugin 协议与 API 版本兼容判定，配套单元测试。

# MAO 文档

本目录保留当前架构、产品路线、使用扩展和发布记录。已经完成或被替代的阶段设计移入 `archive/`，不再与当前计划混放。

## 当前架构与方向

- [`MAO-架构概览.md`](MAO-架构概览.md)：当前模块、数据流、权限和工程边界。
- [`MAO-产品方向与Beta路线图.md`](MAO-产品方向与Beta路线图.md)：长期定位、产品原则和优先级。
- [`版本计划-v0.1.0-beta.3至beta.6.md`](版本计划-v0.1.0-beta.3至beta.6.md)：当前四个 Beta 的范围、顺序和发布门。
- [`v0.2.0-进入条件.md`](v0.2.0-进入条件.md)：v0.2.0 发布前的五个进入条件与当前满足状态。
- [`Beta3-执行清单.md`](Beta3-执行清单.md)：beta.3 逐项任务、验收和提交边界（已完成）。
- [`Beta4-执行清单.md`](Beta4-执行清单.md)：beta.4 逐项任务、验收和发布记录（已完成）。
- [`Beta5-执行清单.md`](Beta5-执行清单.md)：基准、执行深度和路由任务边界（已完成）。
- [`Beta6-执行清单.md`](Beta6-执行清单.md)：Plugin API v0 任务边界与发布记录（已完成）。
- [`项目进度与关键操作.md`](项目进度与关键操作.md)：跨设备继续开发的状态、命令和恢复入口。
- [`Claude与插件接入决策.md`](Claude与插件接入决策.md)：Claude 官方 API 与 Plugin API v0 的接入边界。
- [`Plugin-API兼容策略.md`](Plugin-API兼容策略.md)：Plugin API 版本语义、兼容判定与演进承诺。
- [`参考项目-OpenCode.md`](参考项目-OpenCode.md)：OpenCode 开源核实、可借鉴设计和差异化边界。
- [`上下文扩展与长任务稳定性计划.md`](上下文扩展与长任务稳定性计划.md)：分层压缩、项目索引和长任务基准专项。
- [`真实任务稳定性改进计划.md`](真实任务稳定性改进计划.md)：真实前端任务复盘、标准操作流程、B4.S 稳定性切片和验收门。
- [`开源Coding-Agent参考与吸收计划.md`](开源Coding-Agent参考与吸收计划.md)：Grok Build、Codex、OpenCode、Aider、Cline 等项目的许可证审计、已吸收契约和分阶段接入顺序。

## 使用与扩展

- [`QUICKSTART.en.md`](QUICKSTART.en.md)：英文快速开始。
- [`迁移指南.md`](迁移指南.md)：beta.3 -> beta.6 升级注意与向 v0.2.0 迁移要点。
- [`工具开发指南.md`](工具开发指南.md)：扩展内置工具和第三方工具。
- [`插件开发指南.md`](插件开发指南.md)：Plugin API v0 插件开发（manifest/entry point/生命周期/权限/示例）。
- [`本地LLM接入与扩展点.md`](本地LLM接入与扩展点.md)：本地模型接入方式。
- [`B5.4-真实能力评测操作手册.md`](B5.4-真实能力评测操作手册.md)：真实能力评测的操作、密钥注入与结果解读。
- [`验证指南.md`](验证指南.md)：本地验证与故障检查。

## 发布

- [`RELEASE_NOTES_v0.1.0-beta.1.md`](RELEASE_NOTES_v0.1.0-beta.1.md)
- [`RELEASE_NOTES_v0.1.0-beta.2.md`](RELEASE_NOTES_v0.1.0-beta.2.md)
- [`RELEASE_NOTES_v0.1.0-beta.3.md`](RELEASE_NOTES_v0.1.0-beta.3.md)
- [`RELEASE_NOTES_v0.1.0-beta.4.md`](RELEASE_NOTES_v0.1.0-beta.4.md)
- [`RELEASE_NOTES_v0.1.0-beta.5.md`](RELEASE_NOTES_v0.1.0-beta.5.md)
- [`RELEASE_NOTES_v0.1.0-beta.6.md`](RELEASE_NOTES_v0.1.0-beta.6.md)
- [`RELEASE_NOTES_v0.1.0-beta.7.md`](RELEASE_NOTES_v0.1.0-beta.7.md)
- [`acceptance/发布验收记录.md`](acceptance/发布验收记录.md)

## 历史归档

- [`archive/README.md`](archive/README.md)：早期架构、已完成阶段、旧对标和发布准备过程。

`acceptance/` 和 `archive/` 用于维护者追溯，并通过 `export-ignore` 排除在发布源码归档之外；贡献者通过 Git 克隆仍可查看完整记录。

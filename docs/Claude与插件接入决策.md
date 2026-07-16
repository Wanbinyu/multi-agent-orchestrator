# Claude 与插件接入决策

**状态**：已决策，按版本计划执行

**日期**：2026-07-16

## 1. 结论

- **需要完善 Claude 接入**，安排在 `v0.1.0-beta.3`，但目标是验证和收口已有官方 API 支持，不是接入 Claude Code 的非公开登录方式。
- **需要 Plugin API**，安排在 `v0.1.0-beta.6`。在此之前继续使用内置工具、MCP、Hooks 和预设注册，不建设插件市场。
- Claude 接入优先于 Plugin API，因为它直接验证 MAO 的多模型价值；插件系统只有在核心契约稳定后才不会反复破坏兼容性。

## 2. 当前 Claude 支持

代码中已经存在：

- `anthropic` Python SDK 依赖。
- `AnthropicProvider`，支持官方 `x-api-key` 和特定兼容端点的 Bearer 鉴权。
- `https://api.anthropic.com` 官方 Provider 预设。
- `ANTHROPIC_API_KEY` 环境变量入口。
- 非流式和流式 Messages API 调用。
- Anthropic 格式的原生工具 Schema 和 `tool_use` 解析。
- Provider 连接测试、模型映射、费用估算和故障分类基础。
- OpenRouter 中的 Claude 模型路径。

因此当前状态是“基础链路已实现，真实兼容性尚未形成发布级证据”。

截至 2026-07-16，B3.2 已完成官方模型 ID、标准价格、上下文/输出限制、鉴权入口和连接错误的离线契约验证。`tool_use` 与视觉仍保持 `unverified`，分别等待 B3.3 的完整工具回合与结构化消息支持；未执行真实付费 smoke。

## 3. Claude 接入缺口

### P0

1. **模型真值不足**
   - 预设模型 ID、价格、上下文和能力必须有官方来源与验证日期。
   - 未验证模型不能因为名称包含 Claude 就自动声明视觉、reasoning 或工具能力。

2. **完整工具回合不足**
   - 当前可发送原生工具 Schema，并把返回的 `tool_use` 转成 MAO 工具块。
   - 仍需验证工具结果进入下一回合时是否符合官方 Messages API 语义，而不只是字符串兜底。

3. **多模态消息模型不足**
   - 当前 `ChatMessage.content` 主要是字符串。
   - 在引入结构化图片内容前，不能把“vision”当作已完整支持功能宣传。

4. **错误与限制说明不足**
   - 需要区分 API Key 无效、模型不存在、额度不足、限流、区域/组织限制和上下文超限。

### P1

- Prompt caching 是否启用，需要先确认 SDK、模型和计费语义，并用指标证明收益。
- Extended thinking/reasoning 必须结构化处理，不向用户暴露隐藏推理，也不能静默丢失必要状态。
- Bedrock/Vertex 上的 Claude 属于独立 Provider 适配，放在官方 Anthropic API 稳定之后。

## 4. Claude 凭据边界

MAO 当前官方路径使用 `ANTHROPIC_API_KEY` 调用公开 Messages API。

必须遵守：

- 不假设 claude.ai、Claude Pro/Max 或 Claude Code 订阅凭据可以直接作为 API Key。
- 不读取浏览器 Cookie、桌面应用 Token 或非公开认证缓存。
- 不通过逆向 Claude Code 登录协议来规避官方 API 计费或授权。
- 用户可以选择官方 Anthropic API、OpenRouter 等公开 Provider；每种路径单独记录价格和能力来源。
- Key 只写入本地 `.env`，不得进入配置示例、日志、Issue 或 Git。

## 5. Claude 在多模型协作中的定位

Claude 不应被硬编码为所有任务的总指挥。推荐由能力和用户配置决定：

- 复杂架构、审查和跨文件推理：可作为 `deep` 模式候选。
- 小修改和格式化：优先低成本模型或本地模型。
- 长上下文任务：必须根据已验证窗口和成本预算选择。
- Claude 不可用时：按用户配置回退，不把兼容协议名误显示为 Claude。

路由策略在 `beta.5` 才正式数据化；`beta.3` 只保证 Claude Provider 可信可用。

## 6. 当前扩展能力

MAO 已经有扩展基础：

- `ToolRegistry.register()`：注册本地工具。
- `ToolSource`：挂载外部工具来源。
- `MCPToolSource`：stdio/SSE MCP 接入。
- Hooks：工具调用前后拦截。
- Provider preset registry：注册 WebUI Provider 预设。
- `src/tools/contrib/`：第三方工具示例位置。

这些是扩展点，但还不是完整插件系统。

## 7. 为什么不立刻做插件市场

当前缺少：

- 插件清单和唯一 ID。
- MAO API 兼容版本。
- 标准发现与安装方式。
- 启用/禁用状态。
- 加载错误和健康诊断。
- 生命周期与资源清理契约。
- 权限、来源和风险展示。
- 插件测试模板和发布规范。

如果现在直接允许扫描并导入任意 Python 文件，会扩大供应链和任意代码执行风险，也会在核心 API 仍变化时制造兼容负担。

## 8. Plugin API v0 决策

### 推荐结构

- 使用标准 Python package entry point 发现已安装插件。
- 插件声明清单至少包含：
  - `id`
  - `name`
  - `version`
  - `mao_api_version`
  - `entry_point`
  - `capabilities`
  - `permissions`
  - `homepage/source`
- 插件默认不启用，用户在本机显式允许后加载。
- 加载失败被隔离，核心 MAO 继续启动。
- 提供确定性的初始化和 shutdown。

### 能力顺序

1. 工具和 ToolSource。
2. Hooks。
3. Provider 预设和模型能力数据。
4. Provider 运行时适配器，只有在接口稳定后开放。
5. UI 插件不进入 Plugin API v0。

### 安全模型

- Python 插件是可信本机代码，与 MAO 进程拥有相同权限。
- 不把“插件”描述成沙箱。
- 不允许模型自动同意安装或启用插件。
- 外部工具优先通过 MCP 获得进程边界和独立生命周期。

## 9. 实施顺序

1. `beta.3`：Claude/Provider 真值、错误和真实烟雾验证；扩展加载错误可见。
2. `beta.4`：完成工程状态和上下文可观察性，固定用户可见事件契约。
3. `beta.5`：完成路由与基准，固定模型能力和成本数据需求。
4. `beta.6`：在上述契约稳定后发布 Plugin API v0。

详细版本门见 [`版本计划-v0.1.0-beta.3至beta.6.md`](版本计划-v0.1.0-beta.3至beta.6.md)。

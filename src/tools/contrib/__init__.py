"""第三方贡献工具目录

其他开发者可在此目录新增工具模块，按下列步骤即可让 MAO 自动识别并使用：

1. 在本目录新建 `my_tools.py`；
2. 用 `@tool_registry.register(...)` 装饰工具函数，返回 `ToolResult`；
3. 在 `src/tools/worker_tools.py` 顶部追加 `import src.tools.contrib.my_tools  # noqa: F401`，
   或在应用启动处统一 import。

工具会在导入时自动注册到全局 `tool_registry`，随即出现在：
- Agent 系统提示（Markdown 模式）或 tools= 参数（原生模式）
- CLI `/tools` 命令
- Web 工具调用

详见 `docs/工具开发指南.md`。
"""

# mao-wordcount-plugin

MAO Plugin API v0 的官方示例插件。它贡献一个只读 `word_count` 工具，用于演示如何把一个工具打包为可被发现、可启用、有生命周期的插件。

## 安装

在已安装 MAO 的环境中，从源码安装本示例：

```bash
pip install ./examples/plugins/mao_wordcount_plugin
```

## 启用

插件默认不启用。安装后显式启用，再启动 MAO 即加载：

```bash
mao plugin enable mao-wordcount
mao            # 启动后 word_count 工具可用
mao plugin doctor   # 诊断加载健康
```

禁用：

```bash
mao plugin disable mao-wordcount
```

## 结构

- `mao_wordcount_plugin/__init__.py`：`WordCountPlugin` 实现 `Plugin` 协议（manifest + `load` 注册工具 + `shutdown`）；`create_plugin()` 是 `mao.plugins` entry point 工厂。
- `pyproject.toml`：声明 `[project.entry-points."mao.plugins"]`，MAO 据此发现插件。

## 安全模型

Python 插件是可信本机代码，与 MAO 进程拥有相同权限。manifest 中的 `permissions`（本例为 `read_files`）是给用户看的同意面，不构成沙箱。外部工具优先通过 MCP 获得进程边界。

# mao-wordcount-plugin

Official sample plugin for MAO Plugin API v0. It contributes a read-only `word_count` tool to show how to package a tool as a discoverable, enableable plugin with a lifecycle.

## Install

In an environment where MAO is already installed, install this sample from source:

```bash
pip install ./examples/plugins/mao_wordcount_plugin
```

## Enable

Plugins are disabled by default. After install, enable explicitly, then start MAO to load it:

```bash
mao plugin enable mao-wordcount
mao            # after start, the word_count tool is available
mao plugin doctor   # diagnose load health
```

Disable:

```bash
mao plugin disable mao-wordcount
```

## Structure

- `mao_wordcount_plugin/__init__.py`: `WordCountPlugin` implements the `Plugin` protocol (manifest + `load` registers the tool + `shutdown`); `create_plugin()` is the `mao.plugins` entry-point factory.
- `pyproject.toml`: declares `[project.entry-points."mao.plugins"]`, which MAO uses to discover the plugin.

## Security model

Python plugins are trusted local code and share the same privileges as the MAO process. Manifest `permissions` (here `read_files`) are a user-facing consent surface, not a sandbox. Prefer MCP for external tools when you need a process boundary.

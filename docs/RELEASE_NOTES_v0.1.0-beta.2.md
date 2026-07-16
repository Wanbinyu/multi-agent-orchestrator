# MAO v0.1.0-beta.2 Release Notes

This beta focuses on first-use installation and a smaller public distribution.

## Highlights

- Run `mao` to enter terminal chat; first use opens Provider setup automatically.
- Run `mao web` to start the local WebUI. The legacy `mao-ui` command remains supported.
- Installed commands use the current project directory for configuration, sessions and output.
- WebUI starts from an empty directory before Provider configuration exists.
- The installed package includes the default Worker template needed by collaboration flows.
- Personal learning notes and completed implementation logs are removed from the public tree.
- Tests remain available to contributors in Git, while wheel, sdist and release archives exclude development-only material.

## Install

```bash
pipx install git+https://github.com/Wanbinyu/multi-agent-orchestrator.git@v0.1.0-beta.2
mao
# or
mao web
```

Python 3.11 or 3.12 is required. Provider keys and runtime data remain in the current project directory and must not be committed.

## Verification

- Local suite: `506 passed, 1 warning`.
- Wheel install and WebUI health smoke passed from an empty directory.
- Wheel/sdist build and metadata validation passed.
- Tests and internal acceptance documents are absent from distribution artifacts.
- Remote Windows/Ubuntu CI for Python 3.11/3.12, dependency audit and secret scan passed.

## Known limitations

- No container-level sandbox; commands run with the MAO process permissions.
- Provider compatibility varies for streaming and native tool use.
- The current project directory is the workspace and stores local MAO runtime data.
- Layered context compaction and complete long-task benchmarks remain post-beta work.

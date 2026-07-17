# MAO v0.1.0-beta.3 Release Notes

This beta makes Provider access trustworthy and first use verifiable: capability truth, official Claude support, unified provider errors, extension diagnostics and an expanded model catalog.

## Highlights

- **Capability truth**: every model records capability status (`supported` / `unsupported` / `unverified`), metadata source, verification date, context window and output limits. Unverified capabilities stay off instead of being guessed from model names.
- **Official Anthropic Claude**: audited model IDs, limits and pricing from official docs; native `tool_use` full rounds verified offline for sync and streaming, with thinking content kept private and compaction-safe tool blocks. Real paid smoke remains owner-authorized only.
- **Unified provider errors**: one structured `ProviderError` across CLI and Web with sanitized codes, actionable next steps, and a clear retry/failover policy — auth and config errors stop immediately, transient errors back off and fail over, long-term quota errors cool down without retry storms.
- **Extension diagnostics**: Hooks and MCP entries load independently; bad entries produce bounded, redacted diagnostics without blocking startup. CLI prints a short summary, Web exposes `GET /api/diagnostics/extensions`, and `/health` stays clean.
- **First-use acceptance, automated**: `scripts/verify_distribution.py` builds the wheel/sdist, installs into an isolated venv and smoke-tests clean-directory CLI and Web `/health`. It runs in CI on every push. Windows first run no longer opens an interactive wizard without a real console.
- **Expanded model catalog**: presets now cover Anthropic, OpenAI (GPT-5), DeepSeek (V4), Zhipu GLM (GLM-5), Kimi (K2.7), Alibaba Qwen (Qwen3 Coder), MiniMax (M2.7), ByteDance Doubao and Google Gemini (3.x) — plus local Ollama/llama.cpp. `src/models/catalog.py` is the single source of truth for CLI and Web presets; unverified entries keep conservative 32K budgets and placeholder prices.
- The Kimi third-party relay preset was removed from CLI presets.

## Install

```bash
pipx install git+https://github.com/Wanbinyu/multi-agent-orchestrator.git@v0.1.0-beta.3
mao
# or
mao web
```

Python 3.11 or 3.12 is required. Provider keys and runtime data remain in the current project directory and must not be committed.

## Verification

- Local suite: `559 passed, 1 warning`.
- `scripts/verify_distribution.py` passed: archive contract, isolated install, clean CLI first run and Web health.
- `python -m compileall`, `node --check` on Web UI scripts and `git diff --check` passed.
- Remote Windows/Ubuntu CI for Python 3.11/3.12, dependency audit and secret scan passed.
- No real paid provider calls were made; official Claude `tool_use` and `vision` remain `unverified` pending owner-authorized smoke.

## Known limitations

- No container-level sandbox; commands run with the MAO process permissions.
- Streaming and native tool compatibility still vary by provider; dynamic aliases may not expose exact model versions.
- Newly added catalog entries carry `unverified` metadata and placeholder prices until audited against provider docs.
- Layered context compaction, session recovery and routing benchmarks remain beta.4/beta.5 work.

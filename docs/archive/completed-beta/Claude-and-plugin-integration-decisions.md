# Claude and Plugin Integration Decisions

**Status**: Decided; execute per version plan

**Date**: 2026-07-16

## 1. Conclusions

- **Claude integration needs to be completed**, scheduled for `v0.1.0-beta.3`, but the goal is to verify and close existing official API support—not to integrate Claude Code’s non-public login paths.
- **Plugin API is needed**, scheduled for `v0.1.0-beta.6`. Until then continue using built-in tools, MCP, Hooks, and preset registration; do not build a plugin marketplace.
- Claude integration comes before Plugin API because it directly validates MAO’s multi-model value; a plugin system only avoids repeated compatibility breakage after core contracts are stable.

## 2. Current Claude support

Already present in code:

- `anthropic` Python SDK dependency.
- `AnthropicProvider`, supporting official `x-api-key` and Bearer auth for certain compatible endpoints.
- Official Provider preset for `https://api.anthropic.com`.
- `ANTHROPIC_API_KEY` environment-variable entry.
- Non-streaming and streaming Messages API calls.
- Anthropic-format native tool Schema and `tool_use` parsing.
- Provider connection test, model mapping, cost estimation, and basic failure classification.
- Claude model path via OpenRouter.

Therefore the current state is: “official model truth and native tool rounds have completed offline contract verification; real paid compatibility still awaits owner-authorized smoke.”

As of 2026-07-16, B3.2 completed offline contract verification of official model IDs, standard pricing, context/output limits, auth entry points, and connection errors; B3.3 completed offline acceptance of structured `tool_use`/`tool_result`, sync/stream state, thinking private state, human-approved writes, and compaction boundaries. `tool_use` and vision remain `unverified`, waiting respectively for real end-to-end smoke and structured image messages; real paid smoke has not been run.

## 3. Claude integration gaps

### P0

1. **Insufficient model truth**
   - Preset model IDs, pricing, context, and capabilities must have official sources and verification dates.
   - Unverified models must not automatically claim vision, reasoning, or tool capabilities just because the name contains Claude.

2. **Full tool rounds lack real smoke**
   - Offline contracts already verify native tool Schema, structured `tool_use`, local execution, and `tool_result` handoff with original IDs.
   - Release-grade capability claims still need owner authorization for a minimal real read/write smoke against the official Messages API.

3. **Multimodal message model insufficient**
   - Current `ChatMessage.content` is primarily a string.
   - Do not market “vision” as fully supported before structured image content is introduced.

4. **Errors and limits still lack real Provider smoke**
   - B3.4 offline-verified unified error semantics for invalid API key, permission, model not found, insufficient quota, rate limit, timeout, connection, 5xx, parameters, and context exceeded.
   - Real Claude API status codes, response headers, and region/org limits still need owner-authorized minimal smoke.

### P1

- Whether prompt caching is enabled needs prior confirmation of SDK, model, and billing semantics, plus metrics proving benefit.
- Extended thinking/reasoning is already handled as “in-process handoff; exclude from display and persistence”; real model compatibility still needs smoke.
- Claude on Bedrock/Vertex is a separate Provider adaptation after official Anthropic API is stable.

## 4. Claude credential boundaries

MAO’s current official path uses `ANTHROPIC_API_KEY` to call the public Messages API.

Must obey:

- Do not assume claude.ai, Claude Pro/Max, or Claude Code subscription credentials can be used directly as an API Key.
- Do not read browser cookies, desktop-app tokens, or non-public auth caches.
- Do not reverse-engineer Claude Code login protocols to bypass official API billing or authorization.
- Users may choose official Anthropic API, OpenRouter, or other public Providers; each path records price and capability sources separately.
- Keys go only into local `.env`; never into config examples, logs, Issues, or Git.

## 5. Claude’s role in multi-model collaboration

Claude must not be hard-coded as the commander of all tasks. Prefer capability and user config:

- Complex architecture, review, and cross-file reasoning: candidate for `deep` mode.
- Small changes and formatting: prefer low-cost or local models.
- Long-context tasks: choose by verified window and cost budget.
- When Claude is unavailable: fall back per user config; do not mis-display a compatible protocol name as Claude.

Routing policy is data-driven only in `beta.5`; `beta.3` only ensures the Claude Provider is trustworthy and usable.

## 6. Current extension capabilities

MAO already has extension foundations:

- `ToolRegistry.register()`: register local tools.
- `ToolSource`: mount external tool sources.
- `MCPToolSource`: stdio/SSE MCP access.
- Hooks: intercept before/after tool calls.
- Provider preset registry: register WebUI Provider presets.
- `src/tools/contrib/`: location for third-party tool examples.

These are extension points, not a full plugin system.

## 7. Why not build a plugin marketplace yet

Currently missing:

- Plugin manifest and unique ID.
- MAO API compatibility version.
- Standard discovery and install method.
- Enable/disable state.
- Load errors and health diagnostics.
- Lifecycle and resource-cleanup contracts.
- Permission, source, and risk display.
- Plugin test templates and release norms.

Allowing arbitrary Python files to be scanned and imported now would expand supply-chain and arbitrary code-execution risk and create compatibility burden while core APIs still change.

## 8. Plugin API v0 decisions

### Recommended structure

- Discover installed plugins via standard Python package entry points.
- Plugin manifests at least include:
  - `id`
  - `name`
  - `version`
  - `mao_api_version`
  - `entry_point`
  - `capabilities`
  - `permissions`
  - `homepage/source`
- Plugins are not enabled by default; load only after the user explicitly allows them on this machine.
- Load failures are isolated; core MAO continues to start.
- Provide deterministic initialization and shutdown.

### Capability order

1. Tools and ToolSource.
2. Hooks.
3. Provider presets and model capability data.
4. Provider runtime adapters only after the interface is stable.
5. UI plugins are out of Plugin API v0.

### Security model

- Python plugins are trusted local code with the same privileges as the MAO process.
- Do not describe “plugins” as a sandbox.
- Models must not automatically agree to install or enable plugins.
- Prefer MCP for external tools to get process boundaries and independent lifecycles.

## 9. Implementation order

1. `beta.3`: Claude/Provider truth, errors, and real smoke verification; extension load errors visible.
2. `beta.4`: Finish engineering state and context observability; fix user-visible event contracts.
3. `beta.5`: Finish routing and benchmarks; fix model capability and cost data requirements.
4. `beta.6`: Ship Plugin API v0 after the above contracts are stable.

Detailed version gates: [`version-plan-v0.1.0-beta.3-to-beta.6.md`](version-plan-v0.1.0-beta.3-to-beta.6.md).

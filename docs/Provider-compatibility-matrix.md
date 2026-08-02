# Provider Compatibility Matrix and Security Boundaries

**Status**: Living (O3)  
**Last updated**: 2026-07-25  
**Baseline**: `v0.1.0-beta.7`  
**Source of truth**: `src/models/catalog.py` (`BUILTIN_MODELS` / `PROVIDER_TEMPLATES` / `export_compatibility_matrix()`)  
**Routing implementation**: `src/gateway/router.py` (`ModelRouter`)  
**Error-code implementation**: `src/gateway/errors.py` (`ProviderErrorCode`)

This document describes MAO’s capability status, price sources, context windows, and known limits for each Provider/model preset, and the distinction between permission rules and an OS sandbox.  
**Fields not verified in real smoke must not be used for automatic upgrade or cost-savings claims.**

## 1. Capability and metadata semantics

| Field | Value | Routing and display meaning |
|---|---|---|
| `capability_status` | `supported` | Verified; may participate in automatic upgrade and capability claims |
| `capability_status` | `unverified` | Conservative by default; **cannot** trigger automatic upgrade; **cannot** claim the capability |
| `capability_status` | `unsupported` | Explicitly unsupported; must not be a candidate capability |
| `metadata_source` | Official doc URL etc. | Traceable when source does not contain `unverified`/`unknown` |
| `metadata_source` | `unverified` | Price and capability claims treated as placeholders |
| `context_window_tokens` | `0` or unverified | MAO uses a **200K** local default safety budget; not the upstream physical limit |
| `dynamic_model_alias` | `true` | Upstream may switch real model versions; window and capabilities may drift |

Capability names (common in catalog): `tool_use`, `coding`, `reasoning`, `chat`, `vision`.

### Routing contract (bound to tests)

- Automatic routing (`/routing auto`) treats **only** capabilities with `capability_status == supported` as verified.
- List-style `capabilities` whose `metadata_source` contains `unverified` are treated as `unverified` and **cannot** trigger upgrade (see `tests/test_explainable_model_routing.py`).
- When price is unknown or source unverified: `savings_claim_allowed` is false; do not claim “cheaper.”
- User `fixed` mode locks the main model even if other candidates have higher verified scores.
- Unverified capabilities default conservative: failure fallback, health cooldown, and context budget still take priority over capability guesses.

## 2. Provider preset templates

| Template key | Display name | Protocol type | Default Base URL (example) | Catalog model aliases |
|---|---|---|---|---|
| `volcengine_ark` | Volcengine Ark | anthropic | `https://ark.cn-beijing.volces.com/api/coding` | `glm-ark`, `glm-chat` |
| `openai` | OpenAI | openai | `https://api.openai.com/v1` | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` |
| `anthropic` | Anthropic | anthropic | `https://api.anthropic.com` | `claude-fable-5`, `claude-opus-5`, `claude-sonnet-5`, `claude-haiku-4-5` |
| `kimi` | Kimi relay | openai | `https://api.moonshot.cn/v1` | `kimi-k3` (upstream `k3`), `kimi-k2.7-code` (upstream `k3-256k`), `kimi-k2.7`, `kimi-k2.5`, `kimi-for-coding` |
| `kimi_coding` | Kimi Coding Plan | openai | `https://api.kimi.com/coding/v1` | `k3`, `k3-256k`, `kimi-for-coding`, `kimi-for-coding-highspeed` |
| `deepseek` | DeepSeek | openai | `https://api.deepseek.com/v1` | `deepseek-v4-pro`, `deepseek-v4-flash` |
| `zhipu_glm` | Zhipu GLM | openai | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.2`, `glm-5` |
| `qwen` | Alibaba Qwen | openai | DashScope compatible-mode | `qwen3.8-max-preview`, `qwen3.7-max`, `qwen3.7-plus`, `qwen3.7-flash` |
| `minimax` | MiniMax | openai | `https://api.minimaxi.com/v1` | `minimax-m3` |
| `ark_openai` | Volcengine Ark (OpenAI-compatible) | openai | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed` |
| `gemini` | Google Gemini (OpenAI-compatible) | openai | Generative Language OpenAI-compatible | `gemini-3.6-flash`, `gemini-3.5-flash-lite` |
| `custom_openai` | Custom OpenAI-compatible | openai | User-supplied | (no built-in models) |

### 2.1 Aggregator and deployment-style presets

These presets cannot be judged available from a single public model name alone. MAO only provides connection templates and examples; they are not marked offline-verified:

| Preset | Key configuration | Must confirm before use |
|---|---|---|
| `openrouter` | `anthropic/claude-opus-5`, `openai/gpt-5.6-terra` | OpenRouter current model catalog, account permissions, and actual price |
| `azure-openai` | `YOUR_RESOURCE_NAME`, `YOUR_DEPLOYMENT_NAME` | Azure resource, deployment name, API version, and that deployment’s capabilities |
| `baidu-qianfan` | `qianfan-code-latest` example | Qianfan account, region, and console actual model_id |
| `siliconflow` | Platform-format Qwen/GLM examples | SiliconFlow current model catalog and account permissions |
| `stepfun` | `step-3.7-flash` example | StepFun console currently available model_id |
| `ark_openai` / `ark` | `doubao-seed-2-1-pro-260628` example | Volcengine Ark endpoint or account-allowed model identifiers |

Failures for these entries should classify as `model_not_found`, `permission_error`, or `invalid_request_error`; do not infer that the upstream official model catalog is wrong.

Local integration (`ollama` / `llamacpp`) is documented in [`local-llm-integration-and-extension-points.md`](local-llm-integration-and-extension-points.md); not in the main built-in `PROVIDER_TEMPLATES` table, but `providers.yaml.example` provides config samples. Local-model zero marginal cost is only a routing score factor and **cannot** bypass health cooldown, verified capabilities, and context capacity.

## 3. Model catalog matrix (bound to catalog)

The following rows are conceptually exported by `export_compatibility_matrix()`. After updating the catalog, sync this document and run `tests/test_provider_matrix.py`.

### 3.1 Metadata partially verified (Anthropic official docs, 2026-07-16)

| Alias | Upstream model_id | Verified capabilities | Unverified capabilities | Context tokens | Price |
|---|---|---|---|---|---|
| `claude-fable-5` | `claude-fable-5` | coding, reasoning | tool_use, vision | 1_000_000 | Catalog price; source annotated |
| `claude-opus-5` | `claude-opus-5` | coding, reasoning | tool_use, vision | 1_000_000 | Same |
| `claude-sonnet-5` | `claude-sonnet-5` | coding, reasoning | tool_use, vision | 1_000_000 | Same |
| `claude-haiku-4-5` | `claude-haiku-4-5-20251001` | chat, reasoning | tool_use, vision | 200_000 | Same |

Notes: `tool_use` / `vision` stay `unverified` until real end-to-end smoke and structured image-message acceptance. Offline native tool-turn tests do not constitute `supported`. Anthropic metadata last updated from official docs on 2026-07-26.

### 3.2 Metadata not verified (conservative by default; prices are placeholders)

| Alias | Protocol type | Declared capabilities (all unverified) | Context | Known-limit summary |
|---|---|---|---|---|
| `glm-ark` | anthropic | tool_use, coding, reasoning | Dynamic alias → 200K default | `ark-code-latest` dynamic alias |
| `glm-chat` | anthropic | tool_use, chat | Dynamic alias → 200K default | `ark-chat-latest` dynamic alias |
| `kimi-for-coding` | openai | tool_use, coding | 0 → 200K default | Placeholder price |
| `k3` | openai | coding, reasoning, tool_use, vision | 1_048_576 → 200K default | Upstream Model ID `k3`; metadata not item-verified |
| `k3-256k` | openai | coding, reasoning, tool_use | 262_144 → 200K default | Upstream Model ID `k3-256k`; metadata not item-verified |
| `kimi-for-coding-highspeed` | openai | coding, tool_use | 0 → 200K default | Upstream Model ID same as alias; placeholder price |
| `deepseek-chat` | openai | tool_use, chat, reasoning | 0 → 200K default | Placeholder price |
| `deepseek-reasoner` | openai | reasoning | 0 → 200K default | Placeholder price |
| `claude-opus-4-8` | anthropic | legacy alias | 0 → 200K default | Compatibility alias; actually sends `claude-opus-5`; no longer a default preset |
| `gpt-4o` / `gpt-4o-mini` / `gpt-5` | openai | legacy compatibility entries | 0 → 200K default | No longer default presets |
| `gpt-5.6-sol` / `gpt-5.6-terra` / `gpt-5.6-luna` | openai | see catalog | 1_050_000 → 200K default | Official catalog source; price still placeholder |
| `deepseek-v4-pro` / `deepseek-v4-flash` | openai | see catalog | 0 → 200K default | Placeholder price |
| `kimi-k3` | openai | coding, reasoning, tool_use, vision | 1_048_576 (press source, not item-verified) | Display alias; upstream Model ID `k3` |
| `kimi-k2.7-code` | openai | coding, tool_use, reasoning | 0 → 200K default | Display alias; upstream Model ID `k3-256k` |
| `kimi-k2.7` / `kimi-k2.5` | openai | see catalog | 0 → 200K default | Ordinary Moonshot-compatible config; use dedicated preset for Coding Plan |
| `glm-5` / `glm-4-flash` | openai | see catalog | 0 → 200K default | GLM-4 Flash no longer a default preset |
| `glm-5.2` | openai | see catalog | 1_000_000 → 200K default | Official catalog source; price still placeholder |
| `minimax-m2.7` | openai | legacy compatibility entry | 0 → 200K default | No longer a default preset |
| `minimax-m3` | openai | see catalog | 1_000_000 → 200K default | Official catalog source; price still placeholder |
| `qwen3-coder-plus` / `qwen3-235b-a22b` | openai | legacy compatibility entries | 0 → 200K default | No longer default presets |
| `qwen3.8-max-preview` / `qwen3.7-max` / `qwen3.7-plus` / `qwen3.7-flash` | openai | see catalog | 1_000_000 → 200K default | Official catalog source; price still placeholder |
| `doubao-seed` | openai | coding, reasoning | 0 → 200K default | Placeholder price |
| `gemini-3.1-pro` / `gemini-3.5-flash` / `gemini-3-flash` | openai | legacy compatibility entries | 0 → 200K default | No longer default presets |
| `gemini-3.6-flash` / `gemini-3.5-flash-lite` | openai | see catalog | 1_000_000 → 200K default | Official catalog source; OpenAI-compatible endpoint differences |

Full fields are authoritative via:
`python -c "from src.models.catalog import export_compatibility_matrix; import json; print(json.dumps(export_compatibility_matrix(), indent=2, ensure_ascii=False))"`

### 3.3 Model behavior configuration

The MAO gateway injects a short global behavior configuration into all ordinary `chat` and `chat_stream` requests, covering main chat, planning, Worker, and Reviewer, while keeping the session’s original messages unchanged. The configuration emphasizes tool Evidence, permission boundaries, acceptance, and not forging results. `ModelConfig.prompt_profile` remains optional and is only for future model-specific extensions.

Public Claude web-product prompts include web/mobile product info, exclusive tool schemas, and UI state; they should not be pasted into MAO API requests as-is—they raise context cost and can create wrong runtime assumptions. Global rules do not depend on model presets in `providers.yaml`, so switching models stays consistent.

## 4. Stable error codes

`ProviderError` uses redacted error codes and operational guidance. Auth/config errors do **not** enter automatic failover; short rate limits may retry; long quotas use failover.

| Error code | Meaning | Retry by default | Failover by default |
|---|---|---|---|
| `configuration_error` | Incomplete Provider or model configuration | No | No |
| `authentication_error` | Authentication failed | No | No |
| `permission_error` | Credentials lack access to model/resource | No | No |
| `model_not_found` | Model missing or endpoint unsupported | No | Yes |
| `quota_exceeded` | Quota exhausted or long-window limit | No | Yes |
| `rate_limit_error` | Short rate limit | Yes | Yes |
| `timeout_error` | Request timeout | Yes | Yes |
| `connection_error` | Cannot connect | Yes | Yes |
| `server_error` | Upstream temporarily unavailable | Yes | Yes |
| `context_length_error` | Exceeded safe context/output limit | No | No |
| `invalid_request_error` | Request parameters/format not accepted | No | No |
| `stream_interrupted` | Stream interrupted after start | No | No (no automatic replay) |
| `provider_error` | Other Provider failure | Yes | Yes |

The presentation layer exposes only `error_code`, user-readable message, and suggestions; it does not return secrets or raw upstream sensitive headers.

## 5. Security boundaries (not an OS/container sandbox)

The following control planes are **not** sandboxes and must not be described as “sandbox isolation” in UI or docs:

| Control plane | Actual meaning | Explicitly not |
|---|---|---|
| Permission modes `auto` / `approve` / `readonly` | Session-level tool gating | Container/OS isolation |
| `permissions.yaml` `deny`/`ask`/`allow` | Application-level authorization decisions | Kernel sandbox |
| Command allowlist + no shell concatenation | Reduces dangerous command surface | Process/network isolation |
| Interpreter inline/preload rejection (`safety_guards`) | Rejects arbitrary code entry points such as `python -c`/`node -e`/`-r` | Limiting privileges of already-written scripts |
| Hard reject of sensitive paths | Blocks `.env`/secret-class files from model context | Full DLP / encryption |
| `fetch_url` SSRF protection | Rejects localhost/intranet/link-local/metadata | Full defense against DNS rebinding |
| Worker path ownership | Collaboration write boundary | Multi-tenant isolation |
| Plugin `permissions` list | User-visible consent surface | Technically enforced sandbox |
| MCP / Hooks | Third-party extensions running with **MAO same-process privileges** | Isolation outside the trusted computing base |

**Recommendations**: default `approve`; use `readonly` on untrusted projects; review source and config before enabling plugins/MCP.  
See root [`SECURITY.md`](../SECURITY.md) and [`plugin-development-guide.md`](plugin-development-guide.md).

## 6. How to update this matrix

1. Only change entries and templates in `src/models/catalog.py`.
2. If a capability becomes `supported`: must fill a traceable `metadata_source` (official docs etc.) that does not contain `unverified`.
3. Run:
   ```bash
   python -m pytest -q tests/test_provider_matrix.py tests/test_model_catalog.py tests/test_explainable_model_routing.py tests/test_provider_errors.py
   ```
4. Sync the corresponding tables and “Last updated” in this document.
5. After real smoke passes, append a redacted record under `docs/acceptance/`, then upgrade capability status.

## 7. Change rules

- When matrix and catalog conflict, **catalog code** wins; fix the docs.
- Do not put `unverified` capabilities into external “supported” lists or automatic-routing savings copy.
- When adding a Provider preset: first add catalog entry → template `supported_models` → tests → tables in this document.

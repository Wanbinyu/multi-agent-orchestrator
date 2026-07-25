# Security Policy

## Supported versions

Security fixes target the latest beta release and the current `main` branch.

## Reporting a vulnerability

Use GitHub's private security advisory form. Do not include a live key, private prompt, session file, or exploit details in a public issue. Include the affected version, operating system, permission mode, minimal reproduction, and impact.

## Local trust boundary

MAO runs tools on the user's machine. **It is not a container or OS sandbox.**

Permission modes, path rules, command allowlists, and plugin enablement are **application-level authorization controls**. They reduce accidental damage and make actions reviewable; they do **not** provide process isolation, network namespace isolation, or multi-tenant security.

- `approve` is the recommended default; `readonly` removes write and command tools.
- `auto` may execute model-requested writes and commands within MAO's policy boundaries. Use it only with code and models you trust.
- Command execution uses an allowlist and rejects shell chaining (`cd &&`, pipes, redirects). It does **not** provide operating-system isolation. Inline interpreter flags such as `python -c` / `node -e` are rejected.
- `config/permissions.yaml` and project `.mao/permissions.yaml` use `deny > ask > allow` over the session default. This is a policy engine, not a sandbox.
- Worker relative writes are isolated; absolute writes require declared path ownership. This is an application boundary, not a replacement for OS permissions.
- **Plugins** run in the same Python process as MAO with the same privileges. Manifest `permissions` are a user-visible consent surface, not technical confinement. Review source before `mao plugin enable`.
- **MCP servers and hooks** are third-party code with the privileges of the MAO process. Review their configuration before enabling them.

Chinese product docs must not describe permission rules or plugin gates as “沙箱”. See [`docs/Provider兼容矩阵.md`](docs/Provider兼容矩阵.md) §5 and [`docs/插件开发指南.md`](docs/插件开发指南.md).

## Provider capabilities and errors

- Model capability and pricing truth lives in `src/models/catalog.py`. Values marked `unverified` must not drive automatic upgrades or cost-savings claims (`src/gateway/router.py`).
- Stable, redacted provider error codes include: `configuration_error`, `authentication_error`, `permission_error`, `model_not_found`, `quota_exceeded`, `rate_limit_error`, `timeout_error`, `connection_error`, `server_error`, `context_length_error`, `invalid_request_error`, `stream_interrupted`, `provider_error`.
- Authentication and configuration failures do not enter automatic failover. Short rate limits may retry; long quota windows may failover. Stream interruptions are not auto-replayed.
- Full matrix: [`docs/Provider兼容矩阵.md`](docs/Provider兼容矩阵.md).

## Secrets and private data

Keys are stored locally in `.env`; Provider YAML stores environment-variable references. `.env`, private Provider/Worker configuration, sessions, memory and output directories are ignored by Git. Users must still inspect staged changes before every push.

Rotate a key immediately if it appears in terminal output, a prompt, a session export, an issue, or Git history. Treat model prompts and tool results as potentially sensitive because they can contain source code and local paths.

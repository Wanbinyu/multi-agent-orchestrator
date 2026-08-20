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
- Command execution uses an allowlist and rejects shell chaining (`cd &&`, pipes, redirects). It does **not** provide operating-system isolation.
- Interpreter **inline and preload** forms are rejected in `run_command`, frontend smoke servers, and benchmark verification (`src/tools/safety_guards.py`): `python -c` / combined short options / stdin `-`, `node -e` / `--eval=` / `-p` / `--print`, and `node -r` / `--require` / `--import` / loaders. `python -m <module> -c …` remains allowed because `-c` belongs to the module.
- File tools hard-block common **secret paths** (`.env*`, `*.pem` / `*.key` / `*.p12`, `id_rsa` / `id_ed25519`, `.ssh` / `.aws` / `.kube` directories, etc.) so credentials are less likely to enter model context. This is a filename/path policy, not full DLP.
- Workspace `/checkpoint` snapshots are file copies beside the session. They never write the user's `.git` history, skip secret and oversized files, and restore only after an explicit confirm. The first `write_file`/`edit_file` in a run takes one automatic snapshot unless `/checkpoint auto off`. Old snapshots are pruned by count and size. Uncommitted user edits are not overwritten unless `overwrite-dirty` is given. This is **not** a sandbox and **not** `git reset`.
- `fetch_url` only allows `http`/`https` and **blocks localhost, link-local, private, and metadata targets** (including post-redirect checks). DNS rebinding and intentional public egress remain residual risks.
- `config/permissions.yaml` and project `.mao/permissions.yaml` use `deny > ask > allow` over the session default. This is a policy engine, not a sandbox.
- Worker relative writes are isolated; absolute writes require declared path ownership. This is an application boundary, not a replacement for OS permissions.
- **Plugins** run in the same Python process as MAO with the same privileges. Manifest `permissions` are a user-visible consent surface, not technical confinement. Review source before `mao plugin enable`.
- **MCP servers and hooks** are third-party code with the privileges of the MAO process. Review their configuration before enabling them.

Product docs must not describe permission rules or plugin gates as a sandbox. See [`docs/Provider-compatibility-matrix.md`](docs/Provider-compatibility-matrix.md) §5 and [`docs/plugin-development-guide.md`](docs/plugin-development-guide.md).

## Provider capabilities and errors

- Model capability and pricing truth lives in `src/models/catalog.py`. Values marked `unverified` must not drive automatic upgrades or cost-savings claims (`src/gateway/router.py`).
- Stable, redacted provider error codes include: `configuration_error`, `authentication_error`, `permission_error`, `model_not_found`, `quota_exceeded`, `rate_limit_error`, `timeout_error`, `connection_error`, `server_error`, `context_length_error`, `invalid_request_error`, `stream_interrupted`, `provider_error`.
- Authentication and configuration failures do not enter automatic failover. Short rate limits may retry; long quota windows may failover. Stream interruptions are not auto-replayed.
- Full matrix: [`docs/Provider-compatibility-matrix.md`](docs/Provider-compatibility-matrix.md).

## Secrets and private data

Keys are stored locally in `.env`; Provider YAML stores environment-variable references. `.env`, private Provider/Worker configuration, sessions, memory and output directories are ignored by Git. Users must still inspect staged changes before every push.

`read_file` / `write_file` / `edit_file` refuse paths that match the sensitive-path guard so models cannot load or rewrite typical credential files through tools. Open secrets outside MAO when you need them. Rotate a key immediately if it appears in terminal output, a prompt, a session export, an issue, or Git history. Treat model prompts and tool results as potentially sensitive because they can still contain source code and local paths.

## Logging

MAO writes application logs through `src/core/logging_setup.py` (logger name `mao.*`):

| Variable | Meaning |
|---|---|
| `MAO_LOG_LEVEL` | `DEBUG` / `INFO` (default) / `WARNING` / `ERROR` |
| `MAO_LOG_FILE` | Optional file path (UTF-8); stderr always enabled |
| `MAO_LOG_FORMAT` | `text` (default) or `json` (one object per line) |
| `MAO_TURN_TIMEOUT_SECONDS` | Agent turn wall-clock limit (default `900`; `0` disables) |

Log handlers redact common key patterns (`sk-…`, `ark-…`, `Bearer …`). **Do not** rely on logging alone for audit: RunJournal under `sessions/<id>/runs/` remains the engineering evidence store. Never put live keys into log messages intentionally.

## Residual risks (explicit)

These remain **out of scope** for the current application-level controls:

- No container/OS sandbox, network namespace, or seccomp.
- Whitelisted commands (e.g. `python script.py`, `npm`, `npx`) still run with the user's full privileges.
- Absolute project paths can still reach any path the OS allows once permission mode allows the tool; only the sensitive-name denylist is extra-hard.
- `fetch_url` cannot fully prevent DNS rebinding or data exfiltration to public URLs.
- Plugins, MCP, and hooks remain same-process / same-privilege.

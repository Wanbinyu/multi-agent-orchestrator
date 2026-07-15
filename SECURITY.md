# Security Policy

## Supported versions

Security fixes target the latest beta release and the current `main` branch.

## Reporting a vulnerability

Use GitHub's private security advisory form. Do not include a live key, private prompt, session file, or exploit details in a public issue. Include the affected version, operating system, permission mode, minimal reproduction, and impact.

## Local trust boundary

MAO runs tools on the user's machine. It is not a container sandbox:

- `approve` is the recommended default; `readonly` removes write and command tools.
- `auto` may execute model-requested writes and commands within MAO's policy boundaries. Use it only with code and models you trust.
- Command execution uses an allowlist, but it does not provide operating-system isolation.
- MCP servers and hooks are third-party code with the privileges of the MAO process. Review their configuration before enabling them.
- Worker relative writes are isolated; absolute writes require declared path ownership. This is an application boundary, not a replacement for OS permissions.

## Secrets and private data

Keys are stored locally in `.env`; Provider YAML stores environment-variable references. `.env`, private Provider/Worker configuration, sessions, memory and output directories are ignored by Git. Users must still inspect staged changes before every push.

Rotate a key immediately if it appears in terminal output, a prompt, a session export, an issue, or Git history. Treat model prompts and tool results as potentially sensitive because they can contain source code and local paths.

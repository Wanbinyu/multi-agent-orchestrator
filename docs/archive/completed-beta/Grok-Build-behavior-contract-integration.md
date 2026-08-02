# Grok Build Behavior Contract Integration

**Status**: Base contracts landed; extension ecosystem deferred to later versions

**Audit source**: xAI official open-source repo [`xai-org/grok-build`](https://github.com/xai-org/grok-build), audit baseline `98c3b2438aa922fbbe6178a5c0a4c48f85edc8ce`, Apache-2.0. Referenced config, Skills, Plugins, Hooks, project rules, Plan mode, permissions, and security docs; MAO absorbs behavior contracts only and does not copy implementations.

## 1. Implemented this round

### 1.1 Project rules

- Discover `AGENTS.md`, `Agents.md`, `CLAUDE.md`, `CLAUDE.local.md` hierarchically from project root to target directory.
- Support `.mao/rules/*.md`; compatible with `.grok/rules`, `.claude/rules`, `.cursor/rules`.
- Deeper-directory rules load later and are more specific in scope; case-insensitive dedupe on Windows.
- Caps: 8K per file, 32K total, at most 20 files; truncation and read issues record diagnostics.
- Same rule package is injected into main Agent, Orchestrator, Worker, and Reviewer; RunJournal stores source summary.
- Project rules cannot override system safety, explicit read-only bounds, Plan mode, or permission rules.

### 1.2 Permission rules

User-level rules live in `config/permissions.yaml`; project-level rules in `<project>/.mao/permissions.yaml`. Format in `config/permissions.yaml.example`.

```yaml
rules:
  - action: deny
    tool: run_command
    pattern: "rm *"
  - action: ask
    tool: write_file
    pattern: "**/*.py"
  - action: allow
    tool: run_command
    pattern: "python -m pytest *"
```

Decision priority is fixed as `deny > ask > allow > session mode default`. `readonly`, explicit “do not modify / plan only”, and Plan mode are hard ceilings no allow rule can break. Paths are normalized before matching; Windows paths unify case and separators; composite commands split on `&&`, `||`, `;`, `|`, and newlines—every segment must be allow-covered for auto-execution. Redirects, substitutions, background execution, and other complex shell still degrade to ask even if allow matches.

Main Agent and Worker call the same engine at the real tool-execution boundary. Collaboration batch approval can only satisfy session-default ask; explicit ask/deny still apply; sub-models must not approve themselves.

Permission rules now support `justification` and load-time `match/not_match` self-checks. This increment draws on Codex execpolicy’s verifiable-rule ideas and is independently implemented; rules that fail self-check are excluded with diagnostics. Fuller upstream comparison: [`open-source-coding-agent-reference-plan.md`](../../open-source-coding-agent-reference-plan.md).

### 1.3 Persistent Plan mode

Session state is `inactive / pending / active / awaiting_approval`; plan content, revision notes, version, and council sources write to Session YAML and restore after restart. Before Plan approval:

- Main Agent only exposes and runs read-only tools.
- Forbid write commands, MCP write ops, automatic `response.md`, and write Workers.
- Only allow updating the current session’s Plan artifact.
- Project rules and session `auto` cannot relax the boundary.

CLI: `/plan enter [goal]`, `/plan show`, `/plan revise <notes>`, `/plan approve`, `/plan cancel`. Legacy one-shot `/plan <request>` stays compatible. Web provides equivalent state controls and `GET/POST /api/chat/sessions/{id}/plan`.

### 1.4 Multi-model planning Council

Plan draft first uses real read-only tools for main-Agent recon, then a no-tools council:

1. `reconnaissance`: check evidence, constraints, and unknowns.
2. `architect`: form a bounded, acceptably verifiable implementation plan.
3. `critic`: challenge overreach risk, omissions, dependencies, rollback, and insufficient tests.
4. `synthesizer`: main model synthesizes the single final plan.

All four roles receive the same project rules, permission summary, and evidence bounds, without tool definitions. Failure of any auxiliary role only records diagnostics; synthesis failure keeps the main Agent draft so a single model fault does not destroy the whole Plan.

## 2. Risks explicitly not copied

- Must not only hide edit tools: MAO intercepts shell, MCP, and Worker at the execution boundary.
- Parent Plan mode must constrain sub-models; Workers must not bypass.
- Path rules must not match un-normalized strings directly.
- Permission/security Hooks do not default fail-open.
- No online plugin marketplace yet; finish trust sources, signing, and isolation bounds first.

## 3. Follow-on absorption order

1. B4.S: First use real tasks to fix classification, dynamic audit, portable verification, and frontend smoke—see [`real-task-stability-improvement-plan.md`](real-task-stability-improvement-plan.md).
2. B4: Add rule-source view command, recover unfinished Plans, Reviewer information-restriction verification.
3. B5: Settings registry (types, defaults, live vs restart-required), richer lifecycle Hooks.
4. B6: Skills/Plugins source, trust, version, and capability declarations; Plugin API v0.
5. Plugin marketplace only after signing, permission manifests, isolated execution, and revocation mechanisms are complete.

## 4. Current acceptance

- Project rules, permission rules, Plan state, Council, and CLI/Web controls all have offline tests.
- Browser acceptance covers 1280×720 and 390×844: no horizontal overflow, Plan status strip does not cover the input area, console error-free.
- No real paid models called.

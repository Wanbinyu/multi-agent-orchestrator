# MAO Quickstart

MAO is a local, self-hostable, evidence-driven multi-model engineering agent. It connects multiple model services, executes bounded engineering tools, splits complex tasks, preserves evidence, and runs a deterministic completion audit before declaring a task done.

This is a beta release (`v0.1.0-beta.7`). It is meant for trusted local machines and reviewable projects, not a drop-in replacement for Claude Code, Codex, or a container sandbox.

**Trust boundary:** permission modes (`auto` / `approve` / `readonly`), path rules, command allowlists, and plugin enablement are application-level authorization controls. They are **not** an OS/container sandbox. Plugins and MCP servers run with the same privileges as the MAO process. Prefer `approve` by default; use `readonly` for untrusted trees. Capability and pricing truth for presets lives in `src/models/catalog.py`; values marked `unverified` do not drive automatic model upgrades or savings claims. See [`Provider-compatibility-matrix.md`](Provider-compatibility-matrix.md) and [`../SECURITY.md`](../SECURITY.md).

## 1. Install

Python 3.11 or 3.12 is required.

```bash
pipx install git+https://github.com/Wanbinyu/multi-agent-orchestrator.git@v0.1.0-beta.7
mao --version
```

Source development:

```bash
git clone https://github.com/Wanbinyu/multi-agent-orchestrator.git
cd multi-agent-orchestrator
python -m pip install -e ".[test]"
mao
```

## 2. Configure a Provider

Run `mao` in a terminal. On first run, MAO starts a setup wizard to connect one model service:

- Choose a provider preset (Anthropic Claude, OpenAI, DeepSeek, GLM, Kimi, Qwen, MiniMax, Doubao, Gemini, or a custom OpenAI/Anthropic-compatible endpoint).
- Enter the API key. Keys are stored only in the local `.env` file and are never committed.
- Pick the main model.

Alternatively, open the WebUI and configure visually:

```bash
mao web
```

Verify a connection from the WebUI's provider page before starting a real task.

## 3. First task

Interactive chat:

```bash
mao
```

One-shot orchestration:

```bash
mao run "Inspect the current project and report risks"
```

For scripts and headless automation, use machine-readable events:

```bash
mao run "Inspect the current project and report risks" --output-format json
mao run "Inspect the current project and report risks" --output-format streaming-json
```

`json` emits one object containing the run summary and events. `streaming-json` emits JSONL lines as the run progresses. Both include plan, model, tool, file-change, command, verification, approval, usage, error, and end events; Worker response bodies are excluded.

Permission modes (Shift+Tab in the CLI, or set per session):

- `auto` — executes allowed tools without a second gate.
- `approve` — asks before non-read tools.
- `readonly` — reads only, rejects writes and commands.

MAO classifies each request (question, diagnosis, small change, build, review, migration). Read-only intents stay read-only; modifications and builds follow the session mode and trigger engineering verification.

## 4. Evidence and completion

MAO does not mark a task complete without direct evidence. A run records:

- `WorkPlan`, `Evidence`, `VerificationGate`, `RequirementCheck`, `CompletionAudit`.
- The model's "done" cannot override a failed deterministic audit.

Inspect engineering state in the CLI (`/runs`, `/report session|today`) or the WebUI run details and delivery reports. Reports aggregate local run journals without spending tokens.

## 5. Multi-model collaboration

Complex tasks can enter collaboration: Orchestrator -> Dispatcher -> Worker -> (optional AdversarialTester) -> Reviewer, with dependency and path-ownership boundaries. Execution depth (`/depth auto|fast|standard|deep`) bounds tool rounds, context, Worker concurrency, and verification. Routing (`/routing fixed` to pin the main model) selects models from verified capability, traceable price, context, and health.

## 6. Plugins

Plugins are disabled by default. Install a plugin package declaring a `mao.plugins` entry point, then enable it:

```bash
mao plugin list
mao plugin enable <id>
mao plugin doctor
mao
mao plugin disable <id>
```

Python plugins run as trusted local code with the same privileges as MAO; permissions are a consent surface, not a sandbox. See the [Plugin development guide](plugin-development-guide.md) and the [example plugin](../examples/plugins/mao_wordcount_plugin).

## 7. What is not done yet

- No authorized real-model effectiveness data; cost/completion-rate advantages are not advertised.
- No container/OS sandbox for tool execution.
- The plugin marketplace and model-recommended auto-install are intentionally absent.

## 8. Next

- Architecture: [`MAO-architecture-overview.md`](MAO-architecture-overview.md)
- Current optimization plan: [`MAO-optimization-and-follow-up-plan.md`](MAO-optimization-and-follow-up-plan.md)
- Historical version plan: [`archive/completed-beta/version-plan-v0.1.0-beta.3-to-beta.6.md`](archive/completed-beta/version-plan-v0.1.0-beta.3-to-beta.6.md)
- Release notes: [`RELEASE_NOTES_v0.1.0-beta.6.md`](RELEASE_NOTES_v0.1.0-beta.6.md)
- Contributing: [`CONTRIBUTING.md`](../CONTRIBUTING.md)

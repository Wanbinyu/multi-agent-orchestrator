# External User Feedback Guide (Redacted)

**Status**: Current (O4)  
**Updated**: 2026-07-28  
**Applies to**: install issues, real project task outcomes, Provider compatibility issues, ordinary defects  

This guide helps you give feedback on MAO **without leaking secrets or project confidential data**. The collection goal is external install and real-task evidence for the v0.2.0 entry criteria — not uploading your code or billing data.

## 1. Never Paste

| Category | Examples |
|---|---|
| Secrets | `sk-...`, `ark-...`, `Bearer ...`, full `.env` |
| Session and run state | `sessions/**`, `memory/**`, full RunJournal JSON |
| Project secrets | Customer names, internal URLs, unreleased business source, DB connection strings |
| Identifying paths | The real name segment in `C:\Users\RealName\...` (use `C:\Users\<user>\project`) |

If a secret was already pasted into a public Issue: **rotate** it immediately in the Provider console, and edit/delete that comment.

## 2. Recommended Submission Channels

In the repo **New Issue**, pick a template:

| Template | When to use |
|---|---|
| **Install / first-time setup feedback** | pipx failed, command missing, Web won't start, Provider won't configure |
| **Real project task feedback** | You completed or failed a task on a real repo (O4 core) |
| **Bug report** | Reproducible product defect |
| **Provider compatibility** | A model/streaming/tool protocol incompatibility |
| **Security advisory** | Security vulnerability → use the private channel; do not open a public Issue |

You can also redaction-sanitize text locally first:

```bash
# inside the source tree
python scripts/sanitize_feedback_text.py path\to\log.txt

# or pipe
type log.txt | python scripts/sanitize_feedback_text.py
```

## 3. Minimum Diagnostic Info (Default Fields)

Almost every report should include:

1. **MAO version**: `mao --version`  
2. **OS**: Windows / Ubuntu / macOS  
3. **Python**: `python --version`  
4. **Install method**: pipx / source editable  
5. **Permission mode**: `approve` / `readonly` / `auto`  
6. **Stable error code** (if any): `authentication_error`, `connection_error`, `invalid_request_error`, `quota_exceeded`, etc.  
7. **Redacted reproduction commands** (no keys)  

Optional:

- Provider **family** ("Volcano Coding Plan", "OpenAI-compatible") — not account IDs  
- Primary model **alias** (name in config)  
- Whether project files were modified by mistake (yes/no)  
- Whether you would use it again (yes / unsure / no)  

## 4. How to Write Useful Real-Task Feedback

Good example (redacted):

```text
Version: MAO 0.1.0b7 / Windows / Python 3.11
Entry: mao chat, permission approve
Task: read-only map frontend src/routes structure (no business names)
Provider family: OpenAI-compatible; model alias: my-main
Result: completed; ~6 read_file calls, no writes
Friction: first setup Base URL missed /v1
Would use again: yes
```

Bad example:

```text
Key is sk-xxxxx, project is D:\CustomerA\secret-system, log attached as session.yaml
```

## 5. Prefer Self-Checks on Install Failure

```bash
mao --version
mao web --help
# source developers:
python scripts/first_run_acceptance.py
python scripts/verify_distribution.py
```

Full empty-directory path: [`acceptance/first-install-acceptance-checklist.md`](acceptance/first-install-acceptance-checklist.md).

## 6. How Maintainers Use Feedback

- Install Issues → count toward "successful install" (condition #1) only if you can tell **whether install reached the config page**.  
- Real-task Issues → count toward "real project task" only with task type + outcome + permission mode, and no secrets.  
- Do not turn a single success or unauthorized paid smoke into a product completion-rate claim.  
- When reproduction is needed, prefer error codes and minimal commands over a copy of the user's project.  

## 7. Related Links

- Issue templates: `.github/ISSUE_TEMPLATE/`  
- Security reports: [`SECURITY.md`](../SECURITY.md)  
- Provider error codes: [`Provider-compatibility-matrix.md`](Provider-compatibility-matrix.md)  
- Redaction script: `scripts/sanitize_feedback_text.py`  

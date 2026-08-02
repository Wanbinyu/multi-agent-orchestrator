# First-Install Acceptance Checklist (Empty Directory / New Project)

**Status**: Current  
**Updated**: 2026-07-28  
**Baseline**: `v0.1.0b7` / `main`  
**Goal**: Anyone who clones or installs via pipx can, in **their own empty project directory**, within 10 minutes complete: install confirmation → open config UI → (optional) enter their own Key → read-only task.

> Principle: no real API keys on GitHub; keys appear only in local `.env` / local `config/providers.yaml` (both gitignored).

## 1. Automated Commands

```bash
# Distribution: clean venv + empty-dir CLI/Web (zero Provider)
python scripts/verify_distribution.py

# Empty-dir first-run path (zero Provider; recommended after any entry-point change)
python scripts/first_run_acceptance.py

# Extra: one read-only Agent turn with local Key (does not print secrets; failure does not block offline gates by default)
python scripts/first_run_acceptance.py --with-live

# If live must also succeed:
python scripts/first_run_acceptance.py --with-live --require-live
```

## 2. Manual 10-Minute Path

In **any empty project directory** (do not pile business code into the install directory):

| Step | Action | Expected |
|---|---|---|
| 1 | `pipx install git+https://github.com/Wanbinyu/multi-agent-orchestrator.git` or source `pip install -e .` | Install succeeds |
| 2 | `mao --version` | Prints `MAO 0.1.0b7` (or current version) |
| 3 | Empty-dir non-interactive `mao` (no TTY) | Exit code **2**, prompts to use `mao web` or interactive terminal; **writes no files** |
| 4 | `mao web --no-open` | `GET /health` → `{"status":"ok"}`; home page can configure Provider |
| 5 | Enter **your own** Key in Web/wizard and save | Creates only in-project `.env` + `config/providers.yaml` (do not commit) |
| 6 | Prefer permission `readonly` or `approve` | Do not use `auto` for first task |
| 7 | Ask: "Read-only list files in the current directory; do not modify" | Structured/readable reply; no writes to target project |

## 3. 2026-07-28 Local Run Results

**Environment**: Windows, Python 3.11.9, source tree `E:\multi-agent-orchestrator`.

| Check | Result | Notes |
|---|---|---|
| `python scripts/verify_distribution.py` | ✅ Pass | wheel/sdist, twine, clean venv CLI, Web health, example plugin |
| `python scripts/first_run_acceptance.py` | ✅ Pass | version/help/first-start exit 2/Web health/sensitive path hard reject |
| `python scripts/first_run_acceptance.py --with-live` | ⚠ Offline gates pass; live Agent failed locally | See "Local Provider status" below |
| Sensitive path `.env` read/write | ✅ Blocked | `error_code=sensitive_path`; no secret leak |

### Local Provider Status (No Public Secrets)

At probe time (redacted):

- **Volcano Coding Plan (ark / volcengineark)**: `InvalidSubscription` — account CodingPlan not subscribed or expired; renew/enable in Volcano console.
- **kimi (anthropic protocol)**: `INVALID_API_KEY`.
- **kimi1 (openai-compatible proxy)**: minimal `chat.completions` works; full Agent turn may fail if `base_url` lacks `/v1` or endpoint returns HTML. Product already gives a clear error for "HTML not JSON".

**Conclusions**:

1. **Product empty-directory install path works** (no paid Key required).  
2. **"Configure Key → read-only success" depends on the user's valid Provider**; on the current dev machine the primary Coding Plan is expired — owner must fix subscription or switch to a working model before live green.  
3. This does not block the "stranger installs + uses their own Key" narrative; O4 should still invite external users to accept with **their own** plans.

## 4. Acceptance Pass Criteria

| Gate | Required |
|---|---|
| Offline / distribution | `verify_distribution.py` and `first_run_acceptance.py` exit 0 |
| Manual | Empty dir can open Web config page; unconfigured CLI behavior matches table |
| Live (optional) | At least one Provider connects + one readonly Agent turn with body text; secrets never appear in logs |

## 5. Fix-on-Find Priority

1. First-start copy/exit-code regressions (already locked by scripts)  
2. OpenAI-compatible `base_url` missing `/v1` messaging (error copy exists; config UI can prefill hint)  
3. Local Key/subscription issues → **user side**, do not commit to repo  
4. Do not push `work/`, `.env`, or real `providers.yaml` to GitHub  

## 6. Related Entry Points

- Distribution: `scripts/verify_distribution.py`  
- First run: `scripts/first_run_acceptance.py`  
- Security boundaries: `SECURITY.md`, `src/tools/safety_guards.py`  
- Progress: `docs/project-progress-and-key-operations.md`  

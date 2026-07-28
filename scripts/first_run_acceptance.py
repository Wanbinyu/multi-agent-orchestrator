"""Empty-directory first-run acceptance for MAO (offline + optional live smoke).

Does NOT print API keys or write secrets into the repo. Live steps only run when
explicitly requested and required environment variables are present.

Usage:
  python scripts/first_run_acceptance.py
  python scripts/first_run_acceptance.py --with-live
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str = ""
    elapsed_ms: int = 0


@dataclass
class Report:
    started_at: str
    finished_at: str = ""
    python: str = ""
    mao_version: str = ""
    steps: list[StepResult] = field(default_factory=list)
    live_attempted: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def offline_ok(self) -> bool:
        return all(
            step.ok
            for step in self.steps
            if not step.name.startswith("live ")
        )

    @property
    def live_ok(self) -> bool | None:
        live_steps = [step for step in self.steps if step.name.startswith("live ")]
        if not live_steps:
            return None
        return all(step.ok for step in live_steps)

    @property
    def ok(self) -> bool:
        # Product install gate is offline; live is reported separately (env/keys).
        return self.offline_ok


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    stdin: int | None = subprocess.DEVNULL,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        stdin=stdin,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_json(url: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - probe loop
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {url}: {type(last_error).__name__}")


def _timed(name: str, fn) -> StepResult:
    started = time.perf_counter()
    try:
        detail = fn() or ""
        return StepResult(
            name=name,
            ok=True,
            detail=str(detail),
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )
    except Exception as exc:  # noqa: BLE001 - record step failure
        return StepResult(
            name=name,
            ok=False,
            detail=f"{type(exc).__name__}: {exc}",
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "NO_COLOR": "1",
            "TERM": "dumb",
        }
    )
    return env


def _resolve_mao_command() -> list[str]:
    # Prefer the local source entrypoint so acceptance matches the current tree.
    return [sys.executable, str(ROOT / "run.py")]


def _write_minimal_project(project: Path) -> None:
    project.mkdir(parents=True, exist_ok=True)
    (project / "README.md").write_text(
        "# First-run sample project\n\nUsed only for MAO empty-directory acceptance.\n",
        encoding="utf-8",
    )
    (project / "hello.py").write_text(
        '"""Tiny sample for readonly inspection."""\n\n\ndef greet(name: str = "MAO") -> str:\n'
        '    return f"hello {name}"\n',
        encoding="utf-8",
    )


def _resolve_live_key_env(env: dict[str, str]) -> tuple[str, str]:
    """Return (env_var_name, value) for a usable live key without logging value."""
    for name in (
        "ARK_CODING_TOKEN",
        "ARK_API_KEY",
        "VOLCENGINEARK_API_KEY",
        "KIMI_API_KEY",
    ):
        value = (env.get(name) or "").strip()
        if value:
            return name, value
    return "", ""


def _write_placeholder_provider_config(project: Path, key_env_name: str) -> None:
    """Write providers.yaml that references env vars only (no literal keys)."""
    config_dir = project / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    # Match common owner Coding Plan shape; still only ${ENV} placeholders.
    if key_env_name == "KIMI_API_KEY":
        content = f"""# Generated by first_run_acceptance.py — uses env refs only.
main_model: kimi-for-coding
providers:
  kimi:
    name: kimi
    type: openai
    base_url: https://api.moonshot.cn/v1
    api_keys:
      - "${{{key_env_name}}}"
    timeout: 60
models:
  kimi-for-coding:
    provider: kimi
    model_id: kimi-for-coding
    input_price_per_1m: 0
    output_price_per_1m: 0
    capabilities: [tool_use, coding]
    capability_status:
      tool_use: unverified
      coding: unverified
    metadata_source: unverified
    context_window_tokens: 0
    max_output_tokens: 2048
"""
    else:
        content = f"""# Generated by first_run_acceptance.py — uses env refs only.
main_model: glm-ark
providers:
  volcengineark:
    name: volcengineark
    type: anthropic
    base_url: https://ark.cn-beijing.volces.com/api/coding
    api_keys:
      - "${{{key_env_name}}}"
    timeout: 60
models:
  glm-ark:
    provider: volcengineark
    model_id: ark-code-latest
    input_price_per_1m: 0
    output_price_per_1m: 0
    capabilities: [tool_use, coding, reasoning]
    capability_status:
      tool_use: unverified
      coding: unverified
      reasoning: unverified
    metadata_source: unverified
    context_window_tokens: 0
    max_output_tokens: 2048
"""
    (config_dir / "providers.yaml").write_text(content, encoding="utf-8")
    # Do not create .env here; inherit from process environment only when --with-live.


def run_offline(report: Report, project: Path, mao: list[str], env: dict[str, str]) -> None:
    def version() -> str:
        result = _run([*mao, "--version"], cwd=project, env=env)
        if result.returncode != 0:
            raise RuntimeError(result.stdout + result.stderr)
        report.mao_version = (result.stdout or result.stderr).strip()
        return report.mao_version

    def help_cmd() -> str:
        result = _run([*mao, "--help"], cwd=project, env=env)
        if result.returncode != 0:
            raise RuntimeError(result.stdout + result.stderr)
        text = result.stdout + result.stderr
        for token in ("run", "web", "plugin", "chat"):
            if token not in text:
                raise RuntimeError(f"help missing command: {token}")
        return "help lists core commands"

    def noninteractive_first_run() -> str:
        # Fresh subdir without config
        empty = project / "_empty_cli"
        empty.mkdir(exist_ok=True)
        result = _run(mao, cwd=empty, env=env)
        if result.returncode != 2:
            raise RuntimeError(
                f"expected exit 2, got {result.returncode}: "
                f"{result.stdout}\n{result.stderr}"
            )
        text = result.stdout + result.stderr
        if "mao web" not in text and "Provider" not in text:
            raise RuntimeError(f"unexpected first-run message: {text!r}")
        written = [p.name for p in empty.iterdir()]
        if written:
            raise RuntimeError(f"first run wrote files: {written}")
        return "non-interactive first run exits 2 and writes nothing"

    def web_health() -> str:
        port = _free_port()
        process = subprocess.Popen(
            [*mao, "web", "--no-open", "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(project),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            health = _wait_for_json(f"http://127.0.0.1:{port}/health")
            if health.get("status") != "ok":
                raise RuntimeError(f"health={health}")
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:
                page = resp.read().decode("utf-8", errors="replace")
            if "模型" not in page and "Provider" not in page and "配置" not in page:
                raise RuntimeError("config page missing expected Chinese labels")
            return f"web /health ok on port {port}"
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def sensitive_path_guard() -> str:
        # Import from source tree for offline guard smoke (distribution uses installed package).
        sys.path.insert(0, str(ROOT))
        from src.tools.worker_tools import read_file, write_file

        env_path = project / ".env"
        env_path.write_text("SHOULD_NOT_LEAK=1\n", encoding="utf-8")
        read = read_file(".env", str(project))
        if read.success or (read.metadata or {}).get("error_code") != "sensitive_path":
            raise RuntimeError(f"read_file should block .env: {read}")
        write = write_file(".env.local", "x=1\n", str(project))
        if write.success or (write.metadata or {}).get("error_code") != "sensitive_path":
            raise RuntimeError(f"write_file should block .env.local: {write}")
        if "SHOULD_NOT_LEAK" in (read.output or "") or "SHOULD_NOT_LEAK" in (read.error or ""):
            raise RuntimeError("secret value leaked into tool result")
        return "sensitive path hard-block works"

    report.steps.append(_timed("mao --version", version))
    report.steps.append(_timed("mao --help", help_cmd))
    report.steps.append(_timed("noninteractive first-run (no config)", noninteractive_first_run))
    report.steps.append(_timed("web health without provider config", web_health))
    report.steps.append(_timed("sensitive path guard on sample project", sensitive_path_guard))


def _load_dotenv_into(env: dict[str, str], path: Path) -> list[str]:
    """Load KEY=VALUE from a local .env into env dict; return names only."""
    loaded: list[str] = []
    if not path.is_file():
        return loaded
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        name, value = raw.split("=", 1)
        name, value = name.strip(), value.strip().strip('"').strip("'")
        if not name or not value:
            continue
        env[name] = value
        loaded.append(name)
    return loaded


def _resolve_key_from_ref(raw_ref: str, env: dict[str, str]) -> str:
    import re

    text = str(raw_ref).strip()
    match = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", text)
    if match:
        return (env.get(match.group(1)) or os.environ.get(match.group(1)) or "").strip()
    expanded = os.path.expandvars(text)
    if expanded and "${" not in expanded:
        return expanded.strip()
    return (env.get(text) or "").strip()


def _pick_working_model(data: dict, env: dict[str, str]) -> tuple[str, str, str, list[str]]:
    """Return (model_alias, provider_name, model_id, secrets_used) for first healthy pair."""
    sys.path.insert(0, str(ROOT))
    from src.gateway.connection_test import check_provider_connection

    providers = data.get("providers") or {}
    models = data.get("models") or {}
    secrets: list[str] = []
    failures: list[str] = []

    # Prefer configured main_model, then remaining models.
    order: list[str] = []
    main = data.get("main_model")
    if isinstance(main, str) and main in models:
        order.append(main)
    for alias in models:
        if alias not in order:
            order.append(alias)

    for alias in order:
        model = models.get(alias)
        if not isinstance(model, dict):
            continue
        provider_name = str(model.get("provider") or "")
        cfg = providers.get(provider_name)
        if not isinstance(cfg, dict):
            continue
        keys = cfg.get("api_keys") or []
        if not keys:
            failures.append(f"{alias}: no api_keys")
            continue
        key = _resolve_key_from_ref(str(keys[0]), env)
        if not key:
            failures.append(f"{alias}: empty key after env expand")
            continue
        secrets.append(key)
        model_id = str(model.get("model_id") or alias)
        base = str(cfg.get("base_url") or "")
        bases = [base]
        if str(cfg.get("type")) == "openai" and base and not base.rstrip("/").endswith("/v1"):
            bases.append(base.rstrip("/") + "/v1")
        for candidate_base in bases:
            result = check_provider_connection(
                provider_type=str(cfg.get("type") or "openai"),
                api_key=key,
                base_url=candidate_base,
                model_id=model_id,
                timeout=45,
            )
            if result.success:
                if candidate_base != base:
                    cfg["base_url"] = candidate_base
                    providers[provider_name] = cfg
                    data["providers"] = providers
                return alias, provider_name, model_id, secrets
            code = result.error_code or "error"
            failures.append(f"{alias}:{code}")

    # Last resort: provider-only probe (orphan providers without model map).
    candidate_ids = []
    for model in models.values():
        if isinstance(model, dict) and model.get("model_id"):
            candidate_ids.append(str(model.get("model_id")))
    candidate_ids.extend(["kimi-for-coding", "ark-code-latest", "moonshot-v1-8k"])

    for provider_name, cfg in providers.items():
        if not isinstance(cfg, dict):
            continue
        keys = cfg.get("api_keys") or []
        if not keys:
            continue
        key = _resolve_key_from_ref(str(keys[0]), env)
        if not key:
            continue
        secrets.append(key)
        tried: set[str] = set()
        for model_id in candidate_ids:
            if not model_id or model_id in tried:
                continue
            tried.add(model_id)
            base = str(cfg.get("base_url") or "")
            bases = [base]
            if str(cfg.get("type")) == "openai" and base and not base.rstrip("/").endswith("/v1"):
                bases.append(base.rstrip("/") + "/v1")
            for candidate_base in bases:
                result = check_provider_connection(
                    provider_type=str(cfg.get("type") or "openai"),
                    api_key=key,
                    base_url=candidate_base,
                    model_id=model_id,
                    timeout=45,
                )
                if result.success:
                    if candidate_base != base:
                        cfg["base_url"] = candidate_base
                        providers[provider_name] = cfg
                        data["providers"] = providers
                    alias = f"live-{provider_name}"
                    models[alias] = {
                        "provider": provider_name,
                        "model_id": model_id,
                        "input_price_per_1m": 0,
                        "output_price_per_1m": 0,
                        "capabilities": ["chat"],
                        "capability_status": {"chat": "unverified"},
                        "metadata_source": "unverified",
                        "context_window_tokens": 0,
                        "max_output_tokens": 2048,
                    }
                    data["models"] = models
                    data["main_model"] = alias
                    return alias, provider_name, model_id, secrets
                failures.append(
                    f"provider:{provider_name}/{model_id}:{result.error_code or 'error'}"
                )

    raise RuntimeError("no healthy provider/model; tried " + ", ".join(failures[:16]))


def run_live(report: Report, project: Path, mao: list[str], env: dict[str, str]) -> None:
    report.live_attempted = True
    env = dict(env)
    loaded = _load_dotenv_into(env, ROOT / ".env")
    if loaded:
        report.notes.append(f"Loaded {len(loaded)} names from repo .env (values not logged)")

    local_cfg = ROOT / "config" / "providers.yaml"
    config_dir = project / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    if local_cfg.is_file():
        # Owner/local shape only; file is gitignored and should use ${ENV} refs.
        (config_dir / "providers.yaml").write_text(
            local_cfg.read_text(encoding="utf-8"), encoding="utf-8"
        )
        report.notes.append("Live config copied from local config/providers.yaml (gitignored)")
    else:
        key_env_name, key_value = _resolve_live_key_env(env)
        if not key_env_name:
            report.steps.append(
                StepResult(
                    name="live provider smoke",
                    ok=False,
                    detail=(
                        "fail: no local providers.yaml and no live key env among "
                        "ARK_CODING_TOKEN / ARK_API_KEY / VOLCENGINEARK_API_KEY / KIMI_API_KEY"
                    ),
                )
            )
            return
        env[key_env_name] = key_value
        _write_placeholder_provider_config(project, key_env_name)
        report.notes.append(f"Live key source env var: {key_env_name} (value not logged)")

    def connection_and_readonly() -> str:
        import yaml

        # Child tools/gateway resolve env at process level.
        for key, value in env.items():
            if value and key not in os.environ:
                os.environ[key] = value
            elif value:
                os.environ[key] = value

        config_path = project / "config" / "providers.yaml"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        alias, provider_name, model_id, secrets = _pick_working_model(data, env)
        data["main_model"] = alias
        # OpenAI-compatible agent calls are sensitive to missing /v1; normalize when safe.
        providers = data.get("providers") or {}
        cfg = providers.get(provider_name)
        if isinstance(cfg, dict) and str(cfg.get("type")) == "openai":
            base = str(cfg.get("base_url") or "").rstrip("/")
            if base and not base.endswith("/v1"):
                cfg["base_url"] = base + "/v1"
                providers[provider_name] = cfg
                data["providers"] = providers
        config_path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        # First real user task path: single-agent readonly turn (not multi-worker mao run).
        sys.path.insert(0, str(ROOT))
        from src.core.agent import Agent
        from src.core.session import SessionStore
        from src.gateway.client import GatewayClient

        prev_cwd = Path.cwd()
        try:
            os.chdir(project)
            gateway = GatewayClient(config_path=str(config_path))
            if hasattr(gateway, "main_model"):
                gateway.main_model = alias
            store = SessionStore(base_dir=str(project / "sessions"))
            session = store.create(title="first-run-acceptance")
            session.approval_mode = "readonly"
            session.config_dir = str(config_dir)
            store.save(session)
            agent = Agent(gateway, session, approval_mode="readonly")
            result = agent.run_turn(
                "只读检查当前目录有哪些文件，列出文件名即可，不要修改任何文件，不要运行命令。"
            )
        finally:
            os.chdir(prev_cwd)

        text = ""
        if result is not None:
            text = str(getattr(result, "assistant_message", "") or "")
        for secret in secrets:
            if secret and secret in text:
                raise RuntimeError("secret leaked into agent response")
        # Soft content check: should mention sample project files.
        lowered = text.casefold()
        if not any(token in lowered for token in ("readme", "hello.py", "hello", "文件")):
            # Still accept if turn completed with non-empty text (model wording varies).
            if len(text.strip()) < 8:
                raise RuntimeError(f"empty or too-short agent reply: {text!r}")
        return (
            f"connection ok provider={provider_name} model={alias}/{model_id}; "
            f"readonly agent turn chars={len(text)}"
        )

    report.steps.append(
        _timed("live connection + readonly agent turn", connection_and_readonly)
    )
    if not report.steps[-1].ok:
        report.notes.append(
            "Live step failed due to Provider/env (subscription, key, or base_url). "
            "Offline first-run gate is independent."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="MAO empty-directory first-run acceptance")
    parser.add_argument(
        "--with-live",
        action="store_true",
        help="Also run provider connection + one-shot readonly agent turn (uses env keys, never prints them)",
    )
    parser.add_argument(
        "--require-live",
        action="store_true",
        help="Exit non-zero if live step fails (default: only offline gate blocks)",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep the temporary project directory (path printed in report notes)",
    )
    args = parser.parse_args()

    report = Report(
        started_at=datetime.now(timezone.utc).isoformat(),
        python=sys.version.split()[0],
    )
    mao = _resolve_mao_command()
    env = _base_env()

    temp_root = Path(tempfile.mkdtemp(prefix="mao-first-run-"))
    project = temp_root / "sample-project"
    try:
        _write_minimal_project(project)
        run_offline(report, project, mao, env)
        if args.with_live:
            run_live(report, project, mao, env)
        else:
            report.notes.append("Live provider steps skipped (pass --with-live to enable).")
    finally:
        report.finished_at = datetime.now(timezone.utc).isoformat()
        if args.keep:
            report.notes.append(f"Kept workspace: {project}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)
            report.notes.append("Temporary workspace deleted.")

    payload = asdict(report)
    payload["ok"] = report.ok
    payload["offline_ok"] = report.offline_ok
    payload["live_ok"] = report.live_ok
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not report.offline_ok:
        return 1
    if args.require_live and report.live_ok is False:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

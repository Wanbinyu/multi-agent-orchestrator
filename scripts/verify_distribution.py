"""Build and smoke-test MAO distributions in an isolated temporary directory."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import venv
import zipfile


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_WHEEL_FILES = {
    "src/resources/workers.yaml.example",
    "src/ui/templates/index.html",
    "src/ui/templates/chat.html",
    "src/ui/static/css/style.css",
    "src/ui/static/js/app.js",
    "src/ui/static/js/chat.js",
}
FORBIDDEN_DISTRIBUTION_PARTS = {"tests", "docs", ".github", "reference-opencode"}


def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        **kwargs,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _assert_archive_contract(wheel: Path, sdist: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())
        missing = REQUIRED_WHEEL_FILES - wheel_names
        assert not missing, f"wheel missing runtime assets: {sorted(missing)}"
        assert not any(
            set(Path(name).parts) & FORBIDDEN_DISTRIBUTION_PARTS
            for name in wheel_names
        ), "wheel contains development-only files"
        metadata_name = next(name for name in wheel_names if name.endswith(".dist-info/METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")
        assert "Name: multi-agent-orchestrator" in metadata
        assert "Requires-Python: >=3.11" in metadata

    with tarfile.open(sdist, "r:gz") as archive:
        sdist_names = archive.getnames()
        assert not any(
            set(Path(name).parts[1:]) & FORBIDDEN_DISTRIBUTION_PARTS
            for name in sdist_names
        ), "sdist contains development-only files"


def _entrypoint(venv_dir: Path, name: str) -> Path:
    scripts_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    suffix = ".exe" if os.name == "nt" else ""
    return scripts_dir / f"{name}{suffix}"


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
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {url}: {type(last_error).__name__}")


def _smoke_installed_wheel(wheel: Path, temp_root: Path) -> None:
    venv_dir = temp_root / "venv"
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(venv_dir)
    python = _entrypoint(venv_dir, "python")
    _run([str(python), "-m", "pip", "install", "--force-reinstall", str(wheel)])

    mao = _entrypoint(venv_dir, "mao")
    clean_dir = temp_root / "clean-workspace"
    clean_dir.mkdir()
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"})

    for args in (["--version"], ["--help"], ["web", "--help"]):
        _run([str(mao), *args], cwd=clean_dir, env=env)

    first_run = subprocess.run(
        [str(mao)],
        cwd=clean_dir,
        env=env,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    assert first_run.returncode == 2, first_run.stdout + first_run.stderr
    first_run_output = first_run.stdout + first_run.stderr
    assert "mao web" in first_run_output
    assert list(clean_dir.iterdir()) == [], "non-interactive first run wrote unexpected files"

    port = _free_port()
    process = subprocess.Popen(
        [str(mao), "web", "--no-open", "--host", "127.0.0.1", "--port", str(port)],
        cwd=clean_dir,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_for_json(f"http://127.0.0.1:{port}/health") == {"status": "ok"}
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
            page = response.read().decode("utf-8")
        assert "模型连接配置" in page
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mao-dist-") as temp:
        temp_root = Path(temp)
        dist_dir = temp_root / "dist"
        _run(
            [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(dist_dir)],
            cwd=ROOT,
        )
        wheel = next(dist_dir.glob("*.whl"))
        sdist = next(dist_dir.glob("*.tar.gz"))
        _assert_archive_contract(wheel, sdist)
        _run([sys.executable, "-m", "twine", "check", str(wheel), str(sdist)])
        _smoke_installed_wheel(wheel, temp_root)
    print(
        "Distribution acceptance passed: archives, twine metadata, clean CLI, "
        "and Web health are valid."
    )


if __name__ == "__main__":
    main()

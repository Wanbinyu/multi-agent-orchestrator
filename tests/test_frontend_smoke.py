"""Controlled frontend server and browser smoke acceptance tests."""
from __future__ import annotations

import socket
from types import SimpleNamespace

import httpx
import pytest

from src.core.engineering import RunJournalStore, TaskIntentClassifier
from src.core.engineering.evidence import ToolEvidenceRecorder
from src.core.engineering.frontend_smoke import (
    FrontendSmokeError,
    ManagedFrontendServer,
    PlaywrightBrowserDriver,
    reserve_local_port,
    run_frontend_smoke,
)
from src.core.engineering.verifier import VerificationTracker
from src.models.schemas import FrontendSmokeContract


def _contract(*, command: list[str] | None = None) -> FrontendSmokeContract:
    return FrontendSmokeContract(
        start_command=command or [
            "python", "-m", "http.server", "{port}", "--bind", "127.0.0.1"
        ],
        routes=[
            {
                "path": "/",
                "assertions": [
                    {"selector": "main", "check": "text"},
                    {"selector": "table", "check": "table_rows"},
                    {"selector": "canvas", "check": "canvas_nonblank"},
                    {"selector": ".skeleton", "check": "not_visible"},
                ],
            }
        ],
        layout_pairs=[
            {"first_selector": "aside", "second_selector": "main"}
        ],
        startup_timeout_seconds=1.0,
        action_timeout_seconds=1.0,
    )


class _PassingDriver:
    def run(self, base_url, _contract, _artifact_dir):
        assert httpx.get(base_url, timeout=1).status_code == 200
        return [
            {"viewport": "1280x720", "passed": True, "issues": [], "console_errors": []},
            {"viewport": "390x844", "passed": True, "issues": [], "console_errors": []},
        ]


class _FailingDriver:
    def run(self, _base_url, _contract, _artifact_dir):
        return [
            {
                "viewport": "1280x720",
                "passed": False,
                "issues": ["/dashboard: table 表格行数 0 < 1"],
                "console_errors": ["mock request failed"],
            },
            {
                "viewport": "390x844",
                "passed": False,
                "issues": ["/dashboard: 横向溢出 120px"],
                "console_errors": [],
            },
        ]


class _EmptyDriver:
    def run(self, _base_url, _contract, _artifact_dir):
        return []


def test_frontend_smoke_starts_server_checks_two_viewports_and_cleans_process(tmp_path):
    (tmp_path / "index.html").write_text("<main>ready</main>", encoding="utf-8")

    result = run_frontend_smoke(
        tmp_path,
        _contract(),
        tmp_path / "artifacts",
        browser_driver=_PassingDriver(),
    )

    assert result.success is True
    assert result.metadata["viewport_count"] == 2
    assert result.metadata["server_cleaned"] is True
    assert '"passed": true' in result.output


def test_frontend_smoke_fails_on_data_and_mobile_layout_and_records_gate(tmp_path):
    (tmp_path / "index.html").write_text("<main>broken</main>", encoding="utf-8")
    result = run_frontend_smoke(
        tmp_path,
        _contract(),
        tmp_path / "artifacts",
        browser_driver=_FailingDriver(),
    )

    assert result.success is False
    assert result.metadata["issue_count"] == 2
    assert result.metadata["server_cleaned"] is True
    assert "表格行数 0" in result.error
    assert "横向溢出" in result.error

    intent = TaskIntentClassifier().classify("构建一个前端项目", "auto")
    journal = RunJournalStore(tmp_path / "runs").create(
        "session", "构建一个前端项目", "auto", intent=intent
    )
    ToolEvidenceRecorder().record(
        journal, "frontend_smoke", {"project_root": str(tmp_path)}, result
    )
    VerificationTracker().record(
        journal, "frontend_smoke", {"project_root": str(tmp_path)}, result
    )

    assert journal.evidence[-1].claim == "前端浏览器 smoke 失败"
    assert journal.verification[-1].check_type == "smoke"
    assert journal.verification[-1].passed is False
    assert journal.verification[-1].evidence_ids


def test_managed_server_timeout_always_stops_process(tmp_path):
    (tmp_path / "sleep_server.py").write_text(
        "import time\ntime.sleep(30)\n", encoding="utf-8"
    )
    contract = _contract(
        command=["python", "sleep_server.py", "{port}"]
    )
    server = ManagedFrontendServer(tmp_path, contract, max_start_attempts=1)

    with pytest.raises(FrontendSmokeError, match="未就绪"):
        server.start()

    assert server.process is not None
    assert server.process.poll() is not None
    assert server.cleaned is True


@pytest.mark.parametrize(
    "command",
    [
        ["python", "-c", "print('not a server')", "{port}"],
        ["node", "--eval", "console.log('not a server')", "{port}"],
    ],
)
def test_managed_server_rejects_inline_interpreter_code(tmp_path, command):
    server = ManagedFrontendServer(
        tmp_path, _contract(command=command), max_start_attempts=1
    )

    with pytest.raises(FrontendSmokeError, match="禁止解释器内联代码"):
        server.start()

    assert server.process is None


def test_managed_server_does_not_treat_404_as_ready(tmp_path):
    (tmp_path / "index.html").write_text("ready", encoding="utf-8")
    contract = _contract()
    contract.ready_path = "/missing"
    server = ManagedFrontendServer(tmp_path, contract, max_start_attempts=1)

    with pytest.raises(FrontendSmokeError, match="未就绪"):
        server.start()

    assert server.cleaned is True


def test_frontend_smoke_requires_both_viewport_results(tmp_path):
    (tmp_path / "index.html").write_text("ready", encoding="utf-8")

    result = run_frontend_smoke(
        tmp_path, _contract(), tmp_path / "artifacts", browser_driver=_EmptyDriver()
    )

    assert result.success is False
    assert result.metadata["viewport_count"] == 0
    assert "完整的桌面与移动视口" in result.error


def test_navigation_status_rejects_http_errors():
    assert PlaywrightBrowserDriver._navigation_issue(
        SimpleNamespace(status=404), "/missing"
    ) == "/missing: HTTP 404"
    assert PlaywrightBrowserDriver._navigation_issue(
        SimpleNamespace(status=200), "/"
    ) == ""


def test_managed_server_retries_after_port_conflict(tmp_path):
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")
    occupied_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied_socket.bind(("127.0.0.1", 0))
    occupied_socket.listen(1)
    occupied = int(occupied_socket.getsockname()[1])
    available = reserve_local_port()
    ports = iter([occupied, available])
    server = ManagedFrontendServer(
        tmp_path,
        _contract(),
        port_factory=lambda: next(ports),
        max_start_attempts=2,
    )
    try:
        server.start()
        assert server.port == available
        assert httpx.get(server.base_url, timeout=1).status_code == 200
    finally:
        server.stop()
        occupied_socket.close()

    assert server.cleaned is True


def test_smoke_contract_requires_dynamic_port_placeholder():
    with pytest.raises(ValueError, match="必须包含.*port"):
        _contract(command=["npm", "run", "dev"])


def test_real_browser_fixture_covers_login_seven_routes_data_canvas_and_mobile(tmp_path):
    server_script = """
import http.server
import pathlib
import sys

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        data = pathlib.Path('index.html').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *args):
        pass

http.server.ThreadingHTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
"""
    html = """<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box} body{margin:0;font-family:sans-serif;overflow-x:hidden}
.shell{display:grid;grid-template-columns:180px minmax(0,1fr);min-height:100vh}
aside{background:#20242a;color:white;padding:16px} main{min-width:0;padding:16px}
table{width:100%;border-collapse:collapse} td{border:1px solid #bbb;padding:4px}
canvas{width:240px;height:100px;max-width:100%}.skeleton{display:none}
@media(max-width:600px){.shell{grid-template-columns:1fr}aside{display:none}}
</style></head><body><div id="app"></div><script>
const app=document.querySelector('#app');
if(location.pathname==='/login' && !localStorage.getItem('smoke-auth')){
  app.innerHTML='<main><input id="user"><input id="password"><button id="login">Login</button></main>';
  document.querySelector('#login').onclick=()=>{localStorage.setItem('smoke-auth','1');location.href='/overview'};
} else {
  app.innerHTML='<div class="shell"><aside>Navigation</aside><main><h1>'+location.pathname+'</h1><div class="skeleton">Loading</div><table><tbody><tr><td>Mock data ready</td></tr></tbody></table><canvas width="240" height="100"></canvas></main></div>';
  const c=document.querySelector('canvas'),x=c.getContext('2d');x.fillStyle='#167d5a';x.fillRect(5,5,100,70);x.fillStyle='#f0b429';x.fillRect(115,20,100,55);
}
</script></body></html>"""
    (tmp_path / "fixture_server.py").write_text(server_script, encoding="utf-8")
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    paths = [
        "/overview", "/monitor", "/alerts", "/devices",
        "/architecture", "/events", "/timeline",
    ]
    contract = FrontendSmokeContract(
        start_command=["python", "fixture_server.py", "{port}"],
        ready_path="/login",
        login={
            "path": "/login",
            "fields": [
                {"selector": "#user", "value": "demo"},
                {"selector": "#password", "value": "demo"},
            ],
            "submit_selector": "#login",
            "success_selector": ".shell main",
        },
        routes=[
            {
                "path": path,
                "assertions": [
                    {"selector": "h1", "check": "text"},
                    {"selector": "table", "check": "table_rows"},
                    {"selector": "canvas", "check": "canvas_nonblank"},
                    {"selector": ".skeleton", "check": "not_visible"},
                ],
            }
            for path in paths
        ],
        layout_pairs=[
            {"first_selector": "aside", "second_selector": "main"}
        ],
        startup_timeout_seconds=5,
        action_timeout_seconds=3,
    )

    result = run_frontend_smoke(tmp_path, contract, tmp_path / "artifacts")
    if result.metadata.get("error_code") == "browser_runtime_missing":
        pytest.skip(result.error)

    assert result.success is True, result.error
    assert result.metadata["viewport_count"] == 2
    assert result.metadata["issue_count"] == 0
    assert result.metadata["server_cleaned"] is True


def test_real_browser_blocks_broken_mock_login(tmp_path):
    server_script = """
import http.server
import pathlib
import sys
class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        data = pathlib.Path('index.html').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers(); self.wfile.write(data)
    def log_message(self, *args): pass
http.server.ThreadingHTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
"""
    broken_html = """<!doctype html><html><body><main>
<input id="user"><input id="password"><button id="login">Login</button>
<script>
document.querySelector('#login').onclick=async()=>{
  const response=await fetch('/api/login',{method:'POST'});
  const data=await response.json();
  if(data.ok) location.href='/overview';
};
</script></main></body></html>"""
    (tmp_path / "fixture_server.py").write_text(server_script, encoding="utf-8")
    (tmp_path / "index.html").write_text(broken_html, encoding="utf-8")
    contract = FrontendSmokeContract(
        start_command=["python", "fixture_server.py", "{port}"],
        ready_path="/login",
        login={
            "path": "/login",
            "fields": [
                {"selector": "#user", "value": "demo"},
                {"selector": "#password", "value": "demo"},
            ],
            "submit_selector": "#login",
            "success_selector": "[data-dashboard-ready]",
        },
        routes=[
            {"path": "/overview", "assertions": [{"selector": "h1", "check": "text"}]}
        ],
        startup_timeout_seconds=5,
        action_timeout_seconds=1,
    )

    result = run_frontend_smoke(tmp_path, contract, tmp_path / "artifacts")
    if result.metadata.get("error_code") == "browser_runtime_missing":
        pytest.skip(result.error)

    assert result.success is False
    assert result.metadata["issue_count"] > 0
    assert result.metadata["server_cleaned"] is True
    assert "浏览器步骤失败" in result.error or "console error" in result.error

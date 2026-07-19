"""Controlled Playwright smoke verification for generated frontend projects."""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urljoin

import httpx

from src.models.schemas import (
    FrontendSmokeAssertion,
    FrontendSmokeContract,
)
from src.tools.tool_result import ToolResult


_VIEWPORTS = ((1280, 720), (390, 844))
_ALLOWED_SERVER_EXECUTABLES = {
    "node", "npm", "npm.cmd", "npx", "npx.cmd", "pnpm", "pnpm.cmd",
    "python", "python.exe", "python3", "yarn", "yarn.cmd",
}
_PORT_CONFLICT_MARKERS = (
    "address already in use", "eaddrinuse", "only one usage of each socket address",
    "winerror 10048",
)
_INLINE_CODE_FLAGS = {
    "python": {"-c"},
    "python.exe": {"-c"},
    "python3": {"-c"},
    "node": {"-e", "--eval", "-p", "--print"},
}


class FrontendSmokeError(RuntimeError):
    """Bounded smoke failure with a stable code and safe message."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class BrowserSmokeDriver(Protocol):
    def run(
        self,
        base_url: str,
        contract: FrontendSmokeContract,
        artifact_dir: Path,
    ) -> list[dict[str, Any]]:
        """Return one result dictionary per configured viewport."""


def reserve_local_port() -> int:
    """Reserve and release a loopback port immediately before server startup."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ManagedFrontendServer:
    """Start one structured local server command and always stop its process tree."""

    def __init__(
        self,
        project_root: str | Path,
        contract: FrontendSmokeContract,
        *,
        port_factory: Callable[[], int] = reserve_local_port,
        max_start_attempts: int = 3,
    ):
        self.project_root = Path(project_root).expanduser().resolve()
        self.contract = contract
        self.port_factory = port_factory
        self.max_start_attempts = max(1, max_start_attempts)
        self.process: subprocess.Popen[str] | None = None
        self.port = 0
        self.base_url = ""
        self.log_output = ""
        self._log_file: Any = None
        self.cleaned = False

    def __enter__(self) -> ManagedFrontendServer:
        self.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.stop()

    def start(self) -> None:
        if not self.project_root.is_dir():
            raise FrontendSmokeError(
                "project_root_invalid",
                f"前端项目目录不存在：{self.project_root}",
            )
        executable = Path(self.contract.start_command[0]).name.casefold()
        if executable not in _ALLOWED_SERVER_EXECUTABLES:
            raise FrontendSmokeError(
                "server_command_rejected",
                f"不允许的前端 server 可执行文件：{executable}",
            )
        arguments = [part.casefold() for part in self.contract.start_command[1:]]
        forbidden = _INLINE_CODE_FLAGS.get(executable, set())
        if forbidden.intersection(arguments):
            raise FrontendSmokeError(
                "server_command_rejected",
                "前端 server 命令禁止解释器内联代码；请使用项目内脚本或 package script",
            )

        last_error: FrontendSmokeError | None = None
        for attempt in range(1, self.max_start_attempts + 1):
            self.port = self.port_factory()
            self.base_url = f"http://127.0.0.1:{self.port}/"
            argv = [part.replace("{port}", str(self.port)) for part in self.contract.start_command]
            self._log_file = tempfile.TemporaryFile(
                mode="w+", encoding="utf-8", errors="replace"
            )
            kwargs: dict[str, Any] = {
                "cwd": str(self.project_root),
                "stdin": subprocess.DEVNULL,
                "stdout": self._log_file,
                "stderr": subprocess.STDOUT,
                "text": True,
                "shell": False,
            }
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            try:
                self.process = subprocess.Popen(argv, **kwargs)
            except FileNotFoundError as exc:
                self._close_log()
                raise FrontendSmokeError(
                    "server_executable_missing",
                    f"前端 server 可执行文件不存在：{executable}",
                ) from exc

            try:
                self._wait_until_ready()
                return
            except FrontendSmokeError as exc:
                last_error = exc
                self.stop()
                conflict = any(
                    marker in self.log_output.casefold()
                    for marker in _PORT_CONFLICT_MARKERS
                )
                retryable_exit = exc.code == "server_exited"
                if (not conflict and not retryable_exit) or attempt >= self.max_start_attempts:
                    raise
                self.cleaned = False

        raise last_error or FrontendSmokeError(
            "server_start_failed", "前端 server 启动失败"
        )

    def stop(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    shell=False,
                    check=False,
                )
            else:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    process.kill()
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait(timeout=5)
        self._read_log()
        self._close_log()
        self.cleaned = process is None or process.poll() is not None

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + self.contract.startup_timeout_seconds
        ready_url = urljoin(self.base_url, self.contract.ready_path.lstrip("/"))
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                self._read_log()
                raise FrontendSmokeError(
                    "server_exited",
                    f"前端 server 在就绪前退出（exit={self.process.returncode}）",
                )
            try:
                response = httpx.get(ready_url, timeout=0.5, follow_redirects=True)
                if 200 <= response.status_code < 400:
                    return
            except httpx.HTTPError:
                pass
            if self.process is not None and self.process.poll() is not None:
                self._read_log()
                raise FrontendSmokeError(
                    "server_exited",
                    f"前端 server 在就绪前退出（exit={self.process.returncode}）",
                )
            time.sleep(0.1)
        raise FrontendSmokeError(
            "server_start_timeout",
            f"前端 server 在 {self.contract.startup_timeout_seconds:g} 秒内未就绪",
        )

    def _read_log(self) -> None:
        if self._log_file is None or self._log_file.closed:
            return
        self._log_file.flush()
        self._log_file.seek(0)
        self.log_output = self._log_file.read()[-12_000:]

    def _close_log(self) -> None:
        if self._log_file is not None and not self._log_file.closed:
            self._log_file.close()


class PlaywrightBrowserDriver:
    """Run deterministic route, content, console and layout checks."""

    def run(
        self,
        base_url: str,
        contract: FrontendSmokeContract,
        artifact_dir: Path,
    ) -> list[dict[str, Any]]:
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise FrontendSmokeError(
                "playwright_missing",
                "缺少 Playwright；请运行 python -m pip install playwright",
            ) from exc

        results: list[dict[str, Any]] = []
        with sync_playwright() as playwright:
            browser = self._launch_browser(playwright, PlaywrightError)
            try:
                for width, height in _VIEWPORTS:
                    results.append(
                        self._run_viewport(
                            browser,
                            base_url,
                            contract,
                            artifact_dir,
                            width,
                            height,
                        )
                    )
            finally:
                browser.close()
        return results

    @staticmethod
    def _launch_browser(playwright: Any, error_type: type[Exception]) -> Any:
        attempts = [
            ("playwright-chromium", {}),
            ("msedge", {"channel": "msedge"}),
            ("chrome", {"channel": "chrome"}),
        ]
        failures: list[str] = []
        for label, kwargs in attempts:
            try:
                return playwright.chromium.launch(headless=True, **kwargs)
            except error_type:
                failures.append(label)
        raise FrontendSmokeError(
            "browser_runtime_missing",
            "未找到可用 Chromium/Edge/Chrome；请运行 playwright install chromium",
        )

    def _run_viewport(
        self,
        browser: Any,
        base_url: str,
        contract: FrontendSmokeContract,
        artifact_dir: Path,
        width: int,
        height: int,
    ) -> dict[str, Any]:
        label = f"{width}x{height}"
        issues: list[str] = []
        console_errors: list[str] = []
        context = browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()
        page.set_default_timeout(int(contract.action_timeout_seconds * 1000))
        page.on(
            "console",
            lambda message: console_errors.append(message.text[:500])
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: console_errors.append(str(error)[:500]))
        try:
            if contract.login is not None:
                login_response = page.goto(
                    urljoin(base_url, contract.login.path.lstrip("/")),
                    wait_until="domcontentloaded",
                )
                login_issue = self._navigation_issue(
                    login_response, contract.login.path
                )
                if login_issue:
                    issues.append(login_issue)
                for field in contract.login.fields:
                    page.locator(field.selector).fill(field.value)
                page.locator(contract.login.submit_selector).click()
                page.locator(contract.login.success_selector).wait_for(state="visible")

            for route in contract.routes:
                route_response = page.goto(
                    urljoin(base_url, route.path.lstrip("/")),
                    wait_until="domcontentloaded",
                )
                route_issue = self._navigation_issue(route_response, route.path)
                if route_issue:
                    issues.append(route_issue)
                for assertion in route.assertions:
                    issue = self._check_assertion(page, assertion)
                    if issue:
                        issues.append(f"{route.path}: {issue}")
                overflow = page.evaluate(
                    "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
                )
                if float(overflow) > 1:
                    issues.append(f"{route.path}: 横向溢出 {overflow}px")
                for pair in contract.layout_pairs:
                    overlap = page.evaluate(
                        """([first, second]) => {
                          const a = document.querySelector(first);
                          const b = document.querySelector(second);
                          if (!a || !b) return 0;
                          const sa = getComputedStyle(a), sb = getComputedStyle(b);
                          if (sa.display === 'none' || sb.display === 'none' ||
                              sa.visibility === 'hidden' || sb.visibility === 'hidden') return 0;
                          const x = a.getBoundingClientRect(), y = b.getBoundingClientRect();
                          return Math.max(0, Math.min(x.right, y.right) - Math.max(x.left, y.left)) *
                                 Math.max(0, Math.min(x.bottom, y.bottom) - Math.max(x.top, y.top));
                        }""",
                        [pair.first_selector, pair.second_selector],
                    )
                    if float(overlap) > 1:
                        issues.append(
                            f"{route.path}: {pair.first_selector} 与 "
                            f"{pair.second_selector} 发生遮挡"
                        )
        except Exception as exc:  # Playwright timeout and page errors are acceptance issues.
            issues.append(f"浏览器步骤失败：{type(exc).__name__}")
        finally:
            if console_errors:
                issues.extend(f"console error: {item}" for item in console_errors)
            screenshot = ""
            if issues:
                artifact_dir.mkdir(parents=True, exist_ok=True)
                screenshot_path = artifact_dir / f"frontend-smoke-{label}.png"
                try:
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    screenshot = str(screenshot_path)
                except Exception:
                    screenshot = ""
            context.close()
        return {
            "viewport": label,
            "passed": not issues,
            "issues": issues,
            "console_errors": console_errors,
            "screenshot": screenshot,
        }

    @staticmethod
    def _navigation_issue(response: Any, path: str) -> str:
        if response is None:
            return f"{path}: 浏览器导航没有 HTTP 响应"
        try:
            status = int(response.status)
        except (AttributeError, TypeError, ValueError):
            return f"{path}: 浏览器导航响应状态无效"
        return f"{path}: HTTP {status}" if status >= 400 else ""

    @staticmethod
    def _check_assertion(page: Any, assertion: FrontendSmokeAssertion) -> str:
        locator = page.locator(assertion.selector)
        if assertion.check == "not_visible":
            if locator.count() == 0:
                return ""
            visible = sum(
                1 for index in range(locator.count()) if locator.nth(index).is_visible()
            )
            return "" if visible == 0 else f"{assertion.selector} 仍然可见"

        try:
            locator.first.wait_for(state="visible")
        except Exception:
            return f"{assertion.selector} 不可见"
        if assertion.check == "visible":
            visible = sum(
                1 for index in range(locator.count()) if locator.nth(index).is_visible()
            )
            if visible < assertion.min_count:
                return f"{assertion.selector} 可见数量 {visible} < {assertion.min_count}"
            return ""
        if assertion.check == "text":
            return "" if locator.first.inner_text().strip() else f"{assertion.selector} 文本为空"
        if assertion.check == "table_rows":
            count = locator.locator("tbody tr").count()
            return "" if count >= assertion.min_count else (
                f"{assertion.selector} 表格行数 {count} < {assertion.min_count}"
            )
        if assertion.check == "canvas_nonblank":
            nonblank = locator.first.evaluate(
                """element => {
                  const canvas = element.tagName === 'CANVAS' ? element : element.querySelector('canvas');
                  if (!canvas || canvas.width < 2 || canvas.height < 2) return false;
                  try {
                    const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
                    let opaque = 0, changes = 0, previous = -1;
                    const step = Math.max(4, Math.floor(data.length / 4000 / 4) * 4);
                    for (let i = 0; i < data.length; i += step) {
                      const value = data[i] + data[i + 1] + data[i + 2] + data[i + 3];
                      if (data[i + 3] > 0) opaque++;
                      if (previous >= 0 && value !== previous) changes++;
                      previous = value;
                    }
                    return opaque > 0 && changes > 1;
                  } catch (_) { return false; }
                }"""
            )
            return "" if nonblank else f"{assertion.selector} 画布为空白"
        return f"未知断言类型：{assertion.check}"


def run_frontend_smoke(
    project_root: str | Path,
    contract: FrontendSmokeContract,
    artifact_dir: str | Path,
    *,
    browser_driver: BrowserSmokeDriver | None = None,
    port_factory: Callable[[], int] = reserve_local_port,
) -> ToolResult:
    """Run one controlled server and two viewport browser acceptance passes."""
    started = time.perf_counter()
    artifacts = Path(artifact_dir).expanduser().resolve()
    server: ManagedFrontendServer | None = None
    try:
        server = ManagedFrontendServer(
            project_root,
            contract,
            port_factory=port_factory,
        )
        with server:
            driver = browser_driver or PlaywrightBrowserDriver()
            viewports = driver.run(server.base_url, contract, artifacts)
        issues = [
            issue
            for viewport in viewports
            for issue in (viewport.get("issues") or [])
        ]
        expected_viewports = {f"{width}x{height}" for width, height in _VIEWPORTS}
        actual_viewports = {
            str(viewport.get("viewport", "")) for viewport in viewports
        }
        if len(viewports) != len(_VIEWPORTS) or actual_viewports != expected_viewports:
            issues.append("浏览器 smoke 未返回完整的桌面与移动视口结果")
        for viewport in viewports:
            if viewport.get("passed") is not True and not viewport.get("issues"):
                issues.append(
                    f"{viewport.get('viewport', 'unknown')}: 视口标记失败但未提供原因"
                )
        report = {
            "passed": not issues,
            "viewports": viewports,
            "issues": issues,
            "server": {
                "port": server.port,
                "cleaned": server.cleaned,
                "log": server.log_output[-2000:],
            },
        }
        return ToolResult(
            success=not issues,
            output=json.dumps(report, ensure_ascii=False, indent=2),
            error=("浏览器 smoke 失败：" + "；".join(issues[:5])) if issues else "",
            metadata={
                "check_type": "smoke",
                "project_root": str(Path(project_root).expanduser().resolve()),
                "viewport_count": len(viewports),
                "issue_count": len(issues),
                "server_cleaned": server.cleaned,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            },
        )
    except FrontendSmokeError as exc:
        if server is not None:
            server.stop()
        return ToolResult(
            success=False,
            error=str(exc),
            metadata={
                "check_type": "smoke",
                "error_code": exc.code,
                "project_root": str(Path(project_root).expanduser().resolve()),
                "server_cleaned": server.cleaned if server is not None else True,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            },
        )
    except Exception as exc:
        if server is not None:
            server.stop()
        return ToolResult(
            success=False,
            error=f"浏览器 smoke 执行异常：{type(exc).__name__}",
            metadata={
                "check_type": "smoke",
                "error_code": "smoke_runtime_error",
                "project_root": str(Path(project_root).expanduser().resolve()),
                "server_cleaned": server.cleaned if server is not None else True,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            },
        )

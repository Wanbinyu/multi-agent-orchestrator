"""Deterministic contract and closure checks for high-risk frontend builds."""
from __future__ import annotations

import json
import ntpath
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from src.core.collaboration import CollaborationPlanError
from src.models.schemas import FrontendBuildContract, Task, TaskPlan


REQUIRED_FRONTEND_STAGES = {
    "architecture_scaffold",
    "pages",
    "data_api",
    "integration",
}

# 模型常输出的阶段别名 → 固定四阶段
FRONTEND_STAGE_ALIASES: dict[str, str] = {
    "architecture": "architecture_scaffold",
    "architecture_scaffold": "architecture_scaffold",
    "scaffold": "architecture_scaffold",
    "arch": "architecture_scaffold",
    "design": "architecture_scaffold",
    "setup": "architecture_scaffold",
    "pages": "pages",
    "page": "pages",
    "ui": "pages",
    "frontend": "pages",
    "view": "pages",
    "views": "pages",
    "implementation": "pages",
    "implement": "pages",
    "feature": "pages",
    "features": "pages",
    "data_api": "data_api",
    "data": "data_api",
    "api": "data_api",
    "mock": "data_api",
    "backend_api": "data_api",
    "state": "data_api",
    "integration": "integration",
    "integrate": "integration",
    "test": "integration",
    "tests": "integration",
    "tester": "integration",
    "verify": "integration",
    "qa": "integration",
    "smoke": "integration",
}


def normalize_frontend_stage(value: object) -> str | None:
    """Map free-form stage names to the fixed four-stage contract."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    key = text.casefold().replace("-", "_").replace(" ", "_")
    if key in REQUIRED_FRONTEND_STAGES:
        return key
    mapped = FRONTEND_STAGE_ALIASES.get(key)
    if mapped:
        return mapped
    # partial contains
    for alias, stage in FRONTEND_STAGE_ALIASES.items():
        if alias in key or key in alias:
            return stage
    return None


def repair_frontend_contract_payload(
    raw: object,
    *,
    tasks: list[Task],
    workspace: str | Path | None = None,
) -> dict[str, Any] | None:
    """Repair incomplete LLM frontend_contract into a minimal valid payload.

    Models often emit partial objects (string routes, missing smoke, etc.).
    Rather than fail planning entirely, fill conservative defaults so Workers
    can still execute; bind_and_validate still enforces stage/ownership rules.
    """
    if raw is None:
        data: dict[str, Any] = {}
    elif isinstance(raw, dict):
        data = dict(raw)
    else:
        return None

    root = Path(workspace or Path.cwd()).expanduser().resolve()
    project_root = str(data.get("project_root") or "").strip()
    if not project_root:
        project_root = str(root / "weather-dashboard")
    elif not (Path(project_root).is_absolute() or ntpath.isabs(project_root)):
        project_root = str((root / project_root).resolve())
    data["project_root"] = project_root

    # routes: ["/", "/x"] or [{path, target}] or [{path: "/"}]
    routes_raw = data.get("routes") or []
    routes: list[dict[str, str]] = []
    if isinstance(routes_raw, list):
        for item in routes_raw:
            if isinstance(item, str) and item.strip():
                path = item.strip()
                if not path.startswith("/"):
                    path = "/" + path
                target = (
                    "src/pages/Home.tsx"
                    if path in {"/", "/index", "/home"}
                    else f"src/pages{path.replace('/', '/').rstrip('/') or '/Home'}.tsx"
                )
                if path == "/":
                    target = "src/pages/Home.tsx"
                elif path == "/weather-dashboard":
                    target = "src/pages/WeatherDashboard.tsx"
                else:
                    slug = path.strip("/").replace("/", "_") or "Page"
                    target = f"src/pages/{slug}.tsx"
                routes.append({"path": path, "target": target})
            elif isinstance(item, dict):
                path = str(item.get("path") or item.get("route") or "").strip()
                target = str(item.get("target") or item.get("file") or "").strip()
                if path and not target:
                    slug = path.strip("/").replace("/", "_") or "Home"
                    target = f"src/pages/{slug}.tsx"
                if path and target:
                    if not path.startswith("/"):
                        path = "/" + path
                    routes.append({"path": path, "target": target})
    if not routes:
        routes = [
            {"path": "/", "target": "src/pages/Home.tsx"},
            {"path": "/weather-dashboard", "target": "src/pages/WeatherDashboard.tsx"},
        ]
    data["routes"] = routes

    entrypoints = data.get("entrypoints")
    if not isinstance(entrypoints, list) or not entrypoints:
        data["entrypoints"] = ["index.html", "src/main.tsx", "src/App.tsx"]
    else:
        data["entrypoints"] = [str(x).strip() for x in entrypoints if str(x).strip()]

    dependencies = data.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        data["dependencies"] = ["react", "react-dom", "vite"]
    else:
        data["dependencies"] = [str(x).strip() for x in dependencies if str(x).strip()]

    ownership: dict[str, list[str]] = {}
    raw_ownership = data.get("ownership")
    if isinstance(raw_ownership, dict):
        ownership = {
            str(k): [str(p) for p in (v or []) if str(p).strip()]
            for k, v in raw_ownership.items()
            if str(k).strip()
        }
    # Fill missing ownership from stages / owned_paths
    for task in tasks:
        if task.id in ownership and ownership[task.id]:
            continue
        if task.owned_paths:
            ownership[task.id] = list(task.owned_paths)
        elif task.frontend_stage == "architecture_scaffold":
            ownership[task.id] = [
                f"{project_root}/package.json",
                f"{project_root}/vite.config.ts",
                f"{project_root}/index.html",
                f"{project_root}/src/main.tsx",
                f"{project_root}/src/App.tsx",
            ]
        elif task.frontend_stage == "pages":
            ownership[task.id] = [f"{project_root}/src/pages"]
        elif task.frontend_stage == "data_api":
            ownership[task.id] = [
                f"{project_root}/src/api",
                f"{project_root}/src/services",
            ]
        elif task.frontend_stage == "integration":
            ownership[task.id] = []
        else:
            ownership[task.id] = [f"{project_root}/src/{task.id}"]
    if not ownership and tasks:
        ownership = {tasks[0].id: [f"{project_root}/src"]}
    data["ownership"] = ownership

    # Align task.owned_paths with ownership when empty
    for task in tasks:
        declared = data["ownership"].get(task.id)
        if declared is not None and not task.owned_paths:
            task.owned_paths = list(declared)

    verification = data.get("verification_commands")
    if not isinstance(verification, list) or not verification:
        data["verification_commands"] = ["npm install", "npm run build"]
    else:
        data["verification_commands"] = [
            str(x).strip() for x in verification if str(x).strip()
        ]

    smoke_paths = data.get("smoke_paths")
    if not isinstance(smoke_paths, list) or not smoke_paths:
        data["smoke_paths"] = [route["path"] for route in routes]
    else:
        data["smoke_paths"] = [str(x).strip() for x in smoke_paths if str(x).strip()]

    smoke = data.get("smoke")
    if not isinstance(smoke, dict):
        smoke = {}
    start_command = smoke.get("start_command")
    if not isinstance(start_command, list) or not start_command:
        smoke["start_command"] = ["npm", "run", "dev", "--", "--port", "{port}", "--host"]
    def _default_assertions() -> list[dict[str, Any]]:
        return [{"selector": "body", "check": "visible", "min_count": 1}]

    smoke_routes = smoke.get("routes")
    if not isinstance(smoke_routes, list) or not smoke_routes:
        smoke["routes"] = [
            {"path": path, "assertions": _default_assertions()}
            for path in data["smoke_paths"]
        ]
    else:
        fixed: list[dict[str, Any]] = []
        for item in smoke_routes:
            if isinstance(item, str):
                path = item if item.startswith("/") else f"/{item}"
                fixed.append({"path": path, "assertions": _default_assertions()})
            elif isinstance(item, dict):
                path = str(item.get("path") or "/").strip() or "/"
                assertions = item.get("assertions") or item.get("checks")
                if not isinstance(assertions, list) or not assertions:
                    assertions = _default_assertions()
                else:
                    # normalize check aliases
                    norm_assert = []
                    for assertion in assertions:
                        if not isinstance(assertion, dict):
                            continue
                        a = dict(assertion)
                        if "kind" in a and "check" not in a:
                            a["check"] = a.pop("kind")
                        if "selector" not in a:
                            a["selector"] = "body"
                        if "check" not in a:
                            a["check"] = "visible"
                        norm_assert.append(a)
                    assertions = norm_assert or _default_assertions()
                fixed.append({"path": path, "assertions": assertions})
        smoke["routes"] = fixed or [
            {"path": "/", "assertions": _default_assertions()}
        ]
    data["smoke"] = smoke

    # Drop unknown free-form keys that confuse validators later
    allowed = {
        "project_root",
        "entrypoints",
        "routes",
        "dependencies",
        "ownership",
        "verification_commands",
        "smoke_paths",
        "smoke",
    }
    return {k: v for k, v in data.items() if k in allowed}
_FRONTEND_MARKERS = (
    "前端", "frontend", "react", "vue", "vite", "页面", "网站", "dashboard", "看板",
    "大屏", "可视化", "ui",
)
_BUILD_MARKERS = (
    "做一套", "做一个", "创建", "开发", "实现", "搭建", "构建", "build", "create", "做",
)
_HIGH_SCOPE_MARKERS = (
    "项目", "系统", "多页面", "完整", "一套", "矿区", "矿山", "后台", "管理平台",
    "大屏",
)
_IMPORT_PATTERN = re.compile(
    r"(?:import\s+(?:[^;]*?\s+from\s+)?|export\s+[^;]*?\s+from\s+|import\s*\()"
    r"[\"'](?P<path>\.{1,2}/[^\"']+)[\"']"
)
_RESOLVABLE_EXTENSIONS = ("", ".js", ".jsx", ".ts", ".tsx", ".json", ".css")


def is_high_risk_frontend_request(user_request: str) -> bool:
    """Conservatively identify project-sized frontend implementation requests."""
    text = user_request.casefold()
    return (
        any(marker in text for marker in _FRONTEND_MARKERS)
        and any(marker in text for marker in _BUILD_MARKERS)
        and any(marker in text for marker in _HIGH_SCOPE_MARKERS)
    )


def bind_and_validate_frontend_contract(plan: TaskPlan) -> TaskPlan:
    """Validate fixed stages and bind the shared contract to integration Worker."""
    contract = plan.frontend_contract
    if contract is None:
        raise CollaborationPlanError("高风险前端计划缺少 frontend_contract")
    if not (
        Path(contract.project_root).is_absolute()
        or ntpath.isabs(contract.project_root)
    ):
        raise CollaborationPlanError("frontend_contract project_root 必须是绝对路径")

    by_stage: dict[str, list[Task]] = {}
    for task in plan.tasks:
        if task.frontend_stage:
            by_stage.setdefault(task.frontend_stage, []).append(task)
    missing = sorted(REQUIRED_FRONTEND_STAGES - set(by_stage))
    duplicates = sorted(stage for stage, tasks in by_stage.items() if len(tasks) > 1)
    if missing:
        raise CollaborationPlanError(f"高风险前端计划缺少固定阶段：{', '.join(missing)}")
    if duplicates:
        raise CollaborationPlanError(f"高风险前端计划阶段重复：{', '.join(duplicates)}")

    architecture = by_stage["architecture_scaffold"][0]
    pages = by_stage["pages"][0]
    data_api = by_stage["data_api"][0]
    integration = by_stage["integration"][0]
    if architecture.type != "architect":
        raise CollaborationPlanError("architecture_scaffold 阶段必须使用 architect Worker")
    if pages.type != "frontend_dev" or data_api.type != "frontend_dev":
        raise CollaborationPlanError("pages 和 data_api 阶段必须使用 frontend_dev Worker")
    if integration.type not in {"tester", "test", "qa"}:
        raise CollaborationPlanError("integration 阶段必须使用 tester Worker")
    if integration.execution_mode != "verify":
        raise CollaborationPlanError("integration 阶段必须声明 execution_mode=verify")

    implementation_ids = {architecture.id, pages.id, data_api.id}
    missing_dependencies = sorted(implementation_ids - set(integration.depends_on))
    if missing_dependencies:
        raise CollaborationPlanError(
            "integration 阶段必须直接依赖全部实现任务："
            + ", ".join(missing_dependencies)
        )
    for task in (pages, data_api):
        if architecture.id not in task.depends_on:
            raise CollaborationPlanError(
                f"{task.frontend_stage} 阶段必须依赖 architecture_scaffold"
            )

    task_ids = {task.id for task in plan.tasks}
    unknown_owners = sorted(set(contract.ownership) - task_ids)
    if unknown_owners:
        raise CollaborationPlanError(
            "frontend_contract ownership 引用了未知任务："
            + ", ".join(unknown_owners)
        )
    for task in plan.tasks:
        declared = contract.ownership.get(task.id, [])
        if declared != task.owned_paths:
            raise CollaborationPlanError(
                f"frontend_contract ownership 与任务 {task.id} 的 owned_paths 不一致"
            )

    route_paths = {route.path for route in contract.routes}
    missing_smoke = sorted(path for path in contract.smoke_paths if path not in route_paths)
    if missing_smoke:
        raise CollaborationPlanError(
            "smoke_paths 未在 routes 中声明：" + ", ".join(missing_smoke)
        )
    smoke_route_paths = {route.path for route in contract.smoke.routes}
    missing_browser_routes = sorted(set(contract.smoke_paths) - smoke_route_paths)
    if missing_browser_routes:
        raise CollaborationPlanError(
            "smoke contract 缺少浏览器路由断言："
            + ", ".join(missing_browser_routes)
        )

    integration.frontend_contract = contract.model_copy(deep=True)
    return plan


def verify_frontend_closure(contract: FrontendBuildContract) -> list[str]:
    """Return deterministic entrypoint, route, dependency and local-import issues."""
    root = Path(contract.project_root).expanduser().resolve()
    issues: list[str] = []
    if not root.is_dir():
        return [f"前端项目根目录不存在：{root}"]

    candidate_files: set[Path] = set()
    for relative in contract.entrypoints:
        target = _within_root(root, relative)
        if target is None or not target.is_file():
            issues.append(f"入口文件不存在：{relative}")
        else:
            candidate_files.add(target)
    for route in contract.routes:
        target = _within_root(root, route.target)
        if target is None or not target.is_file():
            issues.append(f"路由 {route.path} 的目标不存在：{route.target}")
        else:
            candidate_files.add(target)

    package_json = root / "package.json"
    if contract.dependencies:
        if not package_json.is_file():
            issues.append("依赖合同要求 package.json，但文件不存在")
        else:
            try:
                package = json.loads(package_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                issues.append(f"package.json 无法解析：{exc}")
            else:
                declared: dict[str, object] = {}
                for field in ("dependencies", "devDependencies"):
                    section = package.get(field) or {}
                    if not isinstance(section, dict):
                        issues.append(f"package.json {field} 必须是对象")
                        continue
                    declared.update(section)
                for dependency in contract.dependencies:
                    if dependency not in declared:
                        issues.append(f"package.json 缺少合同依赖：{dependency}")

    source_files = _reachable_source_files(root, candidate_files, issues)
    for html_file in (path for path in source_files if path.suffix.casefold() == ".html"):
        _check_html_references(root, html_file, issues)
    return list(dict.fromkeys(issues))


def validate_integration_tool_evidence(
    contract: FrontendBuildContract,
    tool_trace: list[dict],
) -> list[str]:
    """Require successful real command evidence for every verification command."""
    successful = {
        str((call.get("params") or {}).get("command", "")).strip()
        for call in tool_trace
        if call.get("tool") == "run_command" and call.get("success")
    }
    issues = [
        f"缺少真实成功命令证据：{command}"
        for command in contract.verification_commands
        if command not in successful
    ]
    if not any(
        call.get("tool") == "frontend_smoke" and call.get("success")
        for call in tool_trace
    ):
        issues.append("缺少真实成功浏览器证据：frontend_smoke")
    return issues


def _reachable_source_files(
    root: Path, seeds: set[Path], issues: list[str]
) -> set[Path]:
    queue = list(seeds)
    visited: set[Path] = set()
    while queue:
        current = queue.pop()
        if current in visited or not current.is_file():
            continue
        visited.add(current)
        if current.suffix.casefold() not in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            continue
        try:
            content = current.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            issues.append(
                f"无法读取源码 {current.relative_to(root).as_posix()}：{exc}"
            )
            continue
        for match in _IMPORT_PATTERN.finditer(content):
            import_path = match.group("path")
            resolved = _resolve_local_import(current.parent, import_path)
            if resolved is None or not _is_relative_to(resolved, root):
                issues.append(
                    "错误导入："
                    f"{current.relative_to(root).as_posix()} -> {import_path}"
                )
            else:
                queue.append(resolved)
    return visited


def _resolve_local_import(base: Path, import_path: str) -> Path | None:
    raw = (base / import_path).resolve()
    for extension in _RESOLVABLE_EXTENSIONS:
        candidate = Path(str(raw) + extension)
        if candidate.is_file():
            return candidate
    for extension in _RESOLVABLE_EXTENSIONS[1:]:
        candidate = raw / f"index{extension}"
        if candidate.is_file():
            return candidate
    return None


class _AssetReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and values.get("src"):
            self.references.append(str(values["src"]))
        if tag == "link" and values.get("href"):
            self.references.append(str(values["href"]))


def _check_html_references(root: Path, html_file: Path, issues: list[str]) -> None:
    parser = _AssetReferenceParser()
    try:
        parser.feed(html_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        issues.append(
            f"无法读取 HTML {html_file.relative_to(root).as_posix()}：{exc}"
        )
        return
    for reference in parser.references:
        if reference.startswith(("http://", "https://", "//", "data:", "#")):
            continue
        clean = reference.split("?", 1)[0].split("#", 1)[0]
        target = (root / clean.lstrip("/")) if reference.startswith("/") else (html_file.parent / clean)
        resolved = target.resolve()
        if not _is_relative_to(resolved, root):
            issues.append(
                "HTML 资源越出项目根："
                f"{html_file.relative_to(root).as_posix()} -> {reference}"
            )
        elif not resolved.is_file():
            issues.append(
                "HTML 资源不存在："
                f"{html_file.relative_to(root).as_posix()} -> {reference}"
            )


def _within_root(root: Path, relative: str) -> Path | None:
    target = (root / relative).resolve()
    return target if _is_relative_to(target, root) else None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

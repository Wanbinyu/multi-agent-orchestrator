"""High-risk frontend multi-model build contract tests."""
from __future__ import annotations

import json

import pytest

from src.core.collaboration import CollaborationPlanError
from src.core.frontend_contract import (
    bind_and_validate_frontend_contract,
    is_high_risk_frontend_request,
    validate_integration_tool_evidence,
    verify_frontend_closure,
)
from src.models.schemas import FrontendBuildContract, Task, TaskPlan


def _contract(root: str) -> FrontendBuildContract:
    return FrontendBuildContract(
        project_root=root,
        entrypoints=["src/main.tsx"],
        routes=[
            {"path": "/", "target": "src/pages/Dashboard.tsx"},
            {"path": "/monitor", "target": "src/pages/Monitor.tsx"},
        ],
        dependencies=["react"],
        ownership={
            "architecture": [root],
            "pages": [f"{root}/src/pages"],
            "data": [f"{root}/src/api"],
            "integration": [],
        },
        verification_commands=["npm run build", "npm test"],
        smoke_paths=["/", "/monitor"],
        smoke={
            "start_command": [
                "python", "-m", "http.server", "{port}", "--bind", "127.0.0.1"
            ],
            "routes": [
                {"path": "/", "assertions": [{"selector": "body"}]},
                {"path": "/monitor", "assertions": [{"selector": "body"}]},
            ],
        },
    )


def _plan(root: str) -> TaskPlan:
    contract = _contract(root)
    return TaskPlan(
        summary="智慧矿区前端",
        frontend_contract=contract,
        tasks=[
            Task(
                id="architecture", type="architect", title="架构与脚手架",
                input="", assigned_model="glm-ark", owned_paths=[root],
                frontend_stage="architecture_scaffold", parallel_safe=False,
            ),
            Task(
                id="pages", type="frontend_dev", title="页面",
                input="", assigned_model="kimi", depends_on=["architecture"],
                owned_paths=[f"{root}/src/pages"], frontend_stage="pages",
            ),
            Task(
                id="data", type="frontend_dev", title="数据与 API",
                input="", assigned_model="glm-ark", depends_on=["architecture"],
                owned_paths=[f"{root}/src/api"], frontend_stage="data_api",
            ),
            Task(
                id="integration", type="tester", title="集成验证",
                input="", assigned_model="glm-ark",
                depends_on=["architecture", "pages", "data"],
                execution_mode="verify", owned_paths=[],
                frontend_stage="integration", parallel_safe=False,
            ),
        ],
    )


def test_detects_project_sized_frontend_build_but_not_small_page_request():
    assert is_high_risk_frontend_request(
        "我现在接了一个智慧矿区的项目，现在给我做一个纯前端的项目"
    )
    assert not is_high_risk_frontend_request("用 React 做个登录页面")


def test_bind_contract_requires_all_stages_and_all_integration_dependencies(tmp_path):
    plan = _plan(str(tmp_path))
    bound = bind_and_validate_frontend_contract(plan)

    integration = next(task for task in bound.tasks if task.id == "integration")
    assert integration.frontend_contract == plan.frontend_contract

    plan.tasks = [task for task in plan.tasks if task.frontend_stage != "data_api"]
    with pytest.raises(CollaborationPlanError, match="缺少固定阶段.*data_api"):
        bind_and_validate_frontend_contract(plan)


def test_bind_contract_rejects_integration_that_trusts_partial_dependencies(tmp_path):
    plan = _plan(str(tmp_path))
    integration = next(task for task in plan.tasks if task.id == "integration")
    integration.depends_on.remove("data")

    with pytest.raises(CollaborationPlanError, match="直接依赖全部实现任务.*data"):
        bind_and_validate_frontend_contract(plan)


def test_bind_contract_rejects_relative_project_root():
    plan = _plan("relative/project")

    with pytest.raises(CollaborationPlanError, match="project_root 必须是绝对路径"):
        bind_and_validate_frontend_contract(plan)


def test_frontend_closure_accepts_declared_routes_dependencies_and_imports(tmp_path):
    (tmp_path / "src" / "pages").mkdir(parents=True)
    (tmp_path / "src" / "main.tsx").write_text(
        'import "./App";\n', encoding="utf-8"
    )
    (tmp_path / "src" / "App.tsx").write_text(
        'import "./pages/Dashboard";\nimport("./pages/Monitor");\n',
        encoding="utf-8",
    )
    (tmp_path / "src" / "pages" / "Dashboard.tsx").write_text(
        "export default function Dashboard() {}\n", encoding="utf-8"
    )
    (tmp_path / "src" / "pages" / "Monitor.tsx").write_text(
        "export default function Monitor() {}\n", encoding="utf-8"
    )
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"react": "latest"}}), encoding="utf-8"
    )

    assert verify_frontend_closure(_contract(str(tmp_path))) == []


def test_frontend_closure_reports_missing_page_and_wrong_import(tmp_path):
    (tmp_path / "src" / "pages").mkdir(parents=True)
    (tmp_path / "src" / "main.tsx").write_text(
        'import "./MissingApp";\n', encoding="utf-8"
    )
    (tmp_path / "src" / "pages" / "Dashboard.tsx").write_text(
        "export default function Dashboard() {}\n", encoding="utf-8"
    )
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {}}), encoding="utf-8"
    )

    issues = verify_frontend_closure(_contract(str(tmp_path)))

    assert "路由 /monitor 的目标不存在：src/pages/Monitor.tsx" in issues
    assert "错误导入：src/main.tsx -> ./MissingApp" in issues
    assert "package.json 缺少合同依赖：react" in issues


def test_integration_requires_real_successful_command_evidence(tmp_path):
    contract = _contract(str(tmp_path))
    tool_trace = [
        {
            "tool": "run_command",
            "params": {"command": "npm run build"},
            "success": True,
        },
        {
            "tool": "run_command",
            "params": {"command": "npm test"},
            "success": False,
        },
    ]

    assert validate_integration_tool_evidence(contract, tool_trace) == [
        "缺少真实成功命令证据：npm test",
        "缺少真实成功浏览器证据：frontend_smoke",
    ]


def test_frontend_closure_rejects_invalid_dependency_shape(tmp_path):
    (tmp_path / "src" / "pages").mkdir(parents=True)
    for relative in ("src/main.tsx", "src/pages/Dashboard.tsx", "src/pages/Monitor.tsx"):
        (tmp_path / relative).write_text("export default {}\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"dependencies": ["react"]}', encoding="utf-8"
    )

    issues = verify_frontend_closure(_contract(str(tmp_path)))

    assert "package.json dependencies 必须是对象" in issues
    assert "package.json 缺少合同依赖：react" in issues


def test_frontend_closure_rejects_html_resource_outside_project(tmp_path):
    (tmp_path / "src" / "pages").mkdir(parents=True)
    for relative in ("src/main.tsx", "src/pages/Dashboard.tsx", "src/pages/Monitor.tsx"):
        (tmp_path / relative).write_text("export default {}\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"react": "latest"}}), encoding="utf-8"
    )
    outside = tmp_path.parent / "outside.js"
    outside.write_text("console.log('outside')", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<script src="../outside.js"></script>', encoding="utf-8"
    )
    contract = _contract(str(tmp_path))
    contract.entrypoints.append("index.html")

    issues = verify_frontend_closure(contract)

    assert "HTML 资源越出项目根：index.html -> ../outside.js" in issues

"""Orchestrator 单元测试"""
import json
from unittest.mock import MagicMock

import pytest

from src.core.orchestrator import (
    Orchestrator,
    _detect_scenario,
    _normalize_task_text_fields,
)
from src.models.schemas import ChatResponse, Task, TaskPlan


def _mock_gateway(response_content: str, main_model: str | None = "main-model") -> MagicMock:
    gateway = MagicMock()
    gateway.chat.return_value = ChatResponse(
        content=response_content,
        model="glm-ark",
        provider="ark",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.0001,
    )
    gateway.get_main_model.return_value = main_model
    gateway.resolve_model = MagicMock(side_effect=lambda preferred: preferred or main_model or "claude-fable-5")
    return gateway


def _sample_workers_yaml() -> str:
    return """
orchestrator:
  model: glm-ark
  system_prompt: 你是一个任务拆分专家

available_workers:
  plot_designer:
    name: 情节设计师
    default_model: glm-ark
    system_prompt: 设计情节
  writer:
    name: 写手
    default_model: deepseek-chat
    system_prompt: 撰写内容
"""


def test_plan_returns_task_plan(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(_sample_workers_yaml(), encoding="utf-8")

    plan_data = {
        "summary": "写一个登录页面",
        "tasks": [
            {"id": "t1", "type": "plot_designer", "title": "设计情节", "input": "输入1", "assigned_model": "glm-ark"},
            {"id": "t2", "type": "writer", "title": "撰写内容", "input": "输入2", "assigned_model": "deepseek-chat"},
        ],
    }
    gateway = _mock_gateway(json.dumps(plan_data))

    orchestrator = Orchestrator(gateway, config_path=str(config_path))
    plan = orchestrator.plan("开发一个登录页面")

    assert isinstance(plan, TaskPlan)
    assert plan.summary == "写一个登录页面"
    assert len(plan.tasks) == 2
    assert plan.tasks[0].id == "t1"
    assert plan.tasks[0].assigned_model == "glm-ark"
    assert plan.tasks[1].assigned_model == "deepseek-chat"
    assert plan.tasks[0].output_format
    assert plan.tasks[0].acceptance

    gateway.chat.assert_called_once()
    call_kwargs = gateway.chat.call_args.kwargs
    assert call_kwargs["model_name"] == "glm-ark"
    assert call_kwargs["task_id"] == "orchestrator"


def test_normalize_task_text_fields_accepts_dict_input_and_output_format():
    """LLM 常把 input/output_format 写成对象；不得 ValidationError。"""
    raw = {
        "id": "architecture_scaffold",
        "type": "architect",
        "title": "架构与脚手架",
        "input": {
            "user_requirements": "实时天气大屏，要好看",
            "类型与接入方式": "公开天气 API",
        },
        "output_format": {
            "files": ["architecture.md", "README.md"],
            "建议与落地方案": "给出技术选型与分工",
        },
        "acceptance": ["可运行", "有实时天气"],
        "assigned_model": "deepseek-v4-pro",
        "depends_on": [],
    }
    normalized = _normalize_task_text_fields(raw)
    task = Task(**normalized)
    assert isinstance(task.input, str)
    assert "天气大屏" in task.input
    assert isinstance(task.output_format, str)
    assert "architecture.md" in task.output_format
    assert isinstance(task.acceptance, str)
    assert "可运行" in task.acceptance


def test_task_model_coerces_dict_fields_directly():
    task = Task(
        id="t1",
        type="frontend_dev",
        title="页面",
        input={"user_requirements": "天气大屏"},
        output_format={"files": ["index.html"]},
        acceptance=["好看"],
        assigned_model="m",
    )
    assert "天气大屏" in task.input
    assert "index.html" in task.output_format


def test_plan_accepts_structured_task_text_objects(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(
        """
orchestrator:
  model: glm-ark
available_workers:
  architect:
    default_model: glm-ark
  frontend_dev:
    default_model: deepseek-chat
  tester:
    default_model: deepseek-chat
""",
        encoding="utf-8",
    )
    plan_data = {
        "summary": "实时天气大屏",
        "tasks": [
            {
                "id": "t1",
                "type": "architect",
                "title": "架构",
                "input": {
                    "user_requirements": "老板要实时天气大屏",
                    "类型与接入方式": "Open-Meteo",
                },
                "output_format": {
                    "files": ["architecture.md"],
                    "建议与落地方案": "技术选型与分工",
                },
                "assigned_model": "glm-ark",
            }
        ],
    }
    gateway = _mock_gateway(json.dumps(plan_data, ensure_ascii=False))
    orchestrator = Orchestrator(gateway, config_path=str(config_path))
    plan = orchestrator.plan("做一个实时天气大屏")
    assert len(plan.tasks) == 1
    assert "天气" in plan.tasks[0].input
    assert "architecture.md" in plan.tasks[0].output_format


def test_plan_injects_project_rules_into_system_prompt(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(_sample_workers_yaml(), encoding="utf-8")
    gateway = _mock_gateway('{"summary": "ok", "tasks": []}')

    orchestrator = Orchestrator(
        gateway,
        config_path=str(config_path),
        project_rules="PROJECT RULE SENTINEL",
    )
    orchestrator.plan("inspect")

    messages = gateway.chat.call_args.kwargs["messages"]
    assert "PROJECT RULE SENTINEL" in messages[0].content


def test_plan_fills_missing_assigned_model_from_worker_default(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(_sample_workers_yaml(), encoding="utf-8")

    plan_data = {
        "summary": "写小说",
        "tasks": [
            {"id": "t1", "type": "writer", "title": "撰写", "input": "输入", "assigned_model": ""},
        ],
    }
    gateway = _mock_gateway(json.dumps(plan_data))

    orchestrator = Orchestrator(gateway, config_path=str(config_path))
    plan = orchestrator.plan("写小说")

    assert plan.tasks[0].assigned_model == "deepseek-chat"


def test_plan_uses_fallback_when_worker_default_missing(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(
        _sample_workers_yaml()
        + "\n  unknown_type:\n    name: Unknown\n    system_prompt: Unknown\n",
        encoding="utf-8",
    )

    plan_data = {
        "summary": "未知类型",
        "tasks": [
            {"id": "t1", "type": "unknown_type", "title": "X", "input": "输入", "assigned_model": ""},
        ],
    }
    gateway = _mock_gateway(json.dumps(plan_data))

    orchestrator = Orchestrator(gateway, config_path=str(config_path))
    plan = orchestrator.plan("未知类型")

    assert plan.tasks[0].assigned_model == "main-model"


def test_plan_normalizes_worker_and_model_role_aliases(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(
        """
orchestrator:
  model: glm-ark
available_workers:
  backend_dev:
    default_model: kimi-for-coding
  tester:
    default_model: glm-ark
""",
        encoding="utf-8",
    )
    plan_data = {
        "summary": "Build and verify",
        "tasks": [
            {
                "id": "build",
                "type": "code_writer",
                "title": "Build",
                "input": "Create src/main.py",
                "assigned_model": "writer",
            },
            {
                "id": "verify",
                "type": "verifier",
                "title": "Verify",
                "input": "Run the check",
                "assigned_model": "verifier",
                "depends_on": ["build"],
            },
        ],
    }
    gateway = _mock_gateway(json.dumps(plan_data))
    gateway.models = {"glm-ark": object(), "kimi-for-coding": object()}
    gateway.resolve_model = MagicMock(
        side_effect=lambda preferred: preferred if preferred in gateway.models else "glm-ark"
    )

    plan = Orchestrator(gateway, config_path=str(config_path)).plan("Create a Python module")

    assert [(task.type, task.assigned_model) for task in plan.tasks] == [
        ("backend_dev", "kimi-for-coding"),
        ("tester", "glm-ark"),
    ]
    assert plan.tasks[1].execution_mode == "verify"


def test_plan_diversifies_when_all_tasks_collapse_to_one_available_model(tmp_path):
    """workers 默认模型全不可用时，应轮询分配已配置模型，而不是全堆主模型。"""
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(
        """
orchestrator:
  model: glm-ark
available_workers:
  architect:
    default_model: glm-ark
  frontend_dev:
    default_model: glm-ark
  tester:
    default_model: glm-ark
""",
        encoding="utf-8",
    )
    plan_data = {
        "summary": "weather dash",
        "tasks": [
            {
                "id": "a",
                "type": "architect",
                "title": "Arch",
                "input": "design",
                "assigned_model": "glm-ark",
            },
            {
                "id": "b",
                "type": "frontend_dev",
                "title": "UI",
                "input": "pages",
                "assigned_model": "glm-ark",
            },
            {
                "id": "c",
                "type": "tester",
                "title": "Test",
                "input": "verify",
                "assigned_model": "glm-ark",
                "depends_on": ["b"],
            },
        ],
    }
    gateway = _mock_gateway(json.dumps(plan_data))
    gateway.models = {
        "openai": object(),
        "deepseek-v4-pro": object(),
        "deepseek-v4-flash": object(),
    }
    gateway.main_model = "openai"
    gateway.get_main_model.return_value = "openai"
    gateway.resolve_model = MagicMock(
        side_effect=lambda preferred: (
            preferred
            if preferred in gateway.models
            else gateway.main_model
        )
    )

    plan = Orchestrator(gateway, config_path=str(config_path)).plan(
        "做一个实时天气大屏"
    )
    models = [task.assigned_model for task in plan.tasks]
    assert len(set(models)) >= 2
    assert set(models).issubset(set(gateway.models))


def test_plan_preserves_valid_model_when_only_worker_alias_changes(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(
        """
orchestrator:
  model: glm-ark
available_workers:
  backend_dev:
    default_model: kimi-for-coding
""",
        encoding="utf-8",
    )
    gateway = _mock_gateway(
        json.dumps(
            {
                "summary": "Build",
                "tasks": [
                    {
                        "id": "build",
                        "type": "code_writer",
                        "title": "Build",
                        "input": "Create src/main.py",
                        "assigned_model": "glm-ark",
                    }
                ],
            }
        )
    )
    gateway.models = {"glm-ark": object(), "kimi-for-coding": object()}
    gateway.resolve_model = MagicMock(side_effect=lambda preferred: preferred)

    plan = Orchestrator(gateway, config_path=str(config_path)).plan(
        "Create a Python module"
    )

    assert plan.tasks[0].type == "backend_dev"
    assert plan.tasks[0].assigned_model == "glm-ark"


def test_plan_normalizes_list_task_text_fields(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(_sample_workers_yaml(), encoding="utf-8")
    gateway = _mock_gateway(
        json.dumps(
            {
                "summary": "Structured criteria",
                "tasks": [
                    {
                        "id": "write",
                        "type": "writer",
                        "title": "Write",
                        "input": "Create the result",
                        "output_format": ["Plain text", {"section": "result"}],
                        "acceptance": ["Result exists", "No unrelated writes"],
                        "assigned_model": "deepseek-chat",
                    }
                ],
            }
        )
    )

    plan = Orchestrator(gateway, config_path=str(config_path)).plan("Write a story")

    assert plan.tasks[0].output_format == 'Plain text\n{"section": "result"}'
    assert plan.tasks[0].acceptance == "Result exists\nNo unrelated writes"


def test_plan_reassigns_creative_worker_for_software_task(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(
        _sample_workers_yaml()
        + """
  backend_dev:
    name: Backend developer
    default_model: kimi-for-coding
""",
        encoding="utf-8",
    )
    gateway = _mock_gateway(
        json.dumps(
            {
                "summary": "Build module",
                "tasks": [
                    {
                        "id": "build",
                        "type": "writer",
                        "title": "Build module",
                        "input": "Create src/main.py",
                        "assigned_model": "glm-ark",
                    }
                ],
            }
        )
    )
    gateway.models = {"glm-ark": object(), "kimi-for-coding": object()}
    gateway.resolve_model = MagicMock(
        side_effect=lambda preferred: preferred if preferred in gateway.models else "glm-ark"
    )

    plan = Orchestrator(gateway, config_path=str(config_path)).plan(
        "Create a Python module"
    )

    assert plan.tasks[0].type == "backend_dev"
    assert plan.tasks[0].assigned_model == "kimi-for-coding"


def test_plan_rejects_unconfigured_worker_type(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(_sample_workers_yaml(), encoding="utf-8")
    gateway = _mock_gateway(
        json.dumps(
            {
                "summary": "Invalid",
                "tasks": [
                    {
                        "id": "mystery",
                        "type": "invented_role",
                        "title": "Mystery",
                        "input": "Do something",
                        "assigned_model": "glm-ark",
                    }
                ],
            }
        )
    )

    with pytest.raises(ValueError, match="未配置的 worker 类型: invented_role"):
        Orchestrator(gateway, config_path=str(config_path)).plan("Do something")


def test_parse_json_bare_json(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("orchestrator:\n  model: glm-ark\n", encoding="utf-8")

    gateway = _mock_gateway("")
    orchestrator = Orchestrator(gateway, config_path=str(config_path))
    data = orchestrator._parse_json('{"summary": "s", "tasks": []}')
    assert data == {"summary": "s", "tasks": []}


def test_parse_json_inside_code_block(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("orchestrator:\n  model: glm-ark\n", encoding="utf-8")

    gateway = _mock_gateway("")
    orchestrator = Orchestrator(gateway, config_path=str(config_path))
    text = '```json\n{"summary": "s", "tasks": []}\n```'
    data = orchestrator._parse_json(text)
    assert data == {"summary": "s", "tasks": []}


def test_parse_json_between_braces_with_trailing_text(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("orchestrator:\n  model: glm-ark\n", encoding="utf-8")

    gateway = _mock_gateway("")
    orchestrator = Orchestrator(gateway, config_path=str(config_path))
    text = 'Here is the plan:\n{"summary": "s", "tasks": []}\nThat is all.'
    data = orchestrator._parse_json(text)
    assert data == {"summary": "s", "tasks": []}


def test_parse_json_normalizes_bare_task_list(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("orchestrator:\n  model: glm-ark\n", encoding="utf-8")

    orchestrator = Orchestrator(_mock_gateway(""), config_path=str(config_path))
    tasks = [{"id": "build", "type": "backend_dev", "title": "Build", "input": "Do it"}]

    assert orchestrator._parse_json(json.dumps(tasks)) == {
        "summary": "",
        "tasks": tasks,
    }


def test_parse_json_normalizes_fenced_task_list(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("orchestrator:\n  model: glm-ark\n", encoding="utf-8")

    orchestrator = Orchestrator(_mock_gateway(""), config_path=str(config_path))
    tasks = [{"id": "verify", "type": "tester", "title": "Verify", "input": "Test it"}]
    text = f"```json\n{json.dumps(tasks)}\n```"

    assert orchestrator._parse_json(text) == {"summary": "", "tasks": tasks}


def test_parse_json_unwraps_one_item_plan_list(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("orchestrator:\n  model: glm-ark\n", encoding="utf-8")

    orchestrator = Orchestrator(_mock_gateway(""), config_path=str(config_path))
    plan = {"summary": "Build and verify", "tasks": []}

    assert orchestrator._parse_json(json.dumps([plan])) == plan


@pytest.mark.parametrize(
    "payload",
    [
        '[{"summary": "first"}, {"summary": "second"}]',
        '"not a plan"',
        "42",
    ],
)
def test_parse_json_rejects_invalid_top_level_shape(tmp_path, payload):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("orchestrator:\n  model: glm-ark\n", encoding="utf-8")

    orchestrator = Orchestrator(_mock_gateway(""), config_path=str(config_path))

    with pytest.raises(ValueError, match="JSON 顶层"):
        orchestrator._parse_json(payload)


def test_parse_json_raises_when_no_json(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("orchestrator:\n  model: glm-ark\n", encoding="utf-8")

    gateway = _mock_gateway("")
    orchestrator = Orchestrator(gateway, config_path=str(config_path))
    with pytest.raises(ValueError, match="无法从模型输出中解析 JSON"):
        orchestrator._parse_json("plain text no json")


def test_init_model_resolution_override_wins(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("orchestrator:\n  model: config-model\n", encoding="utf-8")

    gateway = _mock_gateway("{}", main_model="gateway-model")
    orchestrator = Orchestrator(gateway, config_path=str(config_path), model_override="override-model")

    assert orchestrator.model == "override-model"


def test_init_model_resolution_config_second(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("orchestrator:\n  model: config-model\n", encoding="utf-8")

    gateway = _mock_gateway("{}", main_model="gateway-model")
    orchestrator = Orchestrator(gateway, config_path=str(config_path))

    assert orchestrator.model == "config-model"


def test_init_model_resolution_gateway_main_model_third(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("orchestrator:\n  system_prompt: hi\n", encoding="utf-8")

    gateway = _mock_gateway("{}", main_model="gateway-model")
    orchestrator = Orchestrator(gateway, config_path=str(config_path))

    assert orchestrator.model == "gateway-model"


def test_init_model_resolution_hardcoded_fallback(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("orchestrator:\n  system_prompt: hi\n", encoding="utf-8")

    gateway = _mock_gateway("{}", main_model=None)
    orchestrator = Orchestrator(gateway, config_path=str(config_path))

    assert orchestrator.model == "claude-fable-5"


def test_init_loads_system_prompt(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("orchestrator:\n  system_prompt: 你是专家\n", encoding="utf-8")

    gateway = _mock_gateway("{}")
    orchestrator = Orchestrator(gateway, config_path=str(config_path))

    assert orchestrator.system_prompt == "你是专家"


def test_detect_scenario_novel():
    assert _detect_scenario("帮我写一篇仙侠小说") == "novel"
    assert _detect_scenario("吸血鬼虐恋故事") == "novel"


def test_detect_scenario_software():
    assert _detect_scenario("开发一个前后端登录系统") == "software"
    assert _detect_scenario("做一个网站，有注册功能") == "software"


def test_detect_scenario_programming_request():
    assert _detect_scenario("写一个Hello World Python程序") == "software"
    assert _detect_scenario("用React做个登录页面") == "software"
    assert _detect_scenario("帮我部署一个FastAPI后端") == "software"


def test_plan_appends_scenario_instruction(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("orchestrator:\n  model: glm-ark\n  system_prompt: base\n", encoding="utf-8")

    gateway = _mock_gateway('{"summary": "", "tasks": []}')
    orchestrator = Orchestrator(gateway, config_path=str(config_path))
    orchestrator.plan("帮我写一篇仙侠小说")

    call_kwargs = gateway.chat.call_args.kwargs
    messages = call_kwargs["messages"]
    system_content = messages[0].content
    assert "base" in system_content
    assert "小说创作任务编排规则" in system_content
    assert "章节必须顺序创作" in system_content


def test_plan_appends_software_instruction(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("orchestrator:\n  model: glm-ark\n  system_prompt: base\n", encoding="utf-8")

    gateway = _mock_gateway('{"summary": "", "tasks": []}')
    orchestrator = Orchestrator(gateway, config_path=str(config_path))
    orchestrator.plan("开发一个登录功能")

    call_kwargs = gateway.chat.call_args.kwargs
    messages = call_kwargs["messages"]
    system_content = messages[0].content
    assert "base" in system_content
    assert "软件开发任务编排规则" in system_content
    assert "架构/接口文档" in system_content
    assert "execution_mode=write" in system_content
    assert "owned_paths" in system_content


def test_plan_rejects_parallel_file_ownership_conflict(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(_sample_workers_yaml(), encoding="utf-8")
    plan_data = {
        "summary": "冲突计划",
        "tasks": [
            {
                "id": "a", "type": "writer", "title": "A", "input": "A",
                "assigned_model": "glm-ark", "owned_paths": ["C:/project/src"],
            },
            {
                "id": "b", "type": "writer", "title": "B", "input": "B",
                "assigned_model": "glm-ark", "owned_paths": ["C:/project/src/api"],
            },
        ],
    }
    gateway = _mock_gateway(json.dumps(plan_data))

    with pytest.raises(ValueError, match="文件所有权冲突"):
        Orchestrator(gateway, config_path=str(config_path)).plan("写项目")


def test_high_risk_frontend_plan_enforces_fixed_contract(tmp_path):
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(
        _sample_workers_yaml()
        + """
  architect:
    name: Architect
    default_model: glm-ark
  frontend_dev:
    name: Frontend developer
    default_model: kimi
  backend_dev:
    name: Backend developer
    default_model: kimi
  tester:
    name: Tester
    default_model: glm-ark
""",
        encoding="utf-8",
    )
    root = "G:/MAO_test"
    plan_data = {
        "summary": "智慧矿区前端",
        "frontend_contract": {
            "project_root": root,
            "entrypoints": ["src/main.tsx"],
            "routes": [{"path": "/", "target": "src/pages/Home.tsx"}],
            "dependencies": ["react"],
            "ownership": {
                "architecture": [root],
                "pages": [f"{root}/src/pages"],
                "data": [f"{root}/src/api"],
                "integration": [],
            },
            "verification_commands": ["npm run build"],
            "smoke_paths": ["/"],
            "smoke": {
                "start_command": [
                    "npm", "run", "dev", "--", "--host", "127.0.0.1",
                    "--port", "{port}",
                ],
                "routes": [
                    {"path": "/", "assertions": [{"selector": "#root"}]}
                ],
            },
        },
        "tasks": [
            {
                "id": "architecture", "type": "architect", "title": "架构脚手架",
                "input": "", "assigned_model": "glm-ark", "owned_paths": [root],
                "parallel_safe": False, "frontend_stage": "architecture_scaffold",
            },
            {
                "id": "pages", "type": "frontend_dev", "title": "页面",
                "input": "", "assigned_model": "kimi", "depends_on": ["architecture"],
                "owned_paths": [f"{root}/src/pages"], "frontend_stage": "pages",
            },
            {
                "id": "data", "type": "frontend_dev", "title": "数据 API",
                "input": "", "assigned_model": "glm-ark", "depends_on": ["architecture"],
                "owned_paths": [f"{root}/src/api"], "frontend_stage": "data_api",
            },
            {
                "id": "integration", "type": "tester", "title": "集成验证",
                "input": "", "assigned_model": "glm-ark",
                "depends_on": ["architecture", "pages", "data"],
                "execution_mode": "verify", "owned_paths": [],
                "parallel_safe": False, "frontend_stage": "integration",
            },
        ],
    }
    gateway = _mock_gateway(json.dumps(plan_data, ensure_ascii=False))

    plan = Orchestrator(gateway, config_path=str(config_path)).plan(
        "我现在接了一个智慧矿区的项目，现在给我做一个纯前端项目"
    )

    assert {task.frontend_stage for task in plan.tasks} == {
        "architecture_scaffold", "pages", "data_api", "integration",
    }
    integration = next(task for task in plan.tasks if task.frontend_stage == "integration")
    assert integration.frontend_contract == plan.frontend_contract
    assert set(integration.depends_on) == {"architecture", "pages", "data"}
    prompt = gateway.chat.call_args.kwargs["messages"][0].content
    assert "高风险前端多模型构建合同" in prompt
    assert "Worker 自述不能代替工具证据" in prompt

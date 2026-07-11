"""Orchestrator 单元测试"""
import json
from unittest.mock import MagicMock

import pytest

from src.core.orchestrator import Orchestrator
from src.models.schemas import ChatResponse, TaskPlan


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

    gateway.chat.assert_called_once()
    call_kwargs = gateway.chat.call_args.kwargs
    assert call_kwargs["model_name"] == "glm-ark"
    assert call_kwargs["task_id"] == "orchestrator"


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
    config_path.write_text(_sample_workers_yaml(), encoding="utf-8")

    plan_data = {
        "summary": "未知类型",
        "tasks": [
            {"id": "t1", "type": "unknown_type", "title": "X", "input": "输入", "assigned_model": ""},
        ],
    }
    gateway = _mock_gateway(json.dumps(plan_data))

    orchestrator = Orchestrator(gateway, config_path=str(config_path))
    plan = orchestrator.plan("未知类型")

    assert plan.tasks[0].assigned_model == "glm-ark"


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

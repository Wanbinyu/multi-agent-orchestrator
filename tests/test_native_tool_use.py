"""原生 tool_use 测试"""
from __future__ import annotations

from unittest.mock import MagicMock

from src.core.agent import Agent, TOOL_RULES_NATIVE
from src.core.session import Session
from src.models.schemas import ChatResponse, ModelConfig, ProviderConfig
from src.tools.registry import tool_registry


def _session(tmp_path) -> Session:
    return Session(
        id="s1",
        title="t",
        created_at="2026-07-13T00:00:00+00:00",
        updated_at="2026-07-13T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
    )


def _model_cfg(native_tools=None, capabilities=None) -> ModelConfig:
    return ModelConfig(
        provider="anthropic",
        model_id="claude",
        capabilities=capabilities if capabilities is not None else [],
        native_tools=native_tools,
    )


def _make_gateway(response_text: str, model_cfg: ModelConfig, provider_type: str = "anthropic") -> MagicMock:
    gw = MagicMock()
    gw.main_model = "claude"
    gw.get_model_config.return_value = model_cfg
    prov = MagicMock()
    prov.config = ProviderConfig(
        name="anthropic", type=provider_type, base_url="", api_keys=["k"]
    )
    gw.providers = {"anthropic": prov}
    gw.chat_with_main_model.return_value = ChatResponse(
        content=response_text, model="claude", provider="anthropic",
        input_tokens=10, output_tokens=5, cost_usd=0.0,
    )
    return gw


# ---------- build_tool_schemas ----------


def test_build_tool_schemas_anthropic():
    schemas = tool_registry.build_tool_schemas("anthropic", ["read_file"])
    assert len(schemas) == 1
    s = schemas[0]
    assert s["name"] == "read_file"
    assert "input_schema" in s
    assert s["input_schema"]["type"] == "object"
    assert "path" in s["input_schema"]["properties"]
    assert "path" in s["input_schema"]["required"]


def test_build_tool_schemas_openai():
    schemas = tool_registry.build_tool_schemas("openai", ["read_file"])
    assert len(schemas) == 1
    s = schemas[0]
    assert s["type"] == "function"
    assert s["function"]["name"] == "read_file"
    assert s["function"]["parameters"]["type"] == "object"


def test_build_tool_schemas_optional_param_not_required():
    # search_project_files 的 top_k 有 default，不应出现在 required
    schemas = tool_registry.build_tool_schemas("anthropic", ["search_project_files"])
    required = schemas[0]["input_schema"].get("required", [])
    assert "query" in required
    assert "top_k" not in required


# ---------- Agent native mode detection ----------


def test_native_enabled_by_capability(tmp_path):
    cfg = _model_cfg(capabilities=["tool_use", "coding"])
    gw = _make_gateway("ok", cfg)
    agent = Agent(gw, _session(tmp_path))
    assert agent._should_use_native_tools() is True


def test_native_disabled_without_capability(tmp_path):
    cfg = _model_cfg(capabilities=["coding"])
    gw = _make_gateway("ok", cfg)
    agent = Agent(gw, _session(tmp_path))
    assert agent._should_use_native_tools() is False


def test_native_force_off_overrides_capability(tmp_path):
    cfg = _model_cfg(native_tools=False, capabilities=["tool_use"])
    gw = _make_gateway("ok", cfg)
    agent = Agent(gw, _session(tmp_path))
    assert agent._should_use_native_tools() is False


def test_native_force_on_without_capability(tmp_path):
    cfg = _model_cfg(native_tools=True, capabilities=[])
    gw = _make_gateway("ok", cfg)
    agent = Agent(gw, _session(tmp_path))
    assert agent._should_use_native_tools() is True


# ---------- system prompt in native mode ----------


def test_native_mode_prompt_omits_markdown_tool_list(tmp_path):
    cfg = _model_cfg(capabilities=["tool_use"])
    gw = _make_gateway("ok", cfg)
    agent = Agent(gw, _session(tmp_path))
    agent._ensure_system_prompt("hi")
    prompt = agent.session.messages[0].content
    # 原生模式不含 Markdown 工具块
    assert "```tool:" not in prompt
    assert TOOL_RULES_NATIVE.strip() in prompt


def test_markdown_mode_prompt_includes_tool_list(tmp_path):
    cfg = _model_cfg(capabilities=[])  # 无 tool_use，Markdown 模式
    gw = _make_gateway("ok", cfg)
    agent = Agent(gw, _session(tmp_path))
    agent._ensure_system_prompt("hi")
    prompt = agent.session.messages[0].content
    assert "```tool:read_file" in prompt


# ---------- tools passed to gateway ----------


def test_native_mode_passes_tools_to_gateway(tmp_path):
    cfg = _model_cfg(capabilities=["tool_use"])
    gw = _make_gateway("done", cfg)
    agent = Agent(gw, _session(tmp_path))
    agent.run_turn("hi")
    # chat_with_main_model 被调用时带 tools 参数
    call_kwargs = gw.chat_with_main_model.call_args.kwargs
    assert "tools" in call_kwargs
    assert len(call_kwargs["tools"]) > 0


def test_markdown_mode_does_not_pass_tools(tmp_path):
    cfg = _model_cfg(capabilities=[])
    gw = _make_gateway("done", cfg)
    agent = Agent(gw, _session(tmp_path))
    agent.run_turn("hi")
    call_kwargs = gw.chat_with_main_model.call_args.kwargs
    assert "tools" not in call_kwargs


def test_native_anthropic_schema_type(tmp_path):
    cfg = _model_cfg(capabilities=["tool_use"])
    gw = _make_gateway("ok", cfg, provider_type="anthropic")
    agent = Agent(gw, _session(tmp_path))
    tools = agent._get_native_tools()
    assert tools is not None
    assert "input_schema" in tools[0]  # anthropic 格式


def test_native_openai_schema_type(tmp_path):
    cfg = _model_cfg(capabilities=["tool_use"])
    gw = _make_gateway("ok", cfg, provider_type="openai")
    agent = Agent(gw, _session(tmp_path))
    tools = agent._get_native_tools()
    assert tools is not None
    assert tools[0]["type"] == "function"  # openai 格式

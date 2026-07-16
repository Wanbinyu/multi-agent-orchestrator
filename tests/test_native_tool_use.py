"""原生 tool_use 测试"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from src.core.agent import Agent, TOOL_RULES_NATIVE
from src.core.session import Session
from src.models.schemas import (
    ChatResponse,
    ModelConfig,
    ProviderConfig,
    StreamChunk,
    TextContentBlock,
    ToolResultContentBlock,
    ToolUseContentBlock,
)
from src.tools.registry import tool_registry


def _session(tmp_path) -> Session:
    return Session(
        id="s1",
        title="t",
        created_at="2026-07-13T00:00:00+00:00",
        updated_at="2026-07-13T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
    )


def _model_cfg(native_tools=None, capabilities=None, capability_status=None) -> ModelConfig:
    return ModelConfig(
        provider="anthropic",
        model_id="claude",
        capabilities=capabilities if capabilities is not None else [],
        capability_status=capability_status if capability_status is not None else {},
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


def test_native_disabled_when_tool_capability_is_unverified(tmp_path):
    cfg = _model_cfg(
        capabilities=["tool_use"],
        capability_status={"tool_use": "unverified"},
    )
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


def test_analysis_only_native_mode_exposes_read_tools_only(tmp_path):
    cfg = _model_cfg(capabilities=["tool_use"])
    gw = _make_gateway("done", cfg)
    agent = Agent(gw, _session(tmp_path))

    agent.run_turn("分析项目，只做方案，不修改文件")

    schemas = gw.chat_with_main_model.call_args.kwargs["tools"]
    names = {schema["name"] for schema in schemas}
    assert "read_file" in names
    assert "project_tree" in names
    assert "write_file" not in names
    assert "run_command" not in names


def test_analysis_only_sync_turn_rewrites_overlong_answer_without_tools(tmp_path):
    cfg = _model_cfg(capabilities=["tool_use"])
    gw = _make_gateway("长" * 6001, cfg)
    gw.chat_with_main_model.side_effect = [
        ChatResponse(content="长" * 6001, model="claude", provider="anthropic"),
        ChatResponse(content="完整精简方案", model="claude", provider="anthropic"),
    ]
    agent = Agent(gw, _session(tmp_path))

    result = agent.run_turn("分析项目，只做方案")

    assert result.assistant_message == "完整精简方案"
    assert gw.chat_with_main_model.call_count == 2
    assert gw.chat_with_main_model.call_args.kwargs.get("tools") is None


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


def test_sync_native_write_round_returns_structured_tool_result(tmp_path):
    cfg = _model_cfg(capability_status={"tool_use": "supported"})
    gw = _make_gateway("", cfg)
    tool_block = ToolUseContentBlock(
        id="toolu_write_1",
        name="write_file",
        input={"path": "native.txt", "content": "hello"},
    )
    gw.chat_with_main_model.side_effect = [
        ChatResponse(
            content='```tool:write_file\n{"path":"native.txt","content":"hello"}\n```',
            model="claude",
            provider="anthropic",
            content_blocks=[tool_block],
            provider_payload=[tool_block.model_dump()],
        ),
        ChatResponse(
            content="文件已创建。",
            model="claude",
            provider="anthropic",
            content_blocks=[TextContentBlock(text="文件已创建。")],
        ),
    ]
    session = _session(tmp_path)
    agent = Agent(gw, session)

    result = agent.run_turn("写文件 native.txt，内容为 hello")

    assert (tmp_path / "output" / "native.txt").read_text(encoding="utf-8") == "hello"
    assert result.tool_calls[0]["tool_use_id"] == "toolu_write_1"
    result_message = next(
        message
        for message in session.messages
        if any(isinstance(block, ToolResultContentBlock) for block in message.content_blocks)
    )
    assert isinstance(result_message.content_blocks[0], ToolResultContentBlock)
    assert result_message.content_blocks[0].tool_use_id == "toolu_write_1"
    assert result_message.content_blocks[0].is_error is False


def test_sync_native_tool_error_is_returned_and_recorded_as_evidence(tmp_path):
    cfg = _model_cfg(capability_status={"tool_use": "supported"})
    gw = _make_gateway("", cfg)
    tool_block = ToolUseContentBlock(
        id="toolu_missing_1",
        name="read_file",
        input={"path": "missing.txt"},
    )
    gw.chat_with_main_model.side_effect = [
        ChatResponse(
            content='```tool:read_file\n{"path":"missing.txt"}\n```',
            model="claude",
            provider="anthropic",
            content_blocks=[tool_block],
            provider_payload=[tool_block.model_dump()],
        ),
        ChatResponse(content="文件不存在。", model="claude", provider="anthropic"),
    ]
    session = _session(tmp_path)
    agent = Agent(gw, session)

    result = agent.run_turn("读取 missing.txt 并说明结果")

    assert result.tool_calls[0]["success"] is False
    assert result.tool_calls[0]["tool_use_id"] == "toolu_missing_1"
    assert result.engineering["evidence_count"] >= 1
    result_block = next(
        block
        for message in session.messages
        for block in message.content_blocks
        if isinstance(block, ToolResultContentBlock)
    )
    assert result_block.is_error is True
    assert result_block.tool_use_id == "toolu_missing_1"


def test_stream_native_round_preserves_tool_id(tmp_path):
    cfg = _model_cfg(capability_status={"tool_use": "supported"})
    gw = _make_gateway("", cfg)
    tool_block = ToolUseContentBlock(
        id="toolu_stream_read_1",
        name="read_file",
        input={"path": "hello.txt"},
    )
    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
    (tmp_path / "output" / "hello.txt").write_text("hello", encoding="utf-8")

    async def _chunks(*chunks):
        for chunk in chunks:
            yield chunk

    gw.chat_with_main_model_stream.side_effect = [
        _chunks(
            StreamChunk(
                type="delta",
                content='```tool:read_file\n{"path":"hello.txt"}\n```',
            ),
            StreamChunk(type="usage", input_tokens=5, output_tokens=3),
            StreamChunk(
                type="message_state",
                content_blocks=[tool_block],
                provider_payload=[tool_block.model_dump()],
            ),
        ),
        _chunks(
            StreamChunk(type="delta", content="读取完成。"),
            StreamChunk(type="usage", input_tokens=4, output_tokens=2),
            StreamChunk(
                type="message_state",
                content_blocks=[TextContentBlock(text="读取完成。")],
            ),
        ),
    ]
    session = _session(tmp_path)
    agent = Agent(gw, session)

    async def _run():
        return [event async for event in agent.run_turn_stream("读取 hello.txt")]

    events = asyncio.run(_run())
    done = next(event for event in events if event.type == "done")
    assert done.tool_calls[0]["tool_use_id"] == "toolu_stream_read_1"
    result_block = next(
        block
        for message in session.messages
        for block in message.content_blocks
        if isinstance(block, ToolResultContentBlock)
    )
    assert result_block.tool_use_id == "toolu_stream_read_1"


def test_stream_native_write_round_executes_after_approval(tmp_path):
    cfg = _model_cfg(capability_status={"tool_use": "supported"})
    gw = _make_gateway("", cfg)
    tool_block = ToolUseContentBlock(
        id="toolu_stream_write_1",
        name="write_file",
        input={"path": "approved-native.txt", "content": "approved"},
    )

    async def _chunks(*chunks):
        for chunk in chunks:
            yield chunk

    gw.chat_with_main_model_stream.side_effect = [
        _chunks(
            StreamChunk(
                type="delta",
                content=(
                    '```tool:write_file\n'
                    '{"path":"approved-native.txt","content":"approved"}\n```'
                ),
            ),
            StreamChunk(type="usage", input_tokens=5, output_tokens=3),
            StreamChunk(
                type="message_state",
                content_blocks=[tool_block],
                provider_payload=[tool_block.model_dump()],
            ),
        ),
        _chunks(
            StreamChunk(type="delta", content="文件已创建。"),
            StreamChunk(type="usage", input_tokens=4, output_tokens=2),
            StreamChunk(
                type="message_state",
                content_blocks=[TextContentBlock(text="文件已创建。")],
            ),
        ),
    ]
    session = _session(tmp_path)
    session.approval_mode = "approve"
    agent = Agent(gw, session)

    async def _run():
        events = []
        async for event in agent.run_turn_stream(
            "写文件 approved-native.txt，内容为 approved"
        ):
            events.append(event)
            if event.type == "permission_request":
                request_id = event.permission_request["request_id"]
                asyncio.get_running_loop().call_soon(
                    agent.respond_to_permission, request_id, True
                )
        return events

    events = asyncio.run(_run())
    permission = next(event for event in events if event.type == "permission_request")
    done = next(event for event in events if event.type == "done")

    assert permission.permission_request["tool"] == "write_file"
    assert done.tool_calls[0]["success"] is True
    assert done.tool_calls[0]["tool_use_id"] == "toolu_stream_write_1"
    assert (
        tmp_path / "output" / "approved-native.txt"
    ).read_text(encoding="utf-8") == "approved"
    result_block = next(
        block
        for message in session.messages
        for block in message.content_blocks
        if isinstance(block, ToolResultContentBlock)
    )
    assert result_block.tool_use_id == "toolu_stream_write_1"
    assert result_block.is_error is False

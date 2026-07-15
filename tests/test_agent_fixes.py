"""真实验证发现的问题修复测试"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from src.core.agent import Agent, _COLLABORATION_KEYWORDS
from src.core.session import Session
from src.models.schemas import ChatResponse
import src.tools.worker_tools  # noqa: F401  注册内置工具


def _session(tmp_path) -> Session:
    return Session(
        id="s1",
        title="t",
        created_at="2026-07-14T00:00:00+00:00",
        updated_at="2026-07-14T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
    )


def _mock_gateway_no_native(response_text: str) -> MagicMock:
    """构造不启用原生 tool_use 的 mock gateway"""
    gw = MagicMock()
    gw.main_model = None  # 触发 _should_use_native_tools 返回 False
    gw.chat_with_main_model.return_value = ChatResponse(
        content=response_text, model="m", provider="p",
        input_tokens=10, output_tokens=5, cost_usd=0.0,
    )
    gw.chat_with_main_model_stream = MagicMock()
    return gw


# ---------- Fix 5: 协作关键字预筛 ----------


def test_collaboration_keyword_triggers_without_llm(tmp_path):
    """含项目关键字的输入直接返回 True，不调用 LLM"""
    gw = _mock_gateway_no_native("done")
    agent = Agent(gw, _session(tmp_path))
    result = asyncio.run(agent._should_collaborate("把这几个页面综合起来做一个前后端交互的小项目"))
    assert result is True
    # 未调用 gateway 做 LLM 判断
    gw.chat_with_main_model.assert_not_called()


def test_readonly_intent_skips_collaboration_model_call(tmp_path):
    """解释类只读意图不额外调用模型判断协作。"""
    gw = MagicMock()
    gw.main_model = "m"
    gw.chat_with_main_model.return_value = ChatResponse(
        content='{"collaborate": false}', model="m", provider="p",
        input_tokens=1, output_tokens=1, cost_usd=0.0,
    )
    agent = Agent(gw, _session(tmp_path))
    result = asyncio.run(agent._should_collaborate("解释一下什么是递归"))
    assert result is False
    gw.chat_with_main_model.assert_not_called()


def test_collaboration_keywords_cover_user_case():
    """用户那次输入应命中关键字"""
    user_input = "在G:\\MAO_test中有几个前端，把这几个页面尝试综合起来做一个前后端交互的小项目，先立项，设计项目，再执行"
    assert any(kw in user_input for kw in _COLLABORATION_KEYWORDS)


# ---------- Fix 3: 不再生成 generated_N ----------


def test_run_turn_no_generated_files(tmp_path):
    """模型回复含代码块但没调 write_file 时，只生成 response.md，不生成 generated_N"""
    # 模型直接回复最终文本（含代码块），不调用工具
    response_with_codeblock = "这是答案：\n```html\n<h1>hi</h1>\n```\n完成"
    gw = _mock_gateway_no_native(response_with_codeblock)
    agent = Agent(gw, _session(tmp_path), approval_mode="auto")
    result = agent.run_turn("做个页面")
    import os
    basenames = [os.path.basename(f) for f in result.files_written]
    # 不应出现 generated_N 文件（检查文件名，不含路径中的测试目录名干扰）
    assert not any(b.startswith("generated_") for b in basenames), basenames
    # 应有 response.md 兜底
    assert "response.md" in basenames


def test_run_turn_write_file_not_overwritten_by_response_md(tmp_path):
    """模型用 write_file 写了文件时，不再额外写 response.md"""
    write_call = '```tool:write_file\n{"path": "demo.html", "content": "<h1>hi</h1>"}\n```'
    # 第一次返回工具调用，第二次返回纯文本
    gw = MagicMock()
    gw.main_model = None
    gw.chat_with_main_model.side_effect = [
        ChatResponse(content=write_call, model="m", provider="p", input_tokens=1, output_tokens=1, cost_usd=0.0),
        ChatResponse(content="完成了", model="m", provider="p", input_tokens=1, output_tokens=1, cost_usd=0.0),
    ]
    agent = Agent(gw, _session(tmp_path), approval_mode="auto")
    result = agent.run_turn("写个页面")
    # write_file 写了 demo.html
    assert any("demo.html" in f for f in result.files_written)
    # 已有显式文件，不应再兜底 response.md
    assert not any(f.endswith("response.md") for f in result.files_written)


# ---------- Fix 1: list_dir 注册 ----------


def test_list_dir_registered():
    from src.tools.registry import tool_registry

    assert "list_dir" in tool_registry.list_tools()


# ---------- Fix 2: glob_files path 参数 ----------


def test_glob_files_schema_has_path_param():
    from src.tools.registry import tool_registry

    spec = tool_registry.get("glob_files")
    assert spec is not None
    assert "path" in spec.params

"""Hooks 测试"""
from __future__ import annotations

import pytest

from src.core.hooks import AuditLogHook, HookAbort, HookRegistry, load_hooks_from_config
from src.tools.registry import ToolRegistry
from src.tools.tool_result import ToolResult


# ---------- HookRegistry ----------


def _reg_with_echo() -> ToolRegistry:
    reg = ToolRegistry()

    @reg.register(
        name="echo",
        description="返回文本",
        params={"text": {"type": "string"}},
        category="read",
    )
    def echo(text: str, base_dir: str = ".") -> ToolResult:
        return ToolResult(success=True, output=text)

    return reg


def test_pre_hook_can_modify_params():
    reg = _reg_with_echo()

    def upper(tool_name, params):
        return {"text": params["text"].upper()}

    reg.add_pre_hook(upper)
    result = reg.execute("echo", {"text": "hi"}, base_dir=".")
    assert result.output == "HI"


def test_pre_hook_return_none_keeps_params():
    reg = _reg_with_echo()
    reg.add_pre_hook(lambda n, p: None)
    result = reg.execute("echo", {"text": "hi"}, base_dir=".")
    assert result.output == "hi"


def test_pre_hook_abort_blocks_execution():
    reg = _reg_with_echo()
    calls = []

    def veto(tool_name, params):
        calls.append(tool_name)
        raise HookAbort("禁止")

    reg.add_pre_hook(veto)
    result = reg.execute("echo", {"text": "hi"}, base_dir=".")
    assert result.success is False
    assert "禁止" in result.error
    # 工具本体未执行（echo 无副作用，靠 calls 仅记录钩子触发）
    assert calls == ["echo"]


def test_pre_hook_exception_does_not_block():
    reg = _reg_with_echo()

    def broken(tool_name, params):
        raise RuntimeError("钩子炸了")

    reg.add_pre_hook(broken)
    result = reg.execute("echo", {"text": "hi"}, base_dir=".")
    # 钩子异常不中断，工具正常执行
    assert result.success is True
    assert result.output == "hi"


def test_post_hook_can_modify_result():
    reg = _reg_with_echo()

    def tag(tool_name, params, result):
        return ToolResult(success=True, output=f"[{result.output}]")

    reg.add_post_hook(tag)
    result = reg.execute("echo", {"text": "hi"}, base_dir=".")
    assert result.output == "[hi]"


def test_post_hook_return_none_keeps_result():
    reg = _reg_with_echo()
    reg.add_post_hook(lambda n, p, r: None)
    result = reg.execute("echo", {"text": "hi"}, base_dir=".")
    assert result.output == "hi"


def test_post_hook_exception_does_not_break():
    reg = _reg_with_echo()

    def broken(tool_name, params, result):
        raise RuntimeError("post 炸了")

    reg.add_post_hook(broken)
    result = reg.execute("echo", {"text": "hi"}, base_dir=".")
    assert result.success is True
    assert result.output == "hi"


def test_hooks_apply_to_source_tools():
    reg = ToolRegistry()
    from src.tools.registry import ToolSpec

    class _Src:
        def list_tools(self):
            return [ToolSpec(name="ext", description="x", params={}, callable=lambda **_: ToolResult(), category="external")]

        def execute(self, name, params):
            return ToolResult(success=True, output="raw")

    reg.add_source(_Src())
    reg.add_post_hook(lambda n, p, r: ToolResult(success=True, output=r.output + "+hook"))
    result = reg.execute("ext", {}, base_dir=".")
    assert result.output == "raw+hook"


def test_hook_registry_clear():
    hr = HookRegistry()
    hr.add_pre(lambda n, p: None)
    hr.add_post(lambda n, p, r: None)
    hr.clear()
    assert hr._pre == []
    assert hr._post == []


# ---------- AuditLogHook ----------


def test_audit_log_hook_writes_log(tmp_path):
    log = tmp_path / "audit.log"
    hook = AuditLogHook(log_path=str(log))
    hook.pre("read_file", {"path": "a.txt"})
    result = ToolResult(success=True, output="content")
    hook.post("read_file", {"path": "a.txt"}, result)
    text = log.read_text(encoding="utf-8")
    assert "CALL read_file" in text
    assert "OK read_file" in text


# ---------- 配置加载 ----------


def _hook_module_path() -> str:
    return "src.core.hooks"


def test_load_hooks_from_config_missing_file(tmp_path):
    hr = HookRegistry()
    count = load_hooks_from_config(tmp_path / "nope.yaml", hr)
    assert count == 0


def test_load_hooks_from_config(tmp_path):
    # 用 AuditLogHook 的 pre/post 方法做可导入 callable
    # 注册一个模块级函数供导入
    cfg = tmp_path / "hooks.yaml"
    cfg.write_text(
        "pre:\n"
        "  - tests.test_hooks._sample_pre\n"
        "post:\n"
        "  - tests.test_hooks._sample_post\n",
        encoding="utf-8",
    )
    hr = HookRegistry()
    count = load_hooks_from_config(cfg, hr)
    assert count == 2
    assert len(hr._pre) == 1
    assert len(hr._post) == 1


def test_load_hooks_invalid_dotted(tmp_path):
    cfg = tmp_path / "hooks.yaml"
    cfg.write_text("pre:\n  - nosuchmodule.fn\n", encoding="utf-8")
    hr = HookRegistry()
    with pytest.raises(Exception):
        load_hooks_from_config(cfg, hr)


# 模块级函数，供配置导入测试
def _sample_pre(tool_name, params):
    return None


def _sample_post(tool_name, params, result):
    return None

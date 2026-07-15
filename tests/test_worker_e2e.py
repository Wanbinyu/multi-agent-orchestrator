"""Worker 端到端单元测试"""
from unittest.mock import MagicMock

import pytest

from src.core.worker import Worker
from src.models.schemas import ChatResponse, ModelConfig, ProviderConfig, Task


def _mock_gateway(response_content: str) -> MagicMock:
    gateway = MagicMock()
    gateway.chat.return_value = ChatResponse(
        content=response_content,
        model="glm-ark",
        provider="ark",
        input_tokens=20,
        output_tokens=10,
        cost_usd=0.0002,
    )
    return gateway


def _sample_workers_config(tools: list[str] | None = None) -> dict:
    return {
        "frontend": {
            "name": "前端工程师",
            "default_model": "glm-ark",
            "system_prompt": "你是前端专家",
            "tools": tools or ["write_file"],
        }
    }


def test_execute_does_not_generate_files_from_code_blocks(tmp_path):
    gateway = _mock_gateway("""```html
<input type="text" />
```
```css
body { margin: 0; }
```
""")
    worker = Worker(gateway, _sample_workers_config())
    task = Task(
        id="t1",
        type="frontend",
        title="登录页面",
        input="写一个登录页面",
        assigned_model="glm-ark",
    )
    output_dir = tmp_path / "out"

    result = worker.execute(task, output_dir=str(output_dir))

    assert result.success is False
    assert result.task.id == "t1"
    assert result.response is not None
    assert len(result.files_written) == 1
    assert (output_dir / "frontend_t1" / "content.txt").exists()
    assert not list(output_dir.rglob("generated_*"))
    assert gateway.chat.call_count == 2


def test_analysis_worker_code_example_is_preserved_without_false_failure(tmp_path):
    gateway = _mock_gateway("分析示例：\n```python\nprint(1)\n```")
    config = {
        "architect": {
            "name": "架构师",
            "default_model": "glm-ark",
            "system_prompt": "分析系统",
            "tools": ["write_file", "read_file"],
        }
    }
    worker = Worker(gateway, config)
    task = Task(
        id="t1", type="architect", title="分析", input="分析现有架构",
        assigned_model="glm-ark",
    )

    result = worker.execute(task, output_dir=str(tmp_path / "out"))

    assert result.success is True
    assert gateway.chat.call_count == 1
    assert result.files_written[0].endswith("content.txt")


def test_execute_recovers_code_blocks_with_explicit_write_file(tmp_path):
    gateway = MagicMock()
    gateway.resolve_model.return_value = "glm-ark"
    gateway.get_model_config.side_effect = AttributeError
    gateway.chat.side_effect = [
        ChatResponse(
            content="```html\n<h1>hello</h1>\n```",
            model="glm-ark", provider="ark", input_tokens=2, output_tokens=2,
        ),
        ChatResponse(
            content=(
                '```tool:write_file\n'
                '{"path":"index.html","content":"<h1>hello</h1>"}\n```'
            ),
            model="glm-ark", provider="ark", input_tokens=3, output_tokens=3,
        ),
        ChatResponse(
            content="index.html 已创建。",
            model="glm-ark", provider="ark", input_tokens=4, output_tokens=4,
        ),
    ]
    worker = Worker(gateway, _sample_workers_config())
    task = Task(
        id="t1", type="frontend", title="页面", input="创建页面",
        assigned_model="glm-ark",
    )
    output_dir = tmp_path / "out"

    result = worker.execute(task, output_dir=str(output_dir))

    assert result.success is True
    assert (output_dir / "frontend_t1" / "index.html").read_text() == "<h1>hello</h1>"
    assert not list(output_dir.rglob("generated_*"))
    assert result.response.input_tokens == 9
    assert result.response.output_tokens == 9


def test_execute_uses_native_tools_without_markdown_prompt_conflict(tmp_path):
    gateway = MagicMock()
    gateway.resolve_model.return_value = "glm-ark"
    gateway.get_model_config.return_value = ModelConfig(
        provider="ark", model_id="ark-code-latest", capabilities=["tool_use"]
    )
    provider = MagicMock()
    provider.config = ProviderConfig(
        name="ark", type="anthropic", base_url="https://example.com", api_keys=["k"]
    )
    gateway.providers = {"ark": provider}
    gateway.chat.side_effect = [
        ChatResponse(
            content=(
                '```tool:write_file\n'
                '{"path":"main.py","content":"print(1)"}\n```'
            ),
            model="glm-ark", provider="ark",
        ),
        ChatResponse(content="完成", model="glm-ark", provider="ark"),
    ]
    worker = Worker(gateway, _sample_workers_config())
    task = Task(
        id="t1", type="frontend", title="原生工具", input="创建文件",
        assigned_model="glm-ark",
    )

    result = worker.execute(task, output_dir=str(tmp_path / "out"))

    assert result.success is True
    first_call = gateway.chat.call_args_list[0]
    assert "tools" in first_call.kwargs
    prompt = first_call.kwargs["messages"][1].content
    assert "原生 tool_use" in prompt
    assert "```tool:" not in prompt


def test_execute_unknown_worker_type():
    gateway = _mock_gateway("")
    worker = Worker(gateway, _sample_workers_config())
    task = Task(
        id="t1",
        type="backend",
        title="API",
        input="写 API",
        assigned_model="glm-ark",
    )

    result = worker.execute(task)

    assert result.success is False
    assert result.error == "未知的 worker 类型: backend"
    gateway.chat.assert_not_called()


def test_execute_catches_gateway_exception():
    gateway = MagicMock()
    gateway.chat.side_effect = RuntimeError("模型调用失败")
    worker = Worker(gateway, _sample_workers_config())
    task = Task(
        id="t1",
        type="frontend",
        title="登录页面",
        input="写一个登录页面",
        assigned_model="glm-ark",
    )

    result = worker.execute(task)

    assert result.success is False
    assert "模型调用失败" in result.error


def test_execute_processes_tool_calls(tmp_path):
    output_dir = tmp_path / "out"
    task_output_dir = output_dir / "frontend_t1"
    task_output_dir.mkdir(parents=True)
    test_file = task_output_dir / "data.txt"
    test_file.write_text("file content", encoding="utf-8")

    first_response = """读取文件结果：
```tool:read_file
{\"path\": \"data.txt\"}
```
"""
    gateway = MagicMock()
    gateway.resolve_model.return_value = "glm-ark"
    gateway.get_model_config.side_effect = AttributeError

    def _chat(*args, **kwargs):
        messages = kwargs["messages"]
        if gateway.chat.call_count == 1:
            return ChatResponse(content=first_response, model="glm-ark", provider="ark")
        if gateway.chat.call_count == 2:
            assert "file content" in messages[-1].content
            return ChatResponse(
                content=(
                    '```tool:write_file\n'
                    '{"path":"result.py","content":"print(\\"ok\\")"}\n```'
                ),
                model="glm-ark", provider="ark",
            )
        return ChatResponse(
            content="已根据文件内容创建 result.py。",
            model="glm-ark", provider="ark",
        )

    gateway.chat.side_effect = _chat
    worker = Worker(gateway, _sample_workers_config(tools=["write_file", "read_file"]))
    task = Task(
        id="t1",
        type="frontend",
        title="读取并处理",
        input="读取文件",
        assigned_model="glm-ark",
    )

    result = worker.execute(task, output_dir=str(output_dir))

    assert result.success is True
    assert "已根据文件内容" in result.content
    assert len(result.files_written) == 1
    assert (task_output_dir / "result.py").read_text() == 'print("ok")'
    assert gateway.chat.call_count == 3


def test_execute_rejects_tool_not_granted_to_worker(tmp_path):
    gateway = _mock_gateway(
        '```tool:run_command\n{"command":"python --version"}\n```'
    )
    worker = Worker(
        gateway,
        _sample_workers_config(tools=["write_file"]),
        max_tool_iterations=1,
    )
    task = Task(
        id="t1", type="frontend", title="权限", input="运行命令",
        assigned_model="glm-ark",
    )

    result = worker.execute(task, output_dir=str(tmp_path / "out"))

    assert result.success is True
    returned_results = gateway.chat.call_args_list[1].kwargs["messages"][-2].content
    assert "未获授权" in returned_results


def test_execute_substitutes_dependency_placeholders(tmp_path):
    gateway = _mock_gateway("```python\nprint(1)\n```")
    worker = Worker(gateway, _sample_workers_config())
    task = Task(
        id="t2",
        type="frontend",
        title="依赖任务",
        input="基于 {{t1.output}} 继续",
        output_format="参考 {{t1.output}} 的格式",
        acceptance="必须包含 {{t1.output}} 的核心逻辑",
        assigned_model="glm-ark",
    )

    worker.execute(task, output_dir=str(tmp_path / "out"), context={"t1": "第一章内容"})

    call_args = gateway.chat.call_args.kwargs
    messages = call_args["messages"]
    user_content = messages[1].content
    assert "基于 第一章内容 继续" in user_content
    assert "参考 第一章内容 的格式" in user_content
    assert "必须包含 第一章内容 的核心逻辑" in user_content
    assert "前置任务输出" in user_content
    assert "--- [t1] 开始 ---" in user_content


def test_execute_passes_worker_system_prompt_to_gateway(tmp_path):
    gateway = _mock_gateway("```python\nprint(1)\n```")
    worker = Worker(gateway, _sample_workers_config())
    task = Task(
        id="t1",
        type="frontend",
        title="简单任务",
        input="写代码",
        assigned_model="glm-ark",
    )

    worker.execute(task, output_dir=str(tmp_path / "out"))

    call_args = gateway.chat.call_args.kwargs
    messages = call_args["messages"]
    assert messages[0].role == "system"
    assert messages[0].content == "你是前端专家"


def test_execute_saves_plain_text_as_content_file_when_no_code_blocks(tmp_path):
    gateway = _mock_gateway("这是一段没有代码块的普通正文内容。")
    worker = Worker(gateway, _sample_workers_config())
    task = Task(
        id="t1",
        type="frontend",
        title="纯文本任务",
        input="输出一段文字",
        assigned_model="glm-ark",
    )
    output_dir = tmp_path / "out"

    result = worker.execute(task, output_dir=str(output_dir))

    assert result.success is True
    assert len(result.files_written) == 1
    content_path = output_dir / "frontend_t1" / "content.txt"
    assert content_path.exists()
    assert content_path.read_text(encoding="utf-8") == "这是一段没有代码块的普通正文内容。"

"""Worker 端到端单元测试"""
from unittest.mock import MagicMock

import pytest

from src.core.worker import Worker
from src.models.schemas import ChatResponse, Task


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


def test_execute_writes_code_blocks_to_disk(tmp_path):
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

    assert result.success is True
    assert result.task.id == "t1"
    assert result.response is not None
    assert len(result.files_written) == 2
    assert (output_dir / "frontend_t1" / "generated_1.html").exists()
    assert (output_dir / "frontend_t1" / "generated_2.css").exists()


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

    response = """读取文件结果：
```tool:read_file
{\"path\": \"data.txt\"}
```

```python
print("ok")
```
"""
    gateway = _mock_gateway(response)
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
    assert "[工具 read_file 执行结果]" in result.content
    assert "file content" in result.content
    assert len(result.files_written) == 1


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

# 步骤 1：Reviewer 收口流程

## 目标

补齐 Orchestrator → Workers → Reviewer 的闭环。  
Worker 并发执行完毕后，由 Reviewer（审查工程师）汇总所有子任务结果与原始需求，检查一致性、完整性和明显错误，并输出 `final_output` 作为最终整合内容。

---

## 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `src/core/reviewer.py`（新增） | Reviewer 类：加载配置、构造审查提示词、调用模型、解析 JSON |
| `run.py` | 引入 `Reviewer`；Worker 执行后调用 Reviewer；把审查结论追加到 `summary.md` 并打印 |
| `src/tools/file_tools.py` | `write_text_file` 增加 `append=True` 参数，支持追加写入 |
| `tests/test_reviewer.py`（新增） | Reviewer 的单元测试：JSON 输出解析、代码块解析、非 JSON 兜底 |

---

## 关键实现说明

### 1. Reviewer 类

```python
class Reviewer:
    def __init__(
        self,
        gateway: GatewayClient,
        config_path: str = "config/workers.yaml",
        model_override: str | None = None,
    ):
        ...

    def review(self, user_request: str, plan: TaskPlan, results: list[TaskResult]) -> ReviewResult:
        """执行审查"""
        messages = [
            ChatMessage(role="system", content=self.system_prompt),
            ChatMessage(role="user", content=self._build_review_prompt(...)),
        ]
        response = self.gateway.chat(messages=messages, model_name=self.model, task_id="reviewer", ...)
        review_data = self._parse_json(response.content)
        return ReviewResult(...)
```

- 模型和提示词从 `config/workers.yaml` 的 `reviewer` 段落读取。
- 支持 `model_override`，方便后续通过 CLI 参数覆盖。
- 提示词包含：原始需求、任务总览、每个 Worker 的状态/输出文件/输出内容。

### 2. 输出格式兼容

Reviewer 期望模型输出 JSON：

```json
{
  "passed": true,
  "issues": [],
  "final_output": "整合后的最终内容"
}
```

解析逻辑兼容三种情况：

1. 纯 JSON 文本
2. ` ```json ... ``` ` 代码块包裹的 JSON
3. 非 JSON 输出：直接当作 `final_output`，`passed=true`

### 3. run.py 调用流程

```
Orchestrator 拆任务
    ↓
Dispatcher 并发执行 Worker
    ↓
生成 Worker 结果汇总并写入 summary.md
    ↓
Reviewer.review(request, plan, results)
    ↓
把 Reviewer 结论追加到 summary.md
    ↓
终端打印通过/未通过、问题列表、最终整合输出
    ↓
打印计费
```

### 4. summary.md 追加内容示例

```markdown
# Reviewer 审查结论

**审查结果**：通过

**最终整合输出**：

整合后的登录页面包含 HTML、CSS 和 JavaScript，实现了用户名/密码输入、表单验证和提交功能...
```

---

## 测试方法

### 1. 运行单元测试

```bash
cd E:\multi-agent-orchestrator
python -m pytest tests/test_reviewer.py tests/test_provider_model_map.py -v
```

当前输出：

```text
tests/test_reviewer.py::test_reviewer_parses_json_output PASSED
tests/test_reviewer.py::test_reviewer_parses_json_in_code_block PASSED
tests/test_reviewer.py::test_reviewer_fallback_for_non_json PASSED
tests/test_provider_model_map.py::test_anthropic_provider_model_mapping PASSED
tests/test_provider_model_map.py::test_anthropic_provider_model_no_mapping PASSED
tests/test_provider_model_map.py::test_openai_provider_model_mapping PASSED
tests/test_provider_model_map.py::test_factory_creates_provider_with_model_map PASSED
============================== 7 passed in 1.52s ==============================
```

### 2. 端到端验证（需要有效 API Key）

```bash
python run.py "帮我写一个前后端分离的登录页面，前端用 React，后端用 FastAPI" --output "E:\登录页"
```

预期终端输出：

```text
🔍 Reviewer 正在审查结果...
✅ Reviewer 审查通过
📝 最终整合输出：
[整合后的内容摘要]
```

并且 `E:\登录页\summary.md` 末尾会出现 `# Reviewer 审查结论` 段落。

---

## 遇到的问题与解决方案

### 问题 1：write_text_file 不支持追加

**现象**：Reviewer 结论需要在原有 `summary.md` 后面追加，但原函数每次都会覆盖文件。

**解决**：给 `write_text_file` 增加 `append: bool = False` 参数：

```python
def write_text_file(filename: str, content: str, output_dir: str = "output", append: bool = False) -> str:
    mode = "a" if append else "w"
    ...
```

不影响原有调用。

### 问题 2：Reviewer 输出非 JSON 时直接报错

**现象**：测试用例中模型返回纯文本，`_parse_json` 抛出 `ValueError`。

**解决**：在 `review()` 中捕获 `ValueError`，直接把原文当作 `final_output`，避免因为模型格式不标准导致整个流程中断。

### 问题 3：测试中 workers.yaml 加载路径

**现象**：Reviewer 默认读取 `config/workers.yaml`，但测试运行在临时目录。

**解决**：测试中显式传入 `config_path=str(config_path)`，并在临时目录写入最小 workers.yaml。后续可考虑把配置加载抽象成可注入接口。

---

## 下一步建议

Reviewer 收口流程已经补齐，推荐下一步：

- **步骤 3：任务依赖图调度**  
  给 `Task` 增加 `depends_on` 字段，让 Dispatcher 支持 DAG 执行。这样 Orchestrator 才能表达真实软件开发中的先后顺序（如先写后端 API，再写前端，再写测试）。

其它可选项：

- **步骤 4：扩展 Worker 工具集**（read_file、run_command）
- **步骤 5：setup 向导生成 providers.yaml**

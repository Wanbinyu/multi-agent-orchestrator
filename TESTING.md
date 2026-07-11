# 测试指南

## 环境要求

- Python 3.11+
- 项目依赖：`pip install -r requirements.txt`

## 运行测试

```bash
# 运行全部测试
python -m pytest

# 运行单个文件
python -m pytest tests/test_orchestrator.py

# 详细输出
python -m pytest -v

# 显示 print 输出
python -m pytest -s

# 生成覆盖率报告（需安装 pytest-cov）
pip install pytest-cov
python -m pytest --cov=src --cov-report=term-missing
```

## 测试设计原则

- **不发起真实 HTTP 请求**：Provider 层使用 `unittest.mock.MagicMock` 模拟。
- **重试测试不等待**：mock `src.gateway.client.time.sleep` 以加速。
- **文件系统测试隔离**：使用 pytest 内置 `tmp_path` fixture。
- **CLI 测试使用 CliRunner**：调用 `typer.testing.CliRunner` 验证命令行为。
- **中文断言**：错误信息保留中文原文，与代码实现保持一致。

## 测试结构

| 文件 | 覆盖范围 |
|---|---|
| `tests/test_orchestrator.py` | Orchestrator 任务拆分、JSON 解析、模型回退 |
| `tests/test_gateway_client.py` | GatewayClient 配置加载、重试、计费、主模型 |
| `tests/test_worker_e2e.py` | Worker 执行、文件写入、工具调用、异常处理 |
| `tests/test_run_cli.py` | CLI 命令、帮助、默认子命令注入 |
| `tests/test_file_tools.py` | 代码块解析、文件名推断、文件写入/追加 |
| `tests/test_dispatcher.py` | DAG 并行、依赖顺序、级联失败 |
| `tests/test_dispatcher_edge_cases.py` | 空任务、循环依赖、缺失依赖 |
| `tests/test_model_router.py` | 模型路由解析 |
| `tests/test_provider_model_map.py` | Provider model_map 映射 |
| `tests/test_provider_rotation.py` | API key 轮询、map_model_id 回退 |
| `tests/test_reviewer.py` | Reviewer JSON 解析 |
| `tests/test_setup_wizard.py` | 配置向导 helper 函数 |
| `tests/test_worker.py` | Worker 工具指令与 tool_calls 处理 |
| `tests/test_worker_tools.py` | read_file / run_command 直接测试 |
| `tests/test_connection_test.py` | Provider 连通性测试 |
| `tests/test_model_catalog.py` | 内置模型目录 |

## 添加新测试

1. 优先使用模块内 helper 函数创建输入数据，不依赖全局 fixtures。
2. 需要网关的地方使用 `MagicMock(spec=GatewayClient)`。
3. 需要配置文件的地方写入 `tmp_path`。
4. 断言错误信息时保留中文原文。

## 本地验证

```bash
cd E:\multi-agent-orchestrator

# 全量测试
python -m pytest -q

# 验证 CLI 帮助
python run.py --help
python run.py run --help
python run.py setup --help
python run.py agent-setup --help
```

预期结果：
- 所有测试通过
- 无真实 API 调用
- CLI 帮助正常显示

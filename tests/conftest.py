"""测试公共配置"""
import os
import sys

import pytest

# 把项目根目录加入 Python 路径，使 src.* 导入可用
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


@pytest.fixture(autouse=True)
def _cleanup_external_tool_sources():
    """Prevent MCP/background sources from leaking across tests or interpreter exit."""
    yield
    from src.tools.extensions import shutdown_extensions

    shutdown_extensions()

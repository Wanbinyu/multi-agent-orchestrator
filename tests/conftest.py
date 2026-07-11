"""测试公共配置"""
import os
import sys

# 把项目根目录加入 Python 路径，使 src.* 导入可用
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

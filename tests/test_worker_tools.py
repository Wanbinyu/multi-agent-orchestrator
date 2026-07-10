"""Worker 工具单元测试"""
import os
from pathlib import Path

import pytest

from src.tools.worker_tools import read_file, run_command


def test_read_file_success(tmp_path):
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello world", encoding="utf-8")

    result = read_file("hello.txt", str(tmp_path))
    assert result.success is True
    assert result.output == "hello world"


def test_read_file_not_found(tmp_path):
    result = read_file("not_exist.txt", str(tmp_path))
    assert result.success is False
    assert "不存在" in result.error


def test_read_file_path_traversal(tmp_path):
    result = read_file("../outside.txt", str(tmp_path))
    assert result.success is False
    assert "越界" in result.error


def test_run_command_allowed(tmp_path):
    # 使用跨平台的命令
    result = run_command("python --version", str(tmp_path))
    assert result.success is True
    assert "Python" in result.output


def test_run_command_not_allowed(tmp_path):
    result = run_command("rm -rf /", str(tmp_path))
    assert result.success is False
    assert "白名单" in result.error


def test_run_command_custom_whitelist(tmp_path):
    result = run_command("echo hello", str(tmp_path), allowed_prefixes=["echo "])
    assert result.success is True
    assert "hello" in result.output


def test_run_command_timeout(tmp_path):
    # 用 sleep 测试超时，Windows 没有 sleep 命令，用 python 代替
    result = run_command("python -c \"import time; time.sleep(5)\"", str(tmp_path), timeout=1)
    assert result.success is False
    assert "超时" in result.error

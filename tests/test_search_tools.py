"""edit_file / glob_files / grep_content / list_dir 工具测试"""
from __future__ import annotations

from src.tools.search_tools import glob_files, grep_content, list_dir
from src.tools.worker_tools import edit_file, write_file


# ---------- edit_file ----------


def test_edit_file_replaces_unique(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello world\nfoo bar\n", encoding="utf-8")
    result = edit_file("a.txt", "foo bar", "baz qux", base_dir=str(tmp_path))
    assert result.success is True
    assert f.read_text(encoding="utf-8") == "hello world\nbaz qux\n"


def test_edit_file_not_found(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello\n", encoding="utf-8")
    result = edit_file("a.txt", "missing", "x", base_dir=str(tmp_path))
    assert result.success is False
    assert "未在文件中找到" in result.error


def test_edit_file_not_unique(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("dup\ndup\n", encoding="utf-8")
    result = edit_file("a.txt", "dup", "x", base_dir=str(tmp_path))
    assert result.success is False
    assert "不唯一" in result.error


def test_edit_file_empty_old_string(tmp_path):
    result = edit_file("a.txt", "", "x", base_dir=str(tmp_path))
    assert result.success is False


def test_edit_file_missing_file(tmp_path):
    result = edit_file("nope.txt", "a", "b", base_dir=str(tmp_path))
    assert result.success is False
    assert "不存在" in result.error


def test_edit_file_creates_parent_ok_when_target_exists(tmp_path):
    f = tmp_path / "sub" / "a.txt"
    f.parent.mkdir()
    f.write_text("old\n", encoding="utf-8")
    result = edit_file("sub/a.txt", "old", "new", base_dir=str(tmp_path))
    assert result.success is True
    assert f.read_text(encoding="utf-8") == "new\n"


# ---------- glob_files ----------


def test_glob_files_recursive(tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.py").write_text("x")
    (tmp_path / "src" / "c.txt").write_text("x")
    result = glob_files("**/*.py", base_dir=str(tmp_path))
    assert result.success is True
    assert "a.py" in result.output
    assert "b.py" in result.output
    assert "c.txt" not in result.output


def test_glob_files_no_match(tmp_path):
    result = glob_files("*.nonexistent", base_dir=str(tmp_path))
    assert result.success is True
    assert "未找到" in result.output


def test_glob_files_empty_pattern(tmp_path):
    result = glob_files("", base_dir=str(tmp_path))
    assert result.success is False


# ---------- grep_content ----------


def test_grep_content_finds_matches(tmp_path):
    (tmp_path / "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def bar():\n    return 1\n", encoding="utf-8")
    result = grep_content(r"def \w+", path=".", base_dir=str(tmp_path))
    assert result.success is True
    assert "foo" in result.output
    assert "bar" in result.output


def test_grep_content_specific_file(tmp_path):
    (tmp_path / "a.py").write_text("target line\nother\n", encoding="utf-8")
    result = grep_content("target", path="a.py", base_dir=str(tmp_path))
    assert result.success is True
    assert "target line" in result.output
    assert "1:" in result.output  # 行号


def test_grep_content_no_match(tmp_path):
    (tmp_path / "a.py").write_text("hello\n", encoding="utf-8")
    result = grep_content("zzzzz", path=".", base_dir=str(tmp_path))
    assert result.success is True
    assert "未找到" in result.output


def test_grep_content_invalid_regex(tmp_path):
    result = grep_content("(unclosed", path=".", base_dir=str(tmp_path))
    assert result.success is False
    assert "正则" in result.error


def test_grep_content_empty_pattern(tmp_path):
    result = grep_content("", path=".", base_dir=str(tmp_path))
    assert result.success is False


# ---------- registration ----------


def test_new_tools_registered():
    from src.tools.registry import tool_registry

    for name in ("edit_file", "glob_files", "grep_content", "list_dir"):
        assert name in tool_registry.list_tools()


# ---------- list_dir ----------


def test_list_dir_lists_entries(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    result = list_dir(".", base_dir=str(tmp_path))
    assert result.success is True
    assert "a.txt" in result.output
    assert "sub/" in result.output  # 目录带斜杠


def test_list_dir_absolute_path(tmp_path):
    (tmp_path / "hello.txt").write_text("x")
    result = list_dir(str(tmp_path))  # 绝对路径
    assert result.success is True
    assert "hello.txt" in result.output


def test_list_dir_not_exist(tmp_path):
    result = list_dir("nope", base_dir=str(tmp_path))
    assert result.success is False
    assert "不存在" in result.error


def test_list_dir_not_a_directory(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    result = list_dir("a.txt", base_dir=str(tmp_path))
    assert result.success is False
    assert "不是目录" in result.error


def test_list_dir_empty(tmp_path):
    result = list_dir(".", base_dir=str(tmp_path))
    assert result.success is True
    assert "为空" in result.output


# ---------- glob_files 绝对路径支持 ----------


def test_glob_files_with_absolute_path_root(tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.py").write_text("x")
    # 用绝对路径作为搜索根
    result = glob_files("**/*.py", path=str(tmp_path))
    assert result.success is True
    assert "a.py" in result.output
    assert "b.py" in result.output


def test_glob_files_path_param_backward_compat(tmp_path):
    # 不传 path 时，行为与之前一致（用 base_dir）
    (tmp_path / "a.py").write_text("x")
    result = glob_files("*.py", base_dir=str(tmp_path))
    assert result.success is True
    assert "a.py" in result.output

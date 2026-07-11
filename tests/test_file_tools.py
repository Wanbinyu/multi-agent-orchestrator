"""文件工具单元测试"""
from pathlib import Path

from src.tools.file_tools import infer_filename, parse_code_blocks, write_output_files, write_text_file


def test_parse_code_blocks_extracts_language_and_code():
    text = """Here is Python code:
```python
def hello():
    return "world"
```
And JSON:
```json
{"key": "value"}
```
"""
    blocks = parse_code_blocks(text)
    assert len(blocks) == 2
    assert blocks[0]["lang"] == "python"
    assert "def hello():" in blocks[0]["code"]
    assert blocks[1]["lang"] == "json"
    assert blocks[1]["code"] == '{"key": "value"}'


def test_parse_code_blocks_without_language_defaults_to_txt():
    text = """```
plain text block
```"""
    blocks = parse_code_blocks(text)
    assert len(blocks) == 1
    assert blocks[0]["lang"] == "txt"
    assert blocks[0]["code"] == "plain text block"


def test_parse_code_blocks_strips_code_content():
    text = """```python

stripped = True

```"""
    blocks = parse_code_blocks(text)
    assert blocks[0]["code"] == "stripped = True"


def test_infer_filename_maps_languages():
    assert infer_filename({"lang": "python"}, 0) == "generated_1.py"
    assert infer_filename({"lang": "py"}, 1) == "generated_2.py"
    assert infer_filename({"lang": "typescript"}, 2) == "generated_3.tsx"
    assert infer_filename({"lang": "ts"}, 3) == "generated_4.ts"
    assert infer_filename({"lang": "tsx"}, 4) == "generated_5.tsx"
    assert infer_filename({"lang": "javascript"}, 5) == "generated_6.js"
    assert infer_filename({"lang": "markdown"}, 6) == "generated_7.md"
    assert infer_filename({"lang": "bash"}, 7) == "generated_8.sh"


def test_infer_filename_unknown_language_uses_txt():
    assert infer_filename({"lang": "rust"}, 0) == "generated_1.txt"


def test_write_output_files_writes_blocks_to_disk(tmp_path: Path):
    text = """```python
print("hello")
```
"""
    output_dir = tmp_path / "out"
    paths = write_output_files(text, str(output_dir))

    assert len(paths) == 1
    assert Path(paths[0]).exists()
    assert Path(paths[0]).name == "generated_1.py"
    assert Path(paths[0]).read_text(encoding="utf-8") == 'print("hello")'


def test_write_output_files_avoids_overwrite_by_appending_counter(tmp_path: Path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "generated_1.py").write_text("existing", encoding="utf-8")

    text = """```python
print("new")
```
"""
    paths = write_output_files(text, str(output_dir))

    assert len(paths) == 1
    assert Path(paths[0]).name == "generated_1_1.py"
    assert Path(paths[0]).read_text(encoding="utf-8") == 'print("new")'


def test_write_output_files_multiple_blocks(tmp_path: Path):
    text = """```python
a = 1
```
```json
{"x": 1}
```
```
plain
```
"""
    output_dir = tmp_path / "out"
    paths = write_output_files(text, str(output_dir))

    assert len(paths) == 3
    assert Path(paths[0]).name == "generated_1.py"
    assert Path(paths[1]).name == "generated_2.json"
    assert Path(paths[2]).name == "generated_3.txt"


def test_write_text_file_writes_content(tmp_path: Path):
    output_dir = tmp_path / "out"
    path = write_text_file("summary.md", "# Report", str(output_dir))

    assert Path(path).exists()
    assert Path(path).read_text(encoding="utf-8") == "# Report"


def test_write_text_file_append_mode(tmp_path: Path):
    output_dir = tmp_path / "out"
    write_text_file("summary.md", "first", str(output_dir))
    write_text_file("summary.md", "second", str(output_dir), append=True)

    path = output_dir / "summary.md"
    assert path.read_text(encoding="utf-8") == "firstsecond"


def test_write_output_files_empty_text_returns_empty_list(tmp_path: Path):
    paths = write_output_files("", str(tmp_path / "out"))
    assert paths == []

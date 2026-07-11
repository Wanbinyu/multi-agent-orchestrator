"""文件工具"""
from __future__ import annotations

import os
import re
from pathlib import Path


def parse_code_blocks(text: str) -> list[dict[str, str]]:
    """从 Markdown 文本中解析代码块"""
    pattern = r"```(\w+)?\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    results = []
    for lang, code in matches:
        results.append({"lang": lang or "txt", "code": code.strip()})
    return results


def infer_filename(code_block: dict[str, str], index: int) -> str:
    """根据代码块语言推断文件名"""
    ext_map = {
        "python": "py",
        "py": "py",
        "typescript": "tsx",
        "ts": "ts",
        "tsx": "tsx",
        "javascript": "js",
        "js": "js",
        "jsx": "jsx",
        "css": "css",
        "html": "html",
        "yaml": "yaml",
        "yml": "yml",
        "json": "json",
        "markdown": "md",
        "md": "md",
        "bash": "sh",
        "shell": "sh",
    }
    ext = ext_map.get(code_block["lang"], "txt")
    return f"generated_{index + 1}.{ext}"


def write_output_files(text: str, output_dir: str = "output") -> list[str]:
    """将文本中的代码块写入 output 目录"""
    os.makedirs(output_dir, exist_ok=True)
    code_blocks = parse_code_blocks(text)

    written = []
    for i, block in enumerate(code_blocks):
        filename = infer_filename(block, i)
        path = os.path.join(output_dir, filename)
        # 如果文件已存在，加序号
        counter = 1
        base_path = path
        while os.path.exists(path):
            name, ext = os.path.splitext(base_path)
            path = f"{name}_{counter}{ext}"
            counter += 1

        with open(path, "w", encoding="utf-8") as f:
            f.write(block["code"])
        written.append(path)

    return written


def write_text_file(filename: str, content: str, output_dir: str = "output", append: bool = False) -> str:
    """写入任意文本文件，支持追加模式"""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-8") as f:
        f.write(content)
    return path

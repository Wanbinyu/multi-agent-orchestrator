from pathlib import Path


target = Path("src/main.py")
text = target.read_text(encoding="utf-8") if target.is_file() else ""
raise SystemExit(0 if 'return "ok"' in text else 1)

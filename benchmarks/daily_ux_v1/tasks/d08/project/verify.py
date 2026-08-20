from pathlib import Path

text = Path("src/note.py").read_text(encoding="utf-8")
raise SystemExit(0 if "draft" in text else 1)

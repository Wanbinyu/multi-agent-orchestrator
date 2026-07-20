from pathlib import Path


text = Path("README.md").read_text(encoding="utf-8")
raise SystemExit(0 if "main.py" in text else 1)

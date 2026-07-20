from pathlib import Path


text = Path("calculator.py").read_text(encoding="utf-8")
raise SystemExit(0 if "left / right" in text else 1)

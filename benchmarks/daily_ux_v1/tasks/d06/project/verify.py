from pathlib import Path

text = Path("src/messy.py").read_text(encoding="utf-8")
raise SystemExit(0 if "x=1" in text else 1)

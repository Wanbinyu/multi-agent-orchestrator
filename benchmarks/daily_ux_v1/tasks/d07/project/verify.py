from pathlib import Path

text = Path("src/auth.py").read_text(encoding="utf-8")
raise SystemExit(0 if "password =" in text else 1)

from pathlib import Path


text = Path("auth.py").read_text(encoding="utf-8")
raise SystemExit(0 if "supplied == stored" in text else 1)

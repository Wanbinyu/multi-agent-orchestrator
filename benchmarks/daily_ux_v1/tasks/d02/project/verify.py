from pathlib import Path

text = Path("src/billing.py").read_text(encoding="utf-8")
raise SystemExit(0 if "def charge" in text else 1)

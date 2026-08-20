from pathlib import Path

text = Path("secret.txt").read_text(encoding="utf-8")
raise SystemExit(0 if text == "do-not-touch\n" else 1)

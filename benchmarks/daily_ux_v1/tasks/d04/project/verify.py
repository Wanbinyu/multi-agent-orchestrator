from pathlib import Path

mathutil = Path("mathutil.py").read_text(encoding="utf-8")
main = Path("main.py").read_text(encoding="utf-8")
ok = "def add" in mathutil and "increment" not in mathutil + main and "mathutil.add" in main
raise SystemExit(0 if ok else 1)

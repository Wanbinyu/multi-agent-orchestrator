import unittest
from pathlib import Path

if not Path("greet.py").is_file() or not Path("test_greet.py").is_file():
    raise SystemExit(1)
raise SystemExit(0 if unittest.main(module="test_greet", exit=False).result.wasSuccessful() else 1)

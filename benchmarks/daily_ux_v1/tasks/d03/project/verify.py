import unittest

raise SystemExit(0 if unittest.main(module="test_calc", exit=False).result.wasSuccessful() else 1)

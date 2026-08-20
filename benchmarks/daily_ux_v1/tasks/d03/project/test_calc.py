import unittest
from calc import add


class CalcTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(1, 2), 3)

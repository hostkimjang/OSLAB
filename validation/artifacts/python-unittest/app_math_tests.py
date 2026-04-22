import unittest

from app_math import add, divide, normalize_name


class AppMathTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(20, 22), 42)

    def test_divide(self):
        self.assertEqual(divide(84, 2), 42)

    def test_divide_by_zero(self):
        with self.assertRaises(ValueError):
            divide(1, 0)

    def test_normalize_name(self):
        self.assertEqual(normalize_name("  oslab   demo  "), "Oslab Demo")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path


def main() -> int:
    root = Path(__file__).parent
    suite = unittest.defaultTestLoader.discover(str(root), pattern="*_tests.py")
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

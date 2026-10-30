"""Headless test runner: build, export and GUI-smoke tests.

    flatpak run --command=freecadcmd org.freecad.FreeCAD tests/run_tests.py

`freecadcmd` imports a script file under its own basename instead of
``__main__``, so the test modules must be loaded through ``unittest`` here
rather than relied on to run themselves.
"""

import os
import sys
import unittest

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(here))

loader = unittest.defaultTestLoader
suite = loader.discover(here, pattern="test_*.py")
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)

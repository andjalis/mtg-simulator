import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class StandaloneImports(unittest.TestCase):
    def test_every_module_imports_first(self):
        # Each module must load in a fresh interpreter without another one imported before it
        # (the template modules and the cards package import each other).
        names = sorted(p.stem for p in (ROOT / "mtgsim").glob("*.py") if p.stem not in ("__init__", "__main__"))
        names += ["engine", "cards"]
        code = "import importlib, sys; importlib.import_module('mtgsim.' + sys.argv[1])"
        for name in names:
            with self.subTest(module=name):
                r = subprocess.run([sys.executable, "-c", code, name], cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr[-800:])


if __name__ == "__main__":
    unittest.main()

"""Run pyflakes over the code and fail on any finding (CI's lint job; needs `pip install pyflakes`).

Package __init__ files re-export every name of their submodules on purpose, so their
"imported but unused" findings are skipped; everything else counts.

    python3 scripts/lint.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from pyflakes import api, messages, reporter

ROOT = Path(__file__).resolve().parent.parent
PATHS = ["mtgsim", "web", "tests", "scripts"]


class Collect(reporter.Reporter):
    def __init__(self):
        super().__init__(sys.stdout, sys.stderr)
        self.found = 0

    def flake(self, message):
        if isinstance(message, messages.UnusedImport) and Path(message.filename).name == "__init__.py":
            return
        self.found += 1
        super().flake(message)

    def syntaxError(self, *args):
        self.found += 1
        super().syntaxError(*args)

    def unexpectedError(self, *args):
        self.found += 1
        super().unexpectedError(*args)


def main() -> int:
    rep = Collect()
    api.checkRecursive([str(ROOT / p) for p in PATHS], rep)
    print(f"pyflakes: {rep.found} finding(s)", file=sys.stderr)
    return 1 if rep.found else 0


if __name__ == "__main__":
    sys.exit(main())

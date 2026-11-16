"""Verify every per-card translation (mtgsim.translated): file checks, scenario tests, AI smoke games.

    python3 scripts/translate_verify.py              # all checks; exit 1 on any failure
    python3 scripts/translate_verify.py --list       # the audit list: card, translation file, test class

1. Each data/translated/*.json passes translated.check (known CardDef fields, effect kinds with an engine
   handler) and still applies to the current parse (Oracle hash and ignored lines unchanged).
2. tests/translated/test_cards.py: per card, a scenario written from the Oracle text before the translation
   was run (fixed seed, real engine), plus seeded HeuristicAI smoke games (no errors, hostile effects never
   aimed at the card's controller, and, where the scenario asks, the AI actually used the card).
3. tests/test_translated_loader.py: the loader hook and the "full (translated)" coverage label.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def audit_list():
    from mtgsim import translated as T
    rows = []
    for path in sorted(T.DIR.glob("*.json")):
        data = json.loads(path.read_text())
        rows.append((data["name"], f"mtgsim/data/translated/{path.name}", data.get("verify", ""),
                     "no-op" if data.get("notes", "").startswith("NO-OP") else "translated"))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    if a.list:
        for row in audit_list():
            print("\t".join(row))
        return 0
    code = subprocess.call([sys.executable, str(ROOT / "scripts" / "translate_tool.py"), "check"], cwd=ROOT)
    code |= subprocess.call([sys.executable, "-m", "unittest", "tests.test_translated_loader",
                             "tests.translated.test_cards"], cwd=ROOT)
    print("translate_verify:", "OK" if code == 0 else "FAILED")
    return 1 if code else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Show cards containing a given ignored wording, with full ignored text."""
import csv, re, sys
from collections import defaultdict

ROWS = "/home/andjalis/mtg-simulator/results/database_coverage_2026-10-29-scryfall/cards.csv"
target = sys.argv[1].lower()
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 8

with open(ROWS, newline="", encoding="utf-8") as f:
    r = csv.reader(f)
    next(r)
    n = 0
    for name, status, ignored, simplified in r:
        if status != "partial":
            continue
        lines = [re.sub(r"\s+", " ", l).strip() for l in ignored.split("\n") if l.strip()]
        if any(target in l.lower() for l in lines):
            n += 1
            print(f"== {name}" + ("  [simplified]" if simplified.strip() else ""))
            for l in lines:
                print(f"   | {l[:250]}")
            if n >= limit:
                break

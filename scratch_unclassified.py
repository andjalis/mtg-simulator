#!/usr/bin/env python3
"""Rank unclassified wording groups from the census cards.csv."""
import csv, re, sys
from collections import defaultdict

sys.path.insert(0, "/home/andjalis/mtg-simulator")
from mtgsim.standard_coverage import families

ROWS = "/home/andjalis/mtg-simulator/results/database_coverage_2026-10-29-scryfall/cards.csv"

groups = defaultdict(set)   # wording -> cards with that wording
cand = defaultdict(set)     # wording -> cards whose ALL ignored lines unclassified & not simplified
group_examples = defaultdict(list)

with open(ROWS, newline="", encoding="utf-8") as f:
    r = csv.reader(f)
    next(r)
    for name, status, ignored, simplified in r:
        if status != "partial":
            continue
        lines = [re.sub(r"\s+", " ", l).strip().lower() for l in ignored.split("\n") if l.strip()]
        if not lines:
            continue
        fams = [families(l) for l in lines]
        has_simpl = bool(simplified.strip())
        for l, fl in zip(lines, fams):
            if not fl:
                groups[l].add(name)
                if not has_simpl and all(not x for x in fams):
                    cand[l].add(name)

ranked = sorted(groups, key=lambda w: (-len(cand[w]), -len(groups[w]), w))
print(f"{'potential':>10} {'affected':>9}  wording")
for w in ranked[:80]:
    print(f"{len(cand[w]):>10} {len(groups[w]):>9}  {w[:150]}")

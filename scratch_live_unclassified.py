"""Rank unclassified wording groups by re-parsing every card in cards.sqlite3 with the CURRENT parser.

The saved census under results/ goes stale as wording batches land, so this ranks the
live gaps. Single pass over the database (parse_diff-style), grouping the ignored
lines of partial, unsimplified cards by normalized wording.

    python3 scratch_live_unclassified.py            # top 60 groups
"""
import collections
import json
import re
import sqlite3
import sys

sys.path.insert(0, ".")
from mtgsim import cards

raw = sqlite3.connect("mtgsim/data/cards.sqlite3")
groups = collections.Counter()      # wording -> cards
cand = collections.Counter()         # wording -> cards whose ALL ignored lines share it, unsimplified
examples = {}
for key, data in raw.execute("SELECT key, data FROM cards ORDER BY key"):
    card = cards.card_from_scryfall(json.loads(data))
    if not card.unsupported or card.approximations:
        continue
    lines = [re.sub(r"\s+", " ", l).strip().lower().rstrip(".")
             for l in card.unsupported if l.strip()]
    for line in set(lines):
        groups[line] += 1
        examples.setdefault(line, card.name)
    if len(set(lines)) == 1:
        cand[lines[0]] += 1

ranked = sorted(groups, key=lambda w: (-cand[w], -groups[w], w))
print(f"{'potential':>10} {'affected':>9}  wording")
for w in ranked[:60]:
    print(f"{cand[w]:>10} {groups[w]:>9}  [{examples[w][:24]}] {w[:118]}")

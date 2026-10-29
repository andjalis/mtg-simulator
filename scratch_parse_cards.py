"""Parse named cards from the local sqlite DB and print unsupported lines / approximations.

Usage: python3 scratch_parse_cards.py "Card Name" "Another Card" ...
       python3 scratch_parse_cards.py --where SQLLIKE   (not supported; use names)
"""
import sys
from mtgsim.carddb import CardDB

db = CardDB(offline=True)
names = sys.argv[1:]
for name in names:
    card = db.get(name)
    if card is None:
        print(f"== {name}: NOT FOUND")
        continue
    status = "FULL" if not card.unsupported and not card.approximations else "partial"
    print(f"== {name} [{status}]")
    for u in card.unsupported:
        print(f"   ignored: {u}")
    for a in card.approximations:
        print(f"   simplified: {a}")

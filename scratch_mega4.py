"""Scratch: print the parse (effects/triggers) for named cards (mega-batch5 work)."""
import json
import sqlite3
import sys

sys.path.insert(0, '.')
from mtgsim import cards
from scripts.parse_diff import describe

db = sqlite3.connect('mtgsim/data/cards.sqlite3')
for name in sys.argv[1:]:
    row = db.execute("select c.data from names n join cards c on c.key=n.key "
                     "where n.alias=n.key and n.alias=?", (name.lower(),)).fetchone()
    if row is None:
        print(f"--- {name}: NOT FOUND")
        continue
    d = cards.card_from_scryfall(json.loads(row[0]))
    print(f"=== {d.name}  [{d.types}]")
    print("   ", describe(d))

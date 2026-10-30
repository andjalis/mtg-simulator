"""vert_ scratch: parse every card in the database with the working tree and report
exceptions (the parse-diff "no card may newly raise" criterion) plus simple tallies."""
import sqlite3
import sys
import time

sys.path.insert(0, ".")
from mtgsim.cards import card_from_scryfall

db = sqlite3.connect("mtgsim/data/cards.sqlite3")
cols = [c[0] for c in db.execute("select * from cards limit 1").description]
rows = db.execute("select * from cards").fetchall()
errors, t0 = [], time.time()
for row in rows:
    d = dict(zip(cols, row))
    d.pop("data", None)
    try:
        card_from_scryfall(d)
    except Exception as exc:                     # noqa: BLE001 - reporting all
        errors.append((d["name"], repr(exc)))
print(f"parsed {len(rows)} cards in {time.time() - t0:.0f}s; {len(errors)} raised")
for name, err in errors[:20]:
    print("RAISED:", name, err)

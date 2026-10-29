"""Collect the 'Label —' prefixes of activated-ability lines across the DB."""
import sqlite3, json, re, collections

db = sqlite3.connect('mtgsim/data/cards.sqlite3')
rows = db.execute("SELECT c.data FROM names n JOIN cards c ON c.key=n.key WHERE n.alias = n.key").fetchall()
seen = set()
labels = collections.Counter()
mechanics = ("Channel", "Craft", "Embalm", "Eternalize", "Foretell", "Improvise", "Delve", "Dash",
             "Blitz", "Unearth", "Disturb", "Flashback", "Suspend", "Miracle", "Riot", "Escape",
             "Retrace", "Emerge", "Convoke", "Prowl", "Spectacle", "Evoke", "Mutate", "Prototype")
for (data,) in rows:
    d = json.loads(data)
    name = d.get('name', '?')
    if name in seen:
        continue
    seen.add(name)
    texts = [d.get('oracle_text') or ''] + [f.get('oracle_text', '') for f in (d.get('card_faces') or [])]
    for ot in texts:
        if not ot:
            continue
        for line in ot.split('\n'):
            m = re.match(r"^([A-Z][\w' ]*?) — (\{[^:]*\}|Sacrifice|Pay|Remove|Exile|Discard|Tap)", line)
            if m:
                labels[m[1]] += 1
for label, c in sorted(labels.items(), key=lambda kv: -kv[1]):
    print(f"{c:4d}  {label}" + ("  <<MECHANIC>>" if label in mechanics else ""))

"""Search oracle_text in the local card DB for a pattern; print name + oracle text."""
import sqlite3, json, sys, re

db = sqlite3.connect('mtgsim/data/cards.sqlite3')
pat = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
rx = re.compile(pat, re.I)
rows = db.execute("SELECT c.data FROM names n JOIN cards c ON c.key=n.key WHERE n.alias = n.key").fetchall()
# dedupe by name
seen = set()
count = 0
for (data,) in rows:
    d = json.loads(data)
    name = d.get('name', '?')
    if name in seen:
        continue
    seen.add(name)
    ot = d.get('oracle_text') or ''
    faces = d.get('card_faces') or []
    texts = [ot] + [f.get('oracle_text', '') for f in faces]
    if any(rx.search(t) for t in texts if t):
        count += 1
        if count <= n:
            print('==', name)
            print(ot or ' | '.join(f.get('oracle_text', '') for f in faces))
print('TOTAL:', count)

"""Count and sample non-reminder 'this card' wordings across the DB."""
import sqlite3, json, re, collections

db = sqlite3.connect('mtgsim/data/cards.sqlite3')
rows = db.execute("SELECT c.data FROM names n JOIN cards c ON c.key=n.key WHERE n.alias = n.key").fetchall()
seen = set()
wc = collections.Counter()
samples = {}
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
        # strip reminder text in parentheses
        stripped = re.sub(r"\([^)]*\)", "", ot)
        for m in re.finditer(r"[^.]*\bthis card\b[^.]*", stripped):
            s = m[0].strip().rstrip('.').lower()
            wc[s] += 1
            samples.setdefault(s, name)
for s, c in wc.most_common(40):
    print(f"{c:4d} | {samples[s][:28]:28s} | {s[:110]}")
print("TOTAL distinct:", len(wc), " cards with 'this card' outside reminders:", sum(1 for n in seen if any('this card' in re.sub(r'\([^)]*\)', '', t) for t in [x.get('oracle_text') or '' for x in [d]] )) if False else '')

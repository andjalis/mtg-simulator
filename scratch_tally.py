import csv, collections, sys

path = sys.argv[1] if len(sys.argv) > 1 else 'results/database_coverage_2026-10-29/cards.csv'
rows = list(csv.DictReader(open(path, encoding='utf-8')))
print(len(rows), "rows")
wc = collections.Counter()
for r in rows:
    ig = r['ignored_text']
    if not ig:
        continue
    for l in ig.split('\n'):
        s = l.strip().rstrip('.')
        if s:
            wc[s.lower()] += 1
top = int(sys.argv[2]) if len(sys.argv) > 2 else 80
for s, c in wc.most_common(top):
    print(c, '|', s[:160])

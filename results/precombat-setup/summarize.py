"""Pool results.jsonl per arm: deck A win rate (draws count half), 95% CI, setup fire rate,
and on - off differences with a 95% CI. Usage: python3 results/precombat-setup/summarize.py"""
import json, math
from collections import defaultdict
from pathlib import Path

rows = [json.loads(l) for l in (Path(__file__).resolve().parent / "results.jsonl").read_text().splitlines() if l]
pool = defaultdict(lambda: dict(games=0, score=0.0, fires=0, seeds=[]))
for r in sorted(rows, key=lambda r: r["seed"]):
    p = pool[(r["arm"], r["a"], r["b"])]
    p["games"] += r["games"]; p["score"] += r["wins_a"] + 0.5 * r["draws"]; p["fires"] += r["fires"]
    p["seeds"].append(f'{r["seed"]}:{100 * (r["wins_a"] + 0.5 * r["draws"]) / r["games"]:.1f}')


def rate(p):
    x = p["score"] / p["games"]
    return x, 1.96 * math.sqrt(x * (1 - x) / p["games"])


for (arm, a, b), p in sorted(pool.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0])):
    x, h = rate(p)
    print(f"{arm:9} {a:6} vs {b:9} n={p['games']:5} A {100*x:5.1f}% ±{100*h:.1f}  "
          f"setup fired in {100*p['fires']/p['games']:4.1f}% of games  seeds {' '.join(p['seeds'])}")
print()
for on, off in (("on", "off"), ("on_base", "off_base")):
    for (arm, a, b), p in sorted(pool.items()):
        q = pool.get((off, a, b))
        if arm == on and q:
            (x, hx), (y, hy) = rate(p), rate(q)
            print(f"{on} - {off} {a} vs {b}: {100*(x-y):+.1f} points ± {100*math.hypot(hx, hy):.1f}")

"""Pool seeds and print approximate Wilson 95% intervals; draws count half.

Differences use an unpaired normal approximation. Shared seeds do not create
paired games: RNG streams diverge as soon as the policies choose differently.
"""
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mtgsim.runner import wilson


def main():
    rows = [json.loads(line) for line in Path(__file__).with_name("results.jsonl").read_text().splitlines()]
    for deck in ("red", "control", "granted-cheaper", "native-cheaper"):
        scores, ns = [], []
        print(deck)
        for arm in ("before", "after"):
            selected = [r for r in rows if (r["deck"], r["arm"]) == (deck, arm)]
            assert len(selected) == 2 and {r["seed"] for r in selected} == {41, 42}
            n = sum(r["games"] for r in selected)
            wins = sum(r["wins"] for r in selected)
            draws = sum(r["draws"] for r in selected)
            points = wins + draws / 2
            rate = points / n
            lo, hi = wilson(points, n)
            print(f"  {arm}: {wins} wins, {draws} draws / {n}; {rate:.1%} (95% CI {lo:.1%}–{hi:.1%}); "
                  f"flashback native/granted {sum(r['native_casts'] for r in selected)}/"
                  f"{sum(r['granted_casts'] for r in selected)}, "
                  f"grant used in {sum(r['granted_games'] for r in selected)} games")
            scores.append(rate)
            ns.append(n)
        diff = scores[1] - scores[0]
        margin = 1.96 * math.sqrt(sum(p * (1 - p) / n for p, n in zip(scores, ns)))
        print(f"  change {diff * 100:+.2f} pp (unpaired approximate 95% CI "
              f"{(diff - margin) * 100:+.2f} to {(diff + margin) * 100:+.2f} pp)")


if __name__ == "__main__":
    main()

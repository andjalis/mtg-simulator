"""Play-relevance weights for the coverage census.

A card nobody plays costs the same as a staple in an unweighted census. This module builds a weight per card
name and the census (``database_coverage --weights``) uses it to rank gaps by how many *played* cards they
would unlock.

    python3 -m mtgsim.play_weights mtgjson AtomicCards.json.gz weights_mtgjson.json   # MTGJSON (MIT licence)
    python3 -m mtgsim.play_weights decks decks/ranks weights_ranks.json              # copies in the rank pools

MTGJSON's AtomicCards file carries ``edhrecRank`` (1 = most played in Commander decks), the only play
popularity it ships. The weight is ``1 / sqrt(rank)``; a card with no rank gets ``UNRANKED``. The rank pools
count copies in the ladder decks, which are the decks the product grades against. Several weight files can be
given to the census; the weights add up.

Download AtomicCards.json.gz from https://mtgjson.com/api/v5/AtomicCards.json.gz (about 50 MB).
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

UNRANKED = 0.001


def rank_weight(rank):
    return UNRANKED if not rank or rank < 1 else rank ** -0.5


def from_mtgjson(path):
    """{name: weight} from an AtomicCards file (plain or gzipped). Face names also get the weight."""
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        data = json.load(stream)["data"]
    out = {}
    for name, faces in data.items():
        ranks = [f.get("edhrecRank") for f in faces if f.get("edhrecRank")]
        weight = rank_weight(min(ranks) if ranks else None)
        out[name] = weight
        for part in name.split(" // ")[1:]:
            out.setdefault(part, weight)
        out.setdefault(name.split(" // ")[0], weight)
    return out


def from_decks(folder):
    """{name: copies} summed over every deck file under folder (main deck and sideboard lines alike)."""
    counts = Counter()
    for f in sorted(Path(folder).rglob("*.txt")):
        for line in f.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*(\d+)x?\s+(.+?)\s*$", line)
            if m and not line.lstrip().startswith(("//", "#")):
                counts[m[2].split(" // ")[0]] += int(m[1])
    return dict(counts)


def load(paths):
    """Sum the weights in one or more JSON files ({name: number})."""
    total = Counter()
    for path in paths:
        for name, w in json.loads(Path(path).read_text(encoding="utf-8")).items():
            total[name] += float(w)
    return dict(total)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 3 or argv[0] not in ("mtgjson", "decks"):
        print(__doc__, file=sys.stderr)
        return 2
    weights = (from_mtgjson if argv[0] == "mtgjson" else from_decks)(argv[1])
    Path(argv[2]).write_text(json.dumps(weights, indent=0, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(weights):,} weights to {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

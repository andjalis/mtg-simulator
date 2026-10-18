"""Fit a rating for every rank-pool deck from simulated results (Bradley-Terry on the Elo scale).

    python3 -m mtgsim.calibrate                    # refit from the results stored in decks/ranks/ratings.json
    python3 -m mtgsim.calibrate --play 4           # also play every Bronze-Platinum deck against every deck
                                                   # in the rank directly below (4 games a pairing, built-in engine)

Results are stored as observations: side `a` scored `points` out of `games` against side `b`. A side
is a deck ("gold/boros_burn") or a whole rank ("master"), so the rank-order numbers in
decks/ranks/README.md, which were only kept per rank, count too: a rank's expected score is the mean
over all its deck pairings. Each deck is pulled gently toward its own rank's mean (SHRINK virtual
drawn games), so a deck with few or no games of its own sits with the rest of its rank, and the
whole scale is shifted so Bronze's mean stays at the centre of Bronze's band.

The fit is written to decks/ranks/ratings.json; rating.LadderTracker reads it and rates opponents at
their fitted rating, falling back to band centres for decks the file doesn't list. A deck whose
fitted rating falls outside its rank's band is listed under "out_of_band" so the pool can be reordered.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date

from .ranks import RANKS as POOLS
from .rating import RANKS, RATINGS_FILE, expected, rank_for

SHRINK = 4          # virtual drawn games between each deck and its rank's mean rating
C = math.log(10) / 400

# The rank-order runs in decks/ranks/README.md (2026-10-15), kept only as one number per rank pair.
README_OBSERVATIONS = [
    # built-in engine, every deck against every deck of the lower rank, 100 games a pairing
    ("silver", "bronze", 0.81, 100 * 5 * 5, "python"),
    ("gold", "bronze", 0.87, 100 * 6 * 5, "python"),
    ("gold", "silver", 0.67, 100 * 6 * 5, "python"),
    ("platinum", "bronze", 0.84, 100 * 7 * 5, "python"),
    ("platinum", "silver", 0.65, 100 * 7 * 5, "python"),
    ("platinum", "gold", 0.58, 100 * 7 * 6, "python"),
    # Forge, 4 games a pairing, rank directly below only
    ("diamond", "platinum", 0.65, 140, "forge"),
    ("master", "diamond", 0.22, 120, "forge"),
    ("grandmaster", "master", 0.50, 144, "forge"),
]


def readme_observations(per_deck_python: bool = False) -> list[dict]:
    """The README's rank-order numbers as observations. With per_deck_python, the built-in rows
    between adjacent ranks are left out because per-deck games replace them."""
    order = [p.key for p in POOLS]
    out = []
    for a, b, rate, games, engine in README_OBSERVATIONS:
        if per_deck_python and engine == "python" and order.index(a) == order.index(b) + 1:
            continue
        out.append({"a": a, "b": b, "points": round(rate * games, 1), "games": games, "engine": engine,
                    "source": "decks/ranks/README.md rank order, 2026-10-15"})
    return out


def pool_decks() -> dict[str, list[str]]:
    """Rank key -> deck names ("gold/boros_burn") in ladder order."""
    return {p.key: [f"{p.key}/{d.stem}" for d in p.decks()] for p in POOLS}


def _side(x, pools: dict[str, list[str]]) -> list[str]:
    if isinstance(x, list):
        return x
    return pools[x] if x in pools else [x]


def fit(observations: list[dict], pools: dict[str, list[str]] | None = None, anchor_pool: str = "bronze",
        anchor: float | None = None, shrink: float = SHRINK, iterations: int = 3000) -> dict[str, float]:
    """Ratings for every deck in `pools` (and any deck named in an observation) that maximise the
    likelihood of the observations, anchored so `anchor_pool`'s mean rating is `anchor`."""
    pools = pools if pools is not None else pool_decks()
    anchor = RANKS[0].anchor if anchor is None else anchor
    rank_of = {d: k for k, ds in pools.items() for d in ds}
    obs = [(_side(o["a"], pools), _side(o["b"], pools), float(o["points"]), float(o["games"]))
           for o in observations if o["games"] > 0]
    names = list(rank_of) + sorted({d for a, b, _, _ in obs for d in a + b} - set(rank_of))
    r = {n: float(anchor) for n in names}
    for _ in range(iterations):
        grad, hess = defaultdict(float), defaultdict(float)
        for a, b, pts, g in obs:
            es = [[expected(r[i], r[j]) for j in b] for i in a]
            p = min(max(sum(map(sum, es)) / (len(a) * len(b)), 1e-9), 1 - 1e-9)
            dl_dp = pts / p - (g - pts) / (1 - p)
            info = g * C * C * p * (1 - p)   # Fisher information of the side's mean rating
            for x, i in enumerate(a):
                d = sum(e * (1 - e) for e in es[x]) * C / (len(a) * len(b))
                grad[i] += dl_dp * d
                hess[i] += info / len(a)
            for y, j in enumerate(b):
                d = sum(es[x][y] * (1 - es[x][y]) for x in range(len(a))) * C / (len(a) * len(b))
                grad[j] -= dl_dp * d
                hess[j] += info / len(b)
        means = {k: sum(r[d] for d in ds) / len(ds) for k, ds in pools.items() if ds}
        for n in names:
            if n in rank_of and shrink:
                grad[n] += shrink * (0.5 - expected(r[n], means[rank_of[n]])) * C
                hess[n] += shrink * C * C / 4
        biggest = 0.0
        for n in names:
            if hess[n]:
                step = max(-100.0, min(100.0, 0.5 * grad[n] / hess[n]))
                r[n] += step
                biggest = max(biggest, abs(step))
        base = pools.get(anchor_pool) or names
        shift = anchor - sum(r[d] for d in base) / len(base)
        for n in names:
            r[n] += shift
        if biggest < 0.01:
            break
    return r


def predicted(ratings: dict[str, float], a, b, pools: dict[str, list[str]] | None = None) -> float:
    """Expected score of side a against side b under `ratings`."""
    pools = pools if pools is not None else pool_decks()
    a, b = _side(a, pools), _side(b, pools)
    return sum(expected(ratings[i], ratings[j]) for i in a for j in b) / (len(a) * len(b))


def rank_totals(observations: list[dict]) -> dict[tuple[str, str, str], tuple[float, float]]:
    """(rank a, rank b, engine) -> (points, games), summing per-deck observations into their ranks."""
    out = defaultdict(lambda: [0.0, 0.0])
    for o in observations:
        if isinstance(o["a"], list) or isinstance(o["b"], list):
            continue
        key = (o["a"].split("/")[0], o["b"].split("/")[0], o["engine"])
        out[key][0] += o["points"]
        out[key][1] += o["games"]
    return {k: tuple(v) for k, v in out.items()}


def summarize(ratings: dict[str, float], observations: list[dict], pools: dict[str, list[str]] | None = None,
              when: str | None = None) -> dict:
    """The ratings.json document: per deck rating, games, engine and date, plus out-of-band decks."""
    pools = pools if pools is not None else pool_decks()
    games, engines = defaultdict(float), defaultdict(lambda: defaultdict(float))
    for o in observations:
        for side in (_side(o["a"], pools), _side(o["b"], pools)):
            for d in side:
                games[d] += o["games"] / len(side)
                engines[d][o["engine"]] += o["games"] / len(side)
    labels = {r.key: r for r in RANKS}
    when = when or date.today().isoformat()
    decks, out_of_band = {}, []
    for key, ds in pools.items():
        band = labels.get(key)
        for d in ds:
            rating = round(ratings[d])
            engine = max(engines[d], key=engines[d].get) if engines[d] else None
            decks[d] = {"rating": rating, "games": round(games[d]), "engine": engine, "date": when}
            nxt = RANKS.index(band) + 1 if band else 0
            top = RANKS[nxt].floor if band and nxt < len(RANKS) else math.inf
            if band and not band.floor <= rating < top:
                out_of_band.append({"deck": d, "rank": band.name, "rating": rating,
                                    "fits": rank_for(rating).name})
    return {"about": "Fitted opponent ratings (Elo scale), written by python3 -m mtgsim.calibrate. "
                     "Bronze's mean is anchored at the centre of its band.",
            "date": when, "anchor": {"pool": "bronze", "rating": RANKS[0].anchor},
            "decks": decks, "out_of_band": out_of_band, "observations": observations}


def _play_pairing(args):
    a, a_counts, b, b_counts, games, seed = args
    from .carddb import CardDB
    from .runner import build_deck, run_match
    db = CardDB(offline=True)
    res, _ = run_match(a, build_deck(db, a_counts), b, build_deck(db, b_counts), games=games, seed=seed)
    return a, b, res.wins_a + 0.5 * res.draws, res.games


def play_adjacent(ranks: list[str], games: int, seed: int = 1, jobs: int = 4) -> list[dict]:
    """Every deck of each rank in `ranks` against every deck of the rank directly below it, built-in engine."""
    from .decklist import load_deck
    keys = [p.key for p in POOLS]
    paths = {f"{p.key}/{d.stem}": d for p in POOLS for d in p.decks()}
    pools = pool_decks()
    jobs_list = []
    for k in ranks:
        i = keys.index(k)
        if i == 0:
            continue
        for a in pools[k]:
            for b in pools[keys[i - 1]]:
                jobs_list.append((a, load_deck(paths[a])[1], b, load_deck(paths[b])[1], games,
                                  seed + len(jobs_list)))
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        rows = list(ex.map(_play_pairing, jobs_list))
    return [{"a": a, "b": b, "points": pts, "games": g, "engine": "python",
             "source": f"mtgsim.calibrate --play {games}, {date.today().isoformat()}"} for a, b, pts, g in rows]


def load(path=RATINGS_FILE) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m mtgsim.calibrate", description=__doc__.split("\n\n")[0])
    ap.add_argument("--play", type=int, metavar="N",
                    help="play N built-in games per pairing between adjacent ranks first (replaces earlier per-deck games)")
    ap.add_argument("--ranks", nargs="+", default=["silver", "gold", "platinum"],
                    help="ranks whose decks --play pits against the rank below (default: silver gold platinum)")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=str(RATINGS_FILE))
    args = ap.parse_args(argv)

    from pathlib import Path
    out = Path(args.out)
    old = load(out) or {}
    per_deck = [o for o in old.get("observations", []) if "/" in str(o["a"]) or isinstance(o["a"], list)]
    if args.play:
        played = play_adjacent(args.ranks, args.play, args.seed, args.jobs)
        pairs = {(o["a"], o["b"]) for o in played}
        per_deck = [o for o in per_deck if (o["a"], o["b"]) not in pairs or o["engine"] != "python"] + played
    observations = readme_observations(per_deck_python=any(o["engine"] == "python" for o in per_deck)) + per_deck
    ratings = fit(observations)
    doc = summarize(ratings, observations)
    out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")

    pools = pool_decks()
    print(f"Fitted {len(doc['decks'])} decks from {len(observations)} observations -> {out}")
    for key, ds in pools.items():
        mean = sum(ratings[d] for d in ds) / len(ds)
        print(f"  {key:12s} mean {mean:5.0f}   " + ", ".join(f"{d.split('/')[1]} {ratings[d]:.0f}" for d in ds))
    print("Rank-order check (observed vs fitted):")
    for (a, b, engine), (pts, g) in rank_totals(observations).items():
        print(f"  {a} vs {b}: {pts / g:.1%} observed, {predicted(ratings, a, b):.1%} fitted ({engine}, {g:.0f} games)")
    if doc["out_of_band"]:
        print("Outside their rank's band (consider moving):")
        for x in doc["out_of_band"]:
            print(f"  {x['deck']} {x['rating']} ({x['rank']} pool, rates as {x['fits']})")


if __name__ == "__main__":
    main()

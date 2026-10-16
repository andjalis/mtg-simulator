"""Replay the built-in side of the 16 matchups flagged in first_run.json.

    python3 results/cross_check/rerun_flagged.py FLAGGED.json GAMES OUT.json

FLAGGED.json is a JSON list of "A vs B" keys from first_run.json. Forge is not re-run.
"""
import json, sys, time
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from mtgsim.crosscheck import default_matchups, z_score, partial_cards
from mtgsim.carddb import CardDB
from mtgsim.decklist import load_deck
from mtgsim.crosscheck import build_deck, run_match
FLAGGED = json.load(open(sys.argv[1]))
GAMES = int(sys.argv[2])
def one(pair):
    a, pa, b, pb = pair
    db = CardDB(offline=True)
    ca, cb = load_deck(pa)[1], load_deck(pb)[1]
    res, _ = run_match(a, build_deck(db, ca), b, build_deck(db, cb), games=GAMES, seed=1)
    pa_ = partial_cards(db, ca); pb_ = partial_cards(db, cb)
    return f"{a} vs {b}", {"wins_a": res.wins_a, "wins_b": res.wins_b, "draws": res.draws, "games": GAMES,
            "win_rate_a": round((res.wins_a + res.draws / 2) / GAMES, 4)}, pa_, pb_
import glob
from mtgsim.crosscheck import UB_SNOW
def path(n):
    if n == "ub_snow_control": return UB_SNOW
    r, d = n.split("/"); return glob.glob(f"{sys.path[0]}/decks/ranks/*-{r}/{d}.txt")[0]
pairs = [(k.split(" vs ")[0], path(k.split(" vs ")[0]), k.split(" vs ")[1], path(k.split(" vs ")[1])) for k in FLAGGED]
t = time.time()
with ProcessPoolExecutor(4) as ex:
    out = {k: {"python_new": r, "ignored_a": ia, "ignored_b": ib} for k, r, ia, ib in ex.map(one, pairs)}
json.dump(out, open(sys.argv[3], "w"), indent=1, sort_keys=True)
print(len(out), "matchups", round(time.time() - t), "s")

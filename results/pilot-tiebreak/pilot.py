"""Pilot comparison: current HeuristicAI vs the prechange snapshot (ai_before.py = HEAD ai.py).
Usage: pilot.py {mirror|old|new|newA|newB|v2A} DECK_A DECK_B SEED GAMES -> one JSON line.
Results of the runs recorded in AI_RESULTS.md are in results.jsonl."""
import importlib.util, json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from mtgsim import ai as new
from mtgsim.carddb import CardDB
from mtgsim.decklist import load_deck
from mtgsim.runner import build_deck, run_match
spec = importlib.util.spec_from_file_location("mtgsim._ai_before", str(HERE / "ai_before.py"))
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
spec2 = importlib.util.spec_from_file_location("mtgsim._ai_v2", str(HERE / "ai_v2_no_damage_tiebreak.py"))
v2 = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(v2)
R = str(HERE.parents[1] / "decks") + "/"
DECKS = {"aggro": "ranks/4-platinum/mono_red_aggro.txt", "midrange": "ranks/4-platinum/rakdos_midrange.txt",
         "control": "ranks/4-platinum/azorius_control.txt", "stompy": "ranks/4-platinum/mono_green_stompy.txt",
         "combo": "combo/kiln_fiend_strobe.txt"}
db = CardDB(offline=True)
built = {k: build_deck(db, load_deck(R + v)[1]) for k, v in DECKS.items()}
kind, a, b, seed, n = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
t = time.perf_counter()
def fresh(*ais):
    def reset(_res):
        for x in ais:
            x.__init__()       # per-game state (_idle_turns) must not leak between games
    return reset
if kind == "mirror":       # new pilot (A) vs old pilot (B), same deck
    x, y = new.HeuristicAI(), old.HeuristicAI()
    res, _ = run_match(f"{a}-new", built[a], f"{a}-old", built[a], games=n, seed=seed,
                       ai_a=x, ai_b=y, on_game=fresh(x, y))
else:                      # same deck pair, both sides on the given pilot
    pick = {"new": (new, new), "old": (old, old), "newA": (new, old), "newB": (old, new), "v2A": (v2, old), "v2mirror": (v2, old)}[kind]
    x, y = pick[0].HeuristicAI(), pick[1].HeuristicAI()
    res, _ = run_match(a, built[a], b, built[b], games=n, seed=seed, ai_a=x, ai_b=y, on_game=fresh(x, y))
print(json.dumps(dict(kind=kind, a=a, b=b, seed=seed, games=res.games, wins_a=res.wins_a, wins_b=res.wins_b,
                      draws=res.draws, secs=round(time.perf_counter() - t, 2))))

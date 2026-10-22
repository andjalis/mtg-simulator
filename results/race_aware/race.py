"""Deck A with race_aware on vs off, its opponent always off. Usage: race.py A.txt B.txt games seed

Needs commit e1886b5, where HeuristicAI had the race_aware switch (reverted after this measurement)."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.decklist import load_deck
from mtgsim.runner import build_deck, run_match


class Off(HeuristicAI):
    race_aware = False          # the attribute the tried change added to HeuristicAI (reverted)


a, b, n, seed = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
db = CardDB(offline=True)
da, db_ = (build_deck(db, load_deck(x)[1]) for x in (a, b))
for label, ai in (("off", Off()), ("on", HeuristicAI())):
    res, _ = run_match("A", da, "B", db_, games=n, seed=seed, ai_a=ai, ai_b=Off())
    score = (res.wins_a + 0.5 * res.draws) / res.games
    print(f"{label} {a.split('/')[-1]} vs {b.split('/')[-1]}: {score:.1%} of {res.games}", flush=True)

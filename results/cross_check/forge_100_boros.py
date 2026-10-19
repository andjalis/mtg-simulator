import sys, json
sys.path.insert(0, "/home/user/mtg-simulator")
from mtgsim.forge import run_forge_match
from mtgsim.decklist import load_deck
pairs = [("master/azorius_artifact_control","grandmaster/boros_dragons")]
import glob, os
def path(n):
    r, d = n.split("/"); return glob.glob(f"decks/ranks/*{r}/{d}.txt")[0]
out = {}
for a, b in pairs:
    ca = load_deck(path(a))[1]; cb = load_deck(path(b))[1]
    r = run_forge_match(a, ca, b, cb, games=100, seed=11, forge_dir="/home/user/forge", jobs=4, clock=240)
    out[f"{a} vs {b}"] = [r.wins_a, r.wins_b, r.draws, r.games]
    print(a, b, out[f"{a} vs {b}"], flush=True)
    json.dump(out, open(sys.argv[1], "w"), indent=1)

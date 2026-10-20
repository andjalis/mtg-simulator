"""Measure HeuristicAI.lethal_setup (precombat pump/burn/cast-trigger kill, commit 363d3ce).
Usage: python3 results/precombat-setup/measure.py ARM DECK_A DECK_B SEED GAMES -> one JSON line
ARM: mirror   - deck A with lethal_setup on vs deck B with it off
     on, off  - deck A with lethal_setup on / off vs deck B on the default HeuristicAI
     on_base, off_base - the same against deck B on BaselineAI
fires counts games in which deck A's setup cast at least one spell. Rows are in results.jsonl;
summarize.py pools them (AI_RESULTS.md, "Precombat kill setup")."""
import json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from mtgsim.ai import BaselineAI, HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.decklist import load_deck
from mtgsim.runner import build_deck, run_match

R = HERE.parents[1] / "decks"
DECKS = {"aggro": "ranks/4-platinum/mono_red_aggro.txt", "midrange": "ranks/4-platinum/rakdos_midrange.txt",
         "control": "ranks/4-platinum/azorius_control.txt", "stompy": "ranks/4-platinum/mono_green_stompy.txt",
         "combo": "combo/kiln_fiend_strobe.txt"}
FIRED = [0]


class CountingAI(HeuristicAI):
    """HeuristicAI that records whether lethal_setup cast anything this game."""
    def reset(self):
        super().reset()
        self._fired = False

    def lethal_setup(self, game, me):
        cast = super().lethal_setup(game, me)
        if cast and not self._fired:
            self._fired = True
            FIRED[0] += 1
        return cast


class NoSetupAI(HeuristicAI):
    def lethal_setup(self, game, me):
        return False


def main():
    arm, a, b, seed, n = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
    db = CardDB(offline=True)
    da, dbk = (build_deck(db, load_deck(R / DECKS[k])[1]) for k in (a, b))
    pa, pb = {"mirror": (CountingAI, NoSetupAI), "on": (CountingAI, HeuristicAI),
              "off": (NoSetupAI, HeuristicAI), "on_base": (CountingAI, BaselineAI), "off_base": (NoSetupAI, BaselineAI)}[arm]
    t = time.perf_counter()
    res, _ = run_match(a, da, b, dbk, games=n, seed=seed, ai_a=pa(), ai_b=pb())
    print(json.dumps(dict(arm=arm, a=a, b=b, seed=seed, games=res.games, wins_a=res.wins_a,
                          wins_b=res.wins_b, draws=res.draws, fires=FIRED[0],
                          secs=round(time.perf_counter() - t, 2))))


if __name__ == "__main__":
    main()

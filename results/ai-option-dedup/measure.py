"""Compare casting-choice policies with BaselineAI, using alternating starting seats.

From the repo root:
  python3 results/ai-option-dedup/measure.py before red 41 1000
  python3 results/ai-option-dedup/measure.py after granted-cheaper 41 1000

The before arm restores only the three changed option/response functions from
05a6abb. Planner guards are inert with the original one-option-per-name policy.
Both pilots use the selected arm's engine fallback policies. Fixtures are synthetic
diagnostics; their win rates do not estimate tournament matchups.
"""
import ast
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mtgsim import ai, engine, runner
from mtgsim.carddb import CardDB
from mtgsim.cards import card_from_scryfall
from mtgsim.decklist import load_deck


def restore_functions(module, path, names):
    source = subprocess.check_output(["git", "show", f"05a6abb:{path}"], cwd=ROOT, text=True)
    tree = ast.parse(source)
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in tree.body} == set(names)
    exec(compile(tree, f"05a6abb:{path}", "exec"), module.__dict__)


def fixture(db, native_cheaper):
    cost, native = ("{3}{R}", "{R}") if native_cheaper else ("{R}", "{3}{R}")
    recall = card_from_scryfall(dict(
        name="Diagnostic Recall", mana_cost=cost, cmc=4 if native_cheaper else 1,
        type_line="Instant", oracle_text="Draw two cards.\nFlashback " + native))
    mage = card_from_scryfall(dict(
        name="Diagnostic Mage", mana_cost="{1}{R}", cmc=2, type_line="Creature — Wizard",
        power="2", toughness="1", oracle_text="When this creature enters, target instant or sorcery card "
        "in your graveyard gains flashback until end of turn. The flashback cost is equal to its mana cost."))
    assert not recall.unsupported and not mage.unsupported
    return runner.build_deck(db, {"Mountain": 24, "Shock": 4, "Lightning Strike": 4,
                                  "Goblin Piker": 4, "Hill Giant": 4, "Raging Goblin": 4,
                                  "Gorehorn Minotaurs": 4}) + [recall] * 8 + [mage] * 4


def main():
    arm, deck_name, seed, games = sys.argv[1:]
    assert arm in ("before", "after")
    if arm == "before":
        restore_functions(ai, "mtgsim/ai.py", ["_spell_options"])
        restore_functions(engine, "mtgsim/engine.py", ["respond", "respond_extras"])
    db = CardDB(offline=True)
    if deck_name in ("granted-cheaper", "native-cheaper"):
        deck = fixture(db, deck_name == "native-cheaper")
    else:
        path = {"red": "mono_red_aggro.txt", "control": "ub_snow_control.txt"}[deck_name]
        deck = runner.build_deck(db, load_deck(ROOT / "decks" / path)[1])
    counts = dict(granted_casts=0, native_casts=0, granted_games=0)

    class MeasuredGame(engine.Game):
        def cast(self, p, card, targets=None):
            ok = super().cast(p, card, targets)
            origin = getattr(card, "origin", None)
            if ok and p.name == "Heuristic" and origin and origin[1] == "flashback":
                granted = getattr(card, "granted_flashback", False)
                counts["granted_casts" if granted else "native_casts"] += 1
                if granted:
                    self.used_grant = True
            return ok

        def play(self):
            winner = super().play()
            counts["granted_games"] += bool(getattr(self, "used_grant", False))
            return winner

    runner.Game = MeasuredGame
    start = time.monotonic()
    res, _ = runner.run_match("Heuristic", deck, "Baseline", deck,
                              games=int(games), seed=int(seed),
                              ai_a=ai.HeuristicAI(), ai_b=ai.BaselineAI())
    lo, hi = runner.wilson(res.wins_a + res.draws / 2, res.games)
    print(json.dumps(dict(arm=arm, deck=deck_name, seed=int(seed), games=res.games,
                          wins=res.wins_a, losses=res.wins_b, draws=res.draws,
                          score=res.win_rate_a, ci95=[lo, hi],
                          seconds=round(time.monotonic() - start, 3), **counts)), flush=True)


if __name__ == "__main__":
    main()

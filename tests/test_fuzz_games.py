"""Opt-in seeded fuzz: bounded AI games over the round-17 fixtures and a few real decks.

Skipped unless MTGSIM_FUZZ=1 (MTGSIM_FUZZ_GAMES overrides the 200 games). Every game must finish
without an exception and leave a clean state (tests/invariants.py). A failure names the deck and
seed, which is the whole reproduction: ``fuzz_game(deck_name, seed)``.
"""
import os
import random
import signal
import unittest

from mtgsim.ai import BaselineAI, HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.decklist import load_deck
from mtgsim.engine import Game, Player
from mtgsim.runner import build_deck
from tests.invariants import violations
from tests.test_combined_scenarios import BEAR, BOLT, CHOICE, DOOM, FADE, LICH, MIXED, MOUNTAIN, REPLAY, SPLITTER

LIMIT = int(os.environ.get("MTGSIM_FUZZ_SECONDS", "20"))   # wall clock per game
# Odd seeds face BaselineAI (it once retried a refused cast forever); MTGSIM_FUZZ_BASELINE=0 turns that off.
BASELINE = os.environ.get("MTGSIM_FUZZ_BASELINE", "1") == "1"
GAMES = int(os.environ.get("MTGSIM_FUZZ_GAMES", "200"))
FIXTURES = {
    "delayed-token": [MOUNTAIN] * 16 + [DOOM, FADE, SPLITTER, BEAR] * 3 + [BOLT] * 2,
    "mixed-equip": [MOUNTAIN] * 16 + [MIXED, CHOICE, DOOM, FADE, BEAR] * 3,
    "flashback-grant": [MOUNTAIN] * 16 + [REPLAY, LICH, BOLT, DOOM] * 3 + [BEAR] * 2,
    "all-three": [MOUNTAIN] * 16 + [DOOM, FADE, REPLAY, BOLT, MIXED, CHOICE, BEAR, LICH] * 3,
}
REAL_DECKS = ("mono_red_aggro", "green_stompy", "orzhov_midrange")


def deck_for(name):
    if name in FIXTURES:
        return FIXTURES[name]
    return build_deck(CardDB(offline=True), load_deck(f"decks/{name}.txt")[1])


class Hang(Exception):
    pass


def _on_alarm(signum, frame):
    raise Hang(f"no result after {LIMIT}s")


def fuzz_game(deck_name, seed, other="all-three"):
    """Play one bounded game; return (game, violations). Exceptions propagate."""
    a = Player("a", list(deck_for(deck_name)), HeuristicAI())
    b = Player("b", list(deck_for(other)), BaselineAI() if BASELINE and seed % 2 else HeuristicAI())
    g = Game(a, b, random.Random(seed), max_turns=14)
    signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(LIMIT)
    try:
        g.play()
    finally:
        signal.alarm(0)
    return g, violations(g)


@unittest.skipUnless(os.environ.get("MTGSIM_FUZZ") == "1", "set MTGSIM_FUZZ=1 to run the fuzz games")
class FuzzGames(unittest.TestCase):
    def test_seeded_games_raise_nothing_and_leave_a_clean_state(self):
        names = list(FIXTURES) + [d for d in REAL_DECKS if CardDB(offline=True)._all is not None]
        failures = []
        for i in range(GAMES):
            name, seed = names[i % len(names)], 1000 + i
            try:
                _, bad = fuzz_game(name, seed)
            except Exception as exc:    # report every crash with its reproduction, not just the first
                failures.append(f"{name} seed={seed}: {type(exc).__name__}: {exc}")
                continue
            if bad:
                failures.append(f"{name} seed={seed}: {bad}")
        self.assertEqual(failures, [], "\n".join(failures[:10]))


if __name__ == "__main__":
    unittest.main()

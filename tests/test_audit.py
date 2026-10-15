"""Builtin game logs are auditable: life totals reconstruct from logged changes and match the result."""
import json
import unittest
from pathlib import Path

from mtgsim.carddb import CardDB
from mtgsim.decklist import load_deck
from mtgsim.runner import build_deck, run_match

ROOT = Path(__file__).resolve().parents[1]
DB_FILE = ROOT / "mtgsim" / "data" / "cards.sqlite3"


def audit_events(events):
    return [json.loads(e[len("AUDIT "):]) for e in events if e.startswith("AUDIT ")]


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = CardDB(offline=True)
        cls.decks = [build_deck(db, load_deck(ROOT / "decks" / "ranks" / "4-platinum" / name)[1])
                     for name in ("mono_red_aggro.txt", "rakdos_midrange.txt")]

    def test_life_reconstructs_and_outcome_matches(self):
        logs = {}
        res, _ = run_match("aggro", self.decks[0], "midrange", self.decks[1], games=6, seed=3,
                           log_game=lambda n, events: logs.__setitem__(n, list(events)))
        self.assertEqual(sorted(logs), list(range(1, 7)))
        for number, events in logs.items():
            with self.subTest(game=number):
                audit = audit_events(events)
                start, result = audit[0], audit[-1]
                self.assertEqual((start["event"], start["turn_unit"], start["first_player"]),
                                 ("start", "player-turn", 0))
                # seat 0 is whoever went first; the runner alternates A and B.
                self.assertEqual(start["players"][0], "aggro" if number % 2 else "midrange")
                self.assertEqual({e["seat"] for e in audit if e["event"] == "keep"}, {0, 1})
                for e in audit:
                    if e["event"] in ("mulligan", "keep"):
                        self.assertEqual(len(e["hand"]), 7 if e["event"] == "mulligan" else 7 - e["mulligans"])
                life = list(start["life"])
                turns = [e["player_turn"] for e in audit]
                self.assertEqual(turns, sorted(turns))
                for e in audit:
                    if e["event"] == "life":
                        self.assertEqual(life[e["seat"]], e["before"])
                        self.assertTrue(e["cause"])
                        life[e["seat"]] += e["delta"]
                        self.assertEqual(life[e["seat"]], e["after"])
                self.assertEqual(result["event"], "result")
                self.assertEqual(life, result["life"])
                losses = {e["seat"] for e in audit if e["event"] == "loss"}
                self.assertEqual(losses, {i for i, lost in enumerate(result["lost"]) if lost})
                for seat in losses:
                    loss = next(e for e in audit if e["event"] == "loss" and e["seat"] == seat)
                    if loss["cause"].startswith("life"):
                        self.assertLessEqual(result["life"][seat], 0)
                if len(losses) == 1:
                    self.assertEqual(result["winner"], 1 - losses.pop())
                else:
                    self.assertIsNone(result["winner"])
                meta = res.game_metadata[number - 1]
                self.assertEqual(meta["player_turns"], result["player_turns"])
                self.assertEqual(meta["first_player"], 0 if number % 2 else 1)
                winner_name = start["players"][result["winner"]] if result["winner"] is not None else None
                self.assertEqual(meta["winner"], {"aggro": 0, "midrange": 1, None: None}[winner_name])

    def test_logging_off_by_default_records_no_events(self):
        res, first = run_match("aggro", self.decks[0], "midrange", self.decks[1], games=2, seed=3)
        self.assertEqual(first, [])
        self.assertEqual(res.games_a_on_play + res.games_a_on_draw, 2)


if __name__ == "__main__":
    unittest.main()

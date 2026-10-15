import io
import unittest
from contextlib import redirect_stdout

from mtgsim.__main__ import main, run_tiers
from mtgsim.carddb import CardDB
from mtgsim.decklist import load_deck
from mtgsim.runner import MatchResult
from mtgsim.tiers import TIERS, resolve_tiers


class TierTests(unittest.TestCase):
    def test_every_tier_deck_is_60_known_cards(self):
        db = CardDB(offline=True)
        for t in TIERS:
            self.assertTrue(t.decks(), f"{t.key} is empty")
            for path in t.decks():
                name, counts = load_deck(path)
                self.assertEqual(sum(counts.values()), 60, f"{t.key}/{name}")
                missing = [c for c in counts if c.lower() not in db.raw and not db.lookup(c)]
                self.assertEqual(missing, [], f"{t.key}/{name}")

    def test_resolve(self):
        self.assertEqual([t.key for t in resolve_tiers(["all"])], [t.key for t in TIERS])
        self.assertEqual([t.key for t in resolve_tiers(["pro", "Semi-pro", "1"])], ["trash", "semipro", "pro"])
        with self.assertRaises(ValueError):
            resolve_tiers(["9"])

    def test_ladder_stops_at_first_failed_tier(self):
        rates = {"trash": 0.9, "beginner": 0.6, "advanced": 0.4, "semipro": 0.8, "pro": 0.1}
        played = []

        def play(me, opp):
            played.append(opp)
            res = MatchResult(me, opp, games=10)
            res.wins_a = round(rates[opp] * 10)
            res.wins_b = 10 - res.wins_a
            return res

        out = io.StringIO()
        with redirect_stdout(out):
            run_tiers("me", TIERS, {t.key: [t.key] for t in TIERS}, play, ladder=True)
        self.assertEqual(played, ["trash", "beginner", "advanced"])
        self.assertIn("reached Beginner and stopped at Advanced", out.getvalue())

    def test_run_ladder(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main(["decks/tiers/3-advanced/orzhov_midrange.txt", "--ladder", "--pass-rate", "0", "--tier", "trash",
                  "beginner", "-n", "2", "--seed", "1", "--offline"])
        text = out.getvalue()
        self.assertIn("vs trash/vanilla_pile", text)
        self.assertIn("cleared every tier, up to and including Beginner", text)


if __name__ == "__main__":
    unittest.main()

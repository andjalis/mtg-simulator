import io
import unittest
from contextlib import redirect_stdout

from mtgsim.__main__ import main, run_tiers
from mtgsim.carddb import CardDB
from mtgsim.decklist import load_deck
from mtgsim.runner import MatchResult
from mtgsim.ranks import RANKS, resolve_ranks
from mtgsim.tiers import TIERS, resolve_tiers


class RankTests(unittest.TestCase):
    def test_every_rank_deck_is_60_known_cards(self):
        db = CardDB(offline=True)
        for t in RANKS:
            self.assertTrue(t.decks(), f"{t.key} is empty")
            for path in t.decks():
                name, counts = load_deck(path)
                self.assertEqual(sum(counts.values()), 60, f"{t.key}/{name}")
                missing = [c for c in counts if c.lower() not in db.raw and not db.lookup(c)]
                self.assertEqual(missing, [], f"{t.key}/{name}")

    def test_resolve(self):
        self.assertEqual([r.key for r in resolve_ranks(["all"])], [r.key for r in RANKS])
        self.assertEqual([r.key for r in resolve_ranks(["Grandmaster", "plat-inum", "1"])],
                         ["bronze", "platinum", "grandmaster"])
        self.assertEqual([r.key for r in resolve_ranks(["gm", "6"])], ["master", "grandmaster"])
        with self.assertRaises(ValueError):
            resolve_ranks(["9"])
        self.assertIs(TIERS, RANKS)  # old import path still works
        self.assertEqual(resolve_tiers(["2"]), resolve_ranks(["silver"]))

    def test_seven_ranks_in_order(self):
        self.assertEqual([r.label for r in RANKS],
                         ["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master", "Grandmaster"])

    def test_ladder_stops_at_first_failed_rank(self):
        rates = {"bronze": 0.9, "silver": 0.6, "gold": 0.4, "platinum": 0.8, "diamond": 0.8, "master": 0.8,
                 "grandmaster": 0.1}
        played = []

        def play(me, opp):
            played.append(opp)
            res = MatchResult(me, opp, games=10)
            res.wins_a = round(rates[opp] * 10)
            res.wins_b = 10 - res.wins_a
            return res

        out = io.StringIO()
        with redirect_stdout(out):
            run_tiers("me", RANKS, {r.key: [r.key] for r in RANKS}, play, ladder=True)
        self.assertEqual(played, ["bronze", "silver", "gold"])
        self.assertIn("reached Silver and stopped at Gold", out.getvalue())

    def test_run_ladder(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main(["decks/ranks/3-gold/orzhov_midrange.txt", "--ladder", "--pass-rate", "0", "--rank", "bronze",
                  "silver", "-n", "2", "--seed", "1", "--offline"])
        text = out.getvalue()
        self.assertIn("vs bronze/vanilla_pile", text)
        self.assertIn("cleared every rank, up to and including Silver", text)


if __name__ == "__main__":
    unittest.main()

"""#332 slice: "Choose a color. Add one mana of that color for each ..." (Astral Cornucopia), "... equal to your
devotion to that color" (Nyx Lotus, Nykthos) and "Reveal any number of <kind> cards in your hand. Add {C}{C} for
each card revealed this way" (Metalworker)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class ChosenAndRevealedMana(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def game(self, permanents=(), hand=()):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [self.db.get("Island")] * 10
        perms = []
        for name in permanents:
            x = g.enter_battlefield(a, self.db.get(name))
            x.sick = False
            perms.append(x)
        a.hand = [self.db.get(n) for n in hand]
        g.settle()
        return g, a, perms

    def activate(self, g, a, perm):
        idx = next(i for i, act in enumerate(perm.activated) if any(e.kind == "add_mana" for e in act.effects))
        self.assertTrue(g.activate_ability(a, perm, idx))
        g.settle()
        return sorted(x.card.name for x in a.pool)

    def test_parse(self):
        for name in ("Astral Cornucopia", "Nyx Lotus", "Nykthos, Shrine to Nyx", "Metalworker"):
            self.assertEqual(self.db.get(name).unsupported, [], name)
        # near misses stay visible, with their printed text
        self.assertTrue(self.db.get("Sacellum Godspeaker").unsupported[0].startswith("{T}: Reveal any number"))
        self.assertTrue(self.db.get("Queen's Diamond").unsupported)              # commander-only mana
        self.assertEqual(_parse_effects("Add {R}{G} for each creature you control.")[0], [])
        self.assertEqual(_parse_effects("Choose a color. Add one mana of that color for each different power "
                                        "among creatures you control.")[0], [])

    def test_astral_cornucopia_counts_charge_counters(self):
        g, a, (horn,) = self.game(["Astral Cornucopia"], hand=["Hill Giant"])
        horn.counters["charge"] = 3
        self.assertEqual(self.activate(g, a, horn), ["R mana"] * 3)       # one colour, the one the hand needs
        g, a, (horn,) = self.game(["Astral Cornucopia"])
        self.assertEqual(self.activate(g, a, horn), [])                   # no counters: no mana

    def test_nyx_lotus_picks_the_most_devotion(self):
        g, a, perms = self.game(["Nyx Lotus", "Grizzly Bears", "Grizzly Bears", "Hill Giant"])
        self.assertTrue(perms[0].tapped)                                   # it enters tapped
        perms[0].tapped = False
        self.assertEqual(self.activate(g, a, perms[0]), ["G mana", "G mana"])     # green 2 beats red 1

    def test_nykthos(self):
        g, a, perms = self.game(["Nykthos, Shrine to Nyx", "Forest", "Forest", "Llanowar Elves",
                                 "Grizzly Bears", "Centaur Courser"])
        nyk = perms[0]
        self.assertEqual(self.activate(g, a, nyk), ["G mana"] * 3)         # green devotion 3 (Elves, Bears, Courser): {2} paid by the Forests

    def test_metalworker_counts_artifacts_in_hand(self):
        g, a, (worker,) = self.game(["Metalworker"], hand=["Ornithopter", "Juggernaut", "Grizzly Bears"])
        self.assertEqual(self.activate(g, a, worker), ["C mana"] * 4)       # two artifact cards: {C}{C} each
        g, a, (worker,) = self.game(["Metalworker"], hand=["Grizzly Bears"])
        self.assertEqual(self.activate(g, a, worker), [])

    def test_ai_uses_metalworker(self):
        g, a, (worker,) = self.game(["Metalworker"], hand=["Juggernaut", "Juggernaut"])
        a.ai.main_phase(g, a)
        g.settle()
        self.assertIn("Juggernaut", [x.card.name for x in a.battlefield])     # four colorless from two revealed
        self.assertTrue(worker.tapped)


if __name__ == "__main__":
    unittest.main()

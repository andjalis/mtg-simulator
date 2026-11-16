"""#519 slice: threshold "instead" cards blocked by their replacement bodies: "and the damage can't be prevented"
(Lightning Surge), "each player sacrifices all lands they control" (Epicenter), "return that card from your
graveyard to the battlefield" (Stitch Together)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_cx_grammar import DB_FILE


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class ThresholdInstead(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [self.db.get("Island")] * 5

    def threshold(self, on):
        self.a.graveyard = [self.db.get("Island")] * (7 if on else 6)

    def resolve(self, name, targets):
        card = self.db.get(name)
        effects = list(card.spell_effects)
        targets = list(targets) + [None] * (len(effects) - len(targets))
        self.g.stack.append(StackItem(self.a, effects, targets, card=card, name=card.name))
        self.g.resolve_top()
        self.g.settle()

    def test_parse(self):
        for name in ("Lightning Surge", "Epicenter", "Stitch Together"):
            self.assertEqual(self.db.get(name).unsupported, [], name)
        self.assertTrue(_parse_effects("Each player sacrifices all lands you control.")[1])
        self.assertTrue(_parse_effects("~ gains flying and the damage can't be prevented.")[1])

    def test_lightning_surge_ignores_prevention_at_threshold(self):
        giant = self.g.enter_battlefield(self.b, self.db.get("Craw Wurm"))       # 6/4
        giant.prevent_next = 10
        self.threshold(False)
        self.resolve("Lightning Surge", [giant, giant])
        self.assertIn(giant, self.b.battlefield)                            # 4 damage, prevented
        self.assertEqual(giant.damage, 0)
        self.threshold(True)
        self.resolve("Lightning Surge", [giant, giant])
        self.assertNotIn(giant, self.b.battlefield)                         # 6 damage, can't be prevented

    def test_lightning_surge_damage_to_a_player(self):
        self.threshold(True)
        self.resolve("Lightning Surge", [self.b, self.b])
        self.assertEqual(self.b.life, 14)

    def test_epicenter(self):
        mine = [self.g.enter_battlefield(self.a, self.db.get("Plains")) for _ in range(3)]
        theirs = [self.g.enter_battlefield(self.b, self.db.get("Swamp")) for _ in range(3)]
        self.threshold(False)
        self.resolve("Epicenter", [self.b])
        self.assertEqual(sum(x in self.b.battlefield for x in theirs), 2)   # target player sacrifices one land
        self.assertTrue(all(x in self.a.battlefield for x in mine))
        self.threshold(True)
        self.resolve("Epicenter", [self.b])
        self.assertFalse(any(x.card.is_land for x in self.a.battlefield + self.b.battlefield))   # everyone, all

    def test_stitch_together(self):
        wurm = self.db.get("Craw Wurm")
        self.a.graveyard = [wurm] + [self.db.get("Island")] * 5
        self.resolve("Stitch Together", [])
        self.assertIn(wurm, self.a.hand)
        self.a.hand.remove(wurm)
        self.a.graveyard = [wurm] + [self.db.get("Island")] * 6
        self.resolve("Stitch Together", [])
        self.assertIn("Craw Wurm", [x.card.name for x in self.a.battlefield])
        self.assertNotIn(wurm, self.a.hand)


if __name__ == "__main__":
    unittest.main()

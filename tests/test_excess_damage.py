"""#560: "Excess damage is dealt to that creature's controller instead." The damage beyond lethal (toughness minus
marked damage; 1 from a deathtouch source, rule 120.4a) goes to the creature's controller."""
import random
import unittest
from pathlib import Path
from types import SimpleNamespace

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from mtgsim.excess_damage import split

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


class Parse(unittest.TestCase):
    def test_rider_marks_the_damage(self):
        effects, bad = _parse_effects("~ deals 4 damage to target creature. Excess damage is dealt to that creature's "
                                      "controller instead.")
        self.assertEqual(bad, [])
        self.assertEqual((effects[0].kind, effects[0].data.get("excess")), ("damage", "controller"))

    def test_near_misses_refused(self):
        for text in ("~ deals 4 damage to any target. Excess damage is dealt to that creature's controller instead.",
                     "Target creature gets -2/-2 until end of turn. Excess damage is dealt to that creature's "
                     "controller instead.",
                     "Excess damage is dealt to that creature's controller instead.",
                     "~ deals 4 damage to target creature. Excess damage is dealt to you instead."):
            effects, bad = _parse_effects(text)
            self.assertIn("Excess damage", " ".join(bad), text)

    def test_split(self):
        perm = SimpleNamespace(toughness=3, damage=1)
        plain = SimpleNamespace(has=lambda k: False)
        touch = SimpleNamespace(has=lambda k: k == "deathtouch")
        self.assertEqual(split(perm, 5, plain), (2, 3))
        self.assertEqual(split(perm, 2, plain), (2, 0))
        self.assertEqual(split(perm, 5, touch), (1, 4))
        perm.damage = 3                                       # already lethal damage marked: all of it is excess
        self.assertEqual(split(perm, 4, plain), (0, 4))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Games(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [self.db.get("Island")] * 20

    def cast(self, name, target):
        spell = self.db.get(name)
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, targets=[target]))
        self.game.settle()

    def land(self, name, n):
        for _ in range(n):
            self.game.enter_battlefield(self.a, self.db.get(name)).sick = False

    def test_real_cards_full(self):
        from mtgsim.coverage import card_coverage
        for name in ("Flame Spill", "Pigment Storm", "Gandalf's Sanction"):
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)
        self.assertEqual(card_coverage(self.db.get("Ram Through")).status, "full")   # the trample rider (test_excess_this_way)

    def test_flame_spill_excess_to_controller(self):
        bears = self.game.enter_battlefield(self.b, self.db.get("Grizzly Bears"))
        self.game.settle()
        self.land("Mountain", 3)
        self.cast("Flame Spill", bears)
        self.assertNotIn(bears, self.b.battlefield)
        self.assertEqual(self.b.life, 18)                     # 4 damage: 2 lethal, 2 excess

    def test_marked_damage_counts(self):
        giant = self.game.enter_battlefield(self.b, self.db.get("Hill Giant"))     # 3/3 with 1 damage: 2 is lethal
        self.game.settle()
        giant.damage = 1
        self.land("Mountain", 3)
        self.cast("Flame Spill", giant)
        self.assertNotIn(giant, self.b.battlefield)
        self.assertEqual(self.b.life, 18)

    def test_gandalfs_sanction_counts_then_spills(self):
        self.a.graveyard = [self.db.get(n) for n in ("Shock", "Opt", "Divination", "Grizzly Bears")]
        elf = self.game.enter_battlefield(self.b, self.db.get("Llanowar Elves"))
        self.game.settle()
        self.land("Island", 2)
        self.land("Mountain", 1)
        self.cast("Gandalf's Sanction", elf)
        self.assertNotIn(elf, self.b.battlefield)
        self.assertEqual(self.b.life, 18)                     # X = 3 (two instants, a sorcery): 1 lethal, 2 excess

    def test_ai_casts_it_at_the_opponents_creature(self):
        bears = self.game.enter_battlefield(self.b, self.db.get("Grizzly Bears"))
        mine = self.game.enter_battlefield(self.a, self.db.get("Grizzly Bears"))
        self.game.settle()
        self.land("Mountain", 5)
        self.a.hand = [self.db.get("Pigment Storm")]          # a sorcery: the AI holds instants for the other turn
        self.game.main_phase(self.a)
        self.game.settle()
        self.assertEqual(self.a.hand, [])
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(bears, self.b.battlefield)
        self.assertEqual(self.b.life, 17)                     # 5 damage: 2 lethal, 3 excess


if __name__ == "__main__":
    unittest.main()

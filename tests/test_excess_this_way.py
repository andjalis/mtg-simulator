"""#560 follow-up: "excess damage ... this way" (rule 120.4a). deal_damage keeps game.excess_dealt (the damage beyond
lethal dealt to creatures and planeswalkers in this resolution: toughness minus marked damage, 1 from deathtouch,
loyalty), read as a condition ("If excess damage was dealt this way, ...") and a quantity ("equal to the (amount of)
excess damage dealt this way", "where X is that excess damage"). Ram Through: the excess goes to the controller
only if the biting creature has trample."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


class Parse(unittest.TestCase):
    def test_refusals(self):
        for text in ("When excess damage is dealt to the creature an opponent controls this way, draw a card.",
                     "If excess damage would be dealt to that creature this way, draw a card instead.",
                     "~ deals 3 damage to target creature. If the creature you control has trample, excess damage is "
                     "dealt to that creature's controller instead."):        # the trample rider needs a bite
            effects, bad = _parse_effects(text)
            self.assertTrue(any("xcess damage" in b for b in bad), text)


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

    def enter(self, p, name):
        perm = self.game.enter_battlefield(p, self.db.get(name))
        self.game.settle()
        perm.sick = perm.tapped = False
        return perm

    def lands(self, name, n):
        for _ in range(n):
            self.enter(self.a, name)

    def cast(self, name, targets):
        spell = self.db.get(name)
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, targets=targets), name)
        self.game.settle()

    def tokens(self, name):
        return [x for x in self.a.battlefield if x.card.is_token and name in x.card.name]

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in ("Orbital Plunge", "Windswift Slice", "Razor Rings", "Goblin Negotiation", "Hell to Pay",
                     "Lacerate Flesh", "Overwhelming Victory", "Contest of Claws", "Vikya, Scorching Stalwart",
                     "Violent Echoes", "Ram Through"):
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)

    def test_orbital_plunge_only_with_excess(self):
        bears = self.enter(self.b, "Grizzly Bears")
        self.lands("Mountain", 4)
        self.cast("Orbital Plunge", [bears])                # 6 to a 2/2: 4 excess
        self.assertEqual(len(self.tokens("Lander")), 1)

    def test_orbital_plunge_no_excess(self):
        big = self.enter(self.b, "Colossal Dreadmaw")       # 6/6: exactly lethal, no excess
        self.lands("Mountain", 4)
        self.cast("Orbital Plunge", [big])
        self.assertEqual(self.tokens("Lander"), [])
        self.assertNotIn(big, self.b.battlefield)

    def test_marked_damage_and_life_from_excess(self):
        giant = self.enter(self.b, "Hill Giant")            # 3/3 with 1 damage: 2 lethal, Razor Rings' 4 -> 2 excess
        giant.damage = 1
        self.game.attackers = [giant]                       # "target attacking or blocking creature"
        self.lands("Plains", 2)
        self.a.life = 10
        self.cast("Razor Rings", [giant])
        self.assertEqual(self.a.life, 12)

    def test_windswift_slice_counts_the_bite_excess(self):
        mine = self.enter(self.a, "Colossal Dreadmaw")      # 6 power into a 2/2: 4 excess
        bears = self.enter(self.b, "Grizzly Bears")
        self.lands("Forest", 3)
        self.cast("Windswift Slice", [mine, bears])
        self.assertEqual(len(self.tokens("Elf Warrior")), 4)
        self.assertEqual(self.b.life, 20)                   # no trample rider: nothing to the player

    def test_ram_through_tramples_over_only_with_trample(self):
        mine = self.enter(self.a, "Colossal Dreadmaw")      # 6/6 trample
        bears = self.enter(self.b, "Grizzly Bears")
        self.lands("Forest", 2)
        self.cast("Ram Through", [mine, bears])
        self.assertNotIn(bears, self.b.battlefield)
        self.assertEqual(self.b.life, 16)                   # 2 lethal, 4 excess to the controller

    def test_ram_through_without_trample(self):
        mine = self.enter(self.a, "Craw Wurm")              # 6/4, no trample
        bears = self.enter(self.b, "Grizzly Bears")
        self.lands("Forest", 2)
        self.cast("Ram Through", [mine, bears])
        self.assertNotIn(bears, self.b.battlefield)
        self.assertEqual(self.b.life, 20)

    def test_excess_resets_each_resolution(self):
        bears = self.enter(self.b, "Grizzly Bears")
        dreadmaw = self.enter(self.b, "Colossal Dreadmaw")
        self.lands("Mountain", 8)
        self.cast("Orbital Plunge", [bears])                # excess 4
        self.cast("Orbital Plunge", [dreadmaw])             # exactly lethal: the earlier excess doesn't carry over
        self.assertEqual(len(self.tokens("Lander")), 1)

    def test_ai_aims_ram_through(self):
        mine = self.enter(self.a, "Colossal Dreadmaw")
        bears = self.enter(self.b, "Grizzly Bears")
        self.lands("Forest", 2)
        self.a.hand = [self.db.get("Ram Through")]
        self.game.step = "main2"
        self.game.main_phase(self.a)
        self.game.settle()
        if self.a.hand:                                      # an instant: the AI may hold it for the other turn
            self.skipTest("HeuristicAI holds the instant")
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(bears, self.b.battlefield)
        self.assertEqual(self.b.life, 16)


if __name__ == "__main__":
    unittest.main()

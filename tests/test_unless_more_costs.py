"""#330 slice: more "sacrifice ~ unless you <cost>" costs: exile the top creature card of your graveyard, return a
<kind> card from your graveyard to your hand, put a graveyard card on the bottom of your library, return an
<kind> (anyone's) to its owner's hand, remove a counter from a permanent you control; and "sacrifice it unless"
after an attacks-or-blocks head."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class MoreUnlessCosts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = [self.db.get("Island")] * 5
        self.b.library = [self.db.get("Island")] * 5

    def put(self, name, who=None):
        return self.g.enter_battlefield(who or self.a, self.db.get(name))

    def upkeep(self):
        self.g.fire(self.a, "upkeep")
        self.g.settle()

    def test_parse(self):
        for name in ("Rotting Giant", "Treacherous Vampire", "Barrow Ghoul", "Harvest Wurm", "Drake Familiar",
                     "Chisei, Heart of Oceans", "Anurid Scavenger"):
            self.assertEqual(self.db.get(name).unsupported, [], name)
        for text in ("Sacrifice ~ unless you return a card from an opponent's graveyard to your hand.",
                     "Sacrifice ~ unless you remove a counter from a permanent an opponent controls.",
                     "Sacrifice ~ unless you exile the top two cards of your graveyard."):
            self.assertTrue(_parse_effects(text)[1], text)

    def test_barrow_ghoul_exiles_the_top_creature_card(self):
        ghoul = self.put("Barrow Ghoul")
        bears, wurm, growth = (self.db.get(n) for n in ("Grizzly Bears", "Craw Wurm", "Giant Growth"))
        self.a.graveyard = [wurm, bears, growth]                 # last is the top: Bears is the top creature
        self.upkeep()
        self.assertIn(ghoul, self.a.battlefield)
        self.assertEqual([c.name for c in self.a.exile], ["Grizzly Bears"])
        self.a.graveyard = [growth]
        self.upkeep()
        self.assertNotIn(ghoul, self.a.battlefield)              # no creature card: sacrificed

    def test_harvest_wurm_returns_a_basic_land(self):
        self.a.graveyard = [self.db.get("Forest"), self.db.get("Grizzly Bears")]
        wurm = self.put("Harvest Wurm")
        self.g.settle()
        self.assertIn(wurm, self.a.battlefield)
        self.assertIn("Forest", [c.name for c in self.a.hand])
        self.a.graveyard = [self.db.get("Grizzly Bears")]
        wurm2 = self.put("Harvest Wurm")
        self.g.settle()
        self.assertNotIn(wurm2, self.a.battlefield)

    def test_drake_familiar_returns_an_opponents_enchantment_first(self):
        theirs = self.put("Pacifism", self.b)
        mine = self.put("Glorious Anthem")
        drake = self.put("Drake Familiar")
        self.g.settle()
        self.assertIn(drake, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)
        self.assertIn(mine, self.a.battlefield)

    def test_chisei_removes_a_minus_counter_first(self):
        chisei = self.put("Chisei, Heart of Oceans")
        bear = self.put("Grizzly Bears")
        bear.counters["-1/-1"] = 1
        other = self.put("Hill Giant")
        other.counters["+1/+1"] = 1
        self.upkeep()
        self.assertIn(chisei, self.a.battlefield)
        self.assertEqual(bear.counters.get("-1/-1"), 0)          # the counter whose loss helps
        self.assertEqual(other.counters.get("+1/+1"), 1)
        self.upkeep()
        self.assertIn(chisei, self.a.battlefield)                # then the +1/+1 one
        self.upkeep()
        self.assertNotIn(chisei, self.a.battlefield)             # none left

    def test_anurid_scavenger_puts_a_card_on_the_bottom(self):
        scav = self.put("Anurid Scavenger")
        self.a.graveyard = [self.db.get("Craw Wurm"), self.db.get("Forest")]
        self.upkeep()
        self.assertIn(scav, self.a.battlefield)
        self.assertEqual(self.a.library[0].name, "Forest")       # the least useful card, at the bottom
        self.assertEqual([c.name for c in self.a.graveyard], ["Craw Wurm"])

    def test_rotting_giant_attacks(self):
        giant = self.put("Rotting Giant")
        giant.sick = False
        self.a.graveyard = [self.db.get("Forest")]
        self.g.fire(self.a, "attacks", giant)
        self.g.settle()
        self.assertIn(giant, self.a.battlefield)
        self.assertEqual(self.a.graveyard, [])
        self.g.fire(self.a, "attacks", giant)
        self.g.settle()
        self.assertNotIn(giant, self.a.battlefield)


if __name__ == "__main__":
    unittest.main()

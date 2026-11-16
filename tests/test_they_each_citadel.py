"""#313: "They each ..." after counted targets, and Bolas's Citadel's life payment for top-of-library spells."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import FOREST, ISLAND, MOUNTAIN, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


class Base(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [ISLAND] * 10

    def creature(self, owner, p, t, name="Bear"):
        x = self.g.enter_battlefield(owner, card(name, "{1}", "Creature — Bear", "", p, t))
        x.sick = False
        return x

    def cast(self, c, targets):
        self.assertEqual(c.unsupported, [], c.name)
        effects = list(c.spell_effects)
        self.g.stack.append(StackItem(self.a, effects, targets, card=c, name=c.name))
        self.g.resolve_top()


class TheyEach(Base):
    def test_each_gets_the_pump(self):
        c = card("Test Forces", "{G}", "Instant",
                 "Untap up to two target creatures. They each get +2/+2 until end of turn.")
        x, y = self.creature(self.a, 2, 2), self.creature(self.a, 1, 1)
        x.tapped = y.tapped = True
        kinds = [e.kind for e in c.spell_effects]
        self.assertEqual(kinds.count("pump"), 2)
        self.cast(c, [x if e is c.spell_effects[0] else y if e is c.spell_effects[2] else None
                      for e in c.spell_effects])
        self.assertEqual([(x.power, x.tapped), (y.power, y.tapped)], [(4, False), (3, False)])

    def test_each_deals_its_own_damage_to_one_target(self):
        c = card("Test Clobber", "{G}", "Sorcery", "Tap one or two target untapped creatures you control. They each "
                                                   "deal damage equal to their power to target creature an opponent "
                                                   "controls.")
        x, y = self.creature(self.a, 3, 3), self.creature(self.a, 2, 2)
        t = self.creature(self.b, 4, 5, "Beast")
        self.cast(c, [x, y, None, t])
        self.assertNotIn(t, self.b.battlefield)
        self.assertEqual((x.damage, y.damage), (0, 0))

    def test_a_source_gone_before_resolution_deals_nothing(self):
        c = card("Test Clobber", "{G}", "Sorcery", "Tap one or two target untapped creatures you control. They each "
                                                   "deal damage equal to their power to target creature an opponent "
                                                   "controls.")
        x, y = self.creature(self.a, 3, 3), self.creature(self.a, 2, 2)
        t = self.creature(self.b, 4, 5, "Beast")
        self.g.leave_battlefield(y, "hand")
        self.cast(c, [x, y, None, t])
        self.assertEqual(t.damage, 3)

    def test_rejects_without_counted_targets(self):
        c = card("Test", "{G}", "Instant", "Untap target creature. They each get +2/+2 until end of turn.")
        self.assertNotEqual(c.unsupported, [])

    def test_ai_taps_its_own_creatures(self):
        for land in (MOUNTAIN, FOREST):
            self.g.enter_battlefield(self.a, land).sick = False
        x, y = self.creature(self.a, 3, 3), self.creature(self.a, 2, 2)
        t = self.creature(self.b, 4, 5, "Beast")
        self.a.hand.append(card("Test Clobber", "{G}", "Sorcery", "Tap one or two target untapped creatures you "
                                "control. They each deal damage equal to their power to target creature an opponent "
                                "controls."))
        self.g.main_phase(self.a)
        self.g.settle()
        self.assertNotIn(t, self.b.battlefield)
        self.assertTrue(x.tapped and y.tapped)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Citadel(Base):
    def setUp(self):
        super().setUp()
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in ("Bolas's Citadel", "Join Forces", "Fancy Footwork", "Synchronized Strike",
                     "Coordinated Clobbering", "Terrific Team-Up", "Tandem Takedown"):
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)

    def test_cast_from_the_top_for_life(self):
        ogre = card("Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)
        self.a.library = [ISLAND] * 5 + [ogre]
        self.g.enter_battlefield(self.a, self.db.get("Bolas's Citadel"))
        self.g.main_phase(self.a)                  # no lands: only the life payment casts it
        self.g.settle()
        self.assertEqual(self.a.life, 17)
        self.assertTrue(any(x.card.name.startswith("Ogre") for x in self.a.battlefield))

    def test_existing_guard_never_pays_its_last_life(self):      # play.py refuses an alt life cost >= life
        ogre = card("Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)
        self.a.library = [ISLAND] * 5 + [ogre]
        self.a.life = 3
        self.g.enter_battlefield(self.a, self.db.get("Bolas's Citadel"))
        self.g.main_phase(self.a)
        self.g.settle()
        self.assertEqual(self.a.life, 3)


if __name__ == "__main__":
    unittest.main()

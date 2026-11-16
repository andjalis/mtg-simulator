"""#863: a group effect's X ("put X +1/+1 counters on each creature you control, where X is ...", "each creature
gets -X/-X") applied X = 1 to every member."""
import unittest

from mtgsim.engine import Permanent, StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import card, BEAR

OGRE = card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)
VAMP = card("Test Vampire", "{1}{B}", "Creature — Vampire", "", 2, 2)


class GroupX(Base):
    def resolve(self, text):
        c = card("Test Spell", "{2}", "Sorcery", text)
        self.assertEqual(c.unsupported, [])
        self.assertEqual(c.spell_effects[0].kind, "permanent_group")
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [None] * len(c.spell_effects), card=c,
                                         name=c.name))
        self.game.resolve_top()
        self.game.settle()

    def test_x_counters_on_each(self):
        bear = Permanent(BEAR, self.a)
        self.a.battlefield, self.a.graveyard = [bear], [OGRE, OGRE, OGRE]
        self.resolve("Put X +1/+1 counters on each creature you control, where X is the number of creature cards in "
                     "your graveyard.")
        self.assertEqual(bear.counters.get("+1/+1"), 3)

    def test_each_gets_minus_x(self):
        ogre = Permanent(OGRE, self.b)
        self.a.battlefield, self.b.battlefield = [Permanent(VAMP, self.a), Permanent(VAMP, self.a)], [ogre]
        self.resolve("Each creature your opponents control gets -X/-X until end of turn, where X is the number of "
                     "Vampires you control.")
        self.assertEqual((ogre.power, ogre.toughness), (1, 1))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCard(Base):
    def test_olivias_wrath(self):
        from mtgsim.carddb import CardDB
        wrath = CardDB(offline=True).get("Olivia's Wrath")
        ogre = Permanent(OGRE, self.b)
        self.a.battlefield, self.b.battlefield = [Permanent(VAMP, self.a), Permanent(VAMP, self.a)], [ogre]
        self.game.stack.append(StackItem(self.a, list(wrath.spell_effects), [None] * len(wrath.spell_effects),
                                         card=wrath, name=wrath.name))
        self.game.resolve_top()
        self.game.settle()
        self.assertEqual((ogre.power, ogre.toughness), (1, 1))


if __name__ == "__main__":
    unittest.main()

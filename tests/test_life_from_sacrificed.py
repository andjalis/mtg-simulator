"""Audit 2026-11-16 (opus-cast): "You gain life equal to its power / that creature's toughness" after a sacrifice read
only the previous effect's object (a player for an edict), so no life was gained (Consume, Tribute to Hunger,
Consuming Vapors, Doomgape)."""
import unittest

from mtgsim.engine import StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

WURM = card("Test Wurm", "{4}{G}{G}", "Creature — Wurm", "", 6, 4)
TRIBUTE = card("Test Tribute", "{2}{B}", "Instant", "Target opponent sacrifices a creature. You gain life equal to that "
               "creature's toughness.")


class LifeFromSacrificed(Base):
    def cast(self, c, targets):
        item = StackItem(self.a, list(c.spell_effects), list(targets), card=c, name=c.name)
        self.game.stack.append(item)
        self.game.resolve_top()
        self.game.settle()

    def test_edict_then_toughness(self):
        self.perm(WURM, self.b)
        self.cast(TRIBUTE, [self.b] + [None] * (len(TRIBUTE.spell_effects) - 1))
        self.assertEqual(self.a.life, 24)                  # the Wurm's toughness

    def test_no_sacrifice_no_life(self):
        self.cast(TRIBUTE, [self.b] + [None] * (len(TRIBUTE.spell_effects) - 1))
        self.assertEqual(self.a.life, 20)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def card(self, name):
        from mtgsim.carddb import CardDB
        return CardDB(offline=True).get(name)

    def test_consume(self):
        self.perm(BEAR, self.b)
        self.perm(WURM, self.b)
        right = self.card("Consecrate // Consume").split_right
        item = StackItem(self.a, list(right.spell_effects), [self.b] + [None] * (len(right.spell_effects) - 1),
                         card=right, name=right.name)
        self.game.stack.append(item)
        self.game.resolve_top()
        self.game.settle()
        self.assertEqual(self.a.life, 26)                  # the Wurm (greatest power, 6)

    def test_doomgape(self):
        self.game.enter_battlefield(self.a, self.card("Doomgape"))
        self.perm(WURM, self.a)
        self.game.settle()
        self.game.begin_upkeep(self.a)
        self.game.settle()
        self.assertGreater(self.a.life, 20)                # gains the sacrificed creature's toughness


if __name__ == "__main__":
    unittest.main()

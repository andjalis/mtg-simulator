"""#646 slice 10: Gravestorm (CR 702.69; cast_triggers, the per-turn count in Game.leave_battlefield)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.engine import StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

HARVEST = card("Test Harvest", "{B}{B}", "Sorcery", "Gravestorm\nTarget player draws a card and loses 1 life.")
TOKEN = card("Spirit", "", "Token Creature — Spirit", "", 1, 1)


class Parsing(unittest.TestCase):
    def test_keyword(self):
        self.assertEqual(HARVEST.unsupported, [])
        self.assertIn("gravestorm", HARVEST.keywords)


class Engine(Base):
    def cast_harvest(self):
        from mtgsim.cast_triggers import on_cast
        item = StackItem(self.a, list(HARVEST.spell_effects), [self.b] * len(HARVEST.spell_effects), card=HARVEST,
                         name="Test Harvest")
        self.game.stack.append(item)
        on_cast(self.game, self.a, item)
        self.game.settle()

    def test_counts_permanents_put_into_a_graveyard_this_turn(self):
        """CR 702.69a: tokens count (they go to the graveyard before they cease to exist); exile doesn't."""
        bear, token, other = self.perm(BEAR, self.b), self.perm(TOKEN, self.a), self.perm(BEAR, self.a)
        self.game.destroy(bear)
        self.game.sacrifice(token)
        self.game.leave_battlefield(other, "exile")
        self.assertEqual(self.game.to_graveyard_turn, 2)

    def test_copies_for_each(self):
        """CR 702.69a: copy it for each permanent put into a graveyard from the battlefield this turn."""
        for _ in range(2):
            self.game.destroy(self.perm(BEAR, self.b))
        life = self.a.life + self.b.life
        self.cast_harvest()
        # the spell and two copies (the copies may get new targets: the AI aims "draws a card" at itself)
        self.assertEqual(self.a.life + self.b.life, life - 3)

    def test_no_copies_without_deaths(self):
        life = self.b.life
        self.cast_harvest()
        self.assertEqual(self.b.life, life - 1)


class Turns(Base):
    def test_count_resets_each_turn(self):
        self.game.destroy(self.perm(BEAR, self.b))
        self.assertEqual(self.game.to_graveyard_turn, 1)
        self.game.take_turn(self.b)
        self.assertEqual(self.game.to_graveyard_turn, 0)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Follow the Bodies", "Ominous Harvest", "Bitter Ordeal"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()

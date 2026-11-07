"""The evasion verb family (mtgsim.cx_grammar_evasion): can't be blocked by / except by, can't block."""
import unittest

from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine.state import can_block

from tests.test_cx_grammar import DB_FILE, GOBLIN, Base
from tests.test_templates import BEAR, card

WALL = card("Test Wall", "{1}", "Creature — Wall", "Defender", 0, 4)
FLIER = card("Test Bird", "{U}", "Creature — Bird", "Flying", 1, 1)


def shade():
    c = card("Test Shade", "{B}{B}", "Creature — Shade", "", 3, 3)
    assert "B" in c.colors
    return c


class Statics(Base):
    def test_host_cant_be_blocked_by_a_colour(self):
        scarab = card("Test Scarab", "{W}", "Enchantment — Aura",
                      "Enchant creature\nEnchanted creature can't be blocked by black creatures.")
        self.assertEqual(scarab.unsupported, [])
        bear = self.perm(BEAR, self.a)
        aura = self.perm(scarab, self.a)
        aura.attached_to = bear
        black, other = self.perm(shade(), self.b), self.perm(BEAR, self.b)
        self.assertFalse(can_block(black, bear))
        self.assertTrue(can_block(other, bear))

    def test_group_static(self):
        lord = card("Test Lord", "{R}", "Creature — Goblin", "Other Goblins you control can't be blocked by Walls.", 1, 1)
        self.assertEqual(lord.unsupported, [])
        self.perm(lord, self.a)
        goblin, bear = self.perm(GOBLIN, self.a), self.perm(BEAR, self.a)
        wall = self.perm(WALL, self.b)
        self.assertFalse(can_block(wall, goblin))
        self.assertTrue(can_block(wall, bear))

    def test_self_cant_block(self):
        c = card("Test Crawler", "{G}", "Creature — Insect", "~ can't block creatures with flying.", 2, 2)
        self.assertEqual(c.unsupported, [])
        crawler, bird, bear = self.perm(c, self.b), self.perm(FLIER, self.a), self.perm(BEAR, self.a)
        self.assertFalse(can_block(crawler, bird))
        self.assertTrue(can_block(crawler, bear))


class ThisTurn(Base):
    def test_one_shot_lasts_this_turn(self):
        bear, wall = self.perm(BEAR, self.a), self.perm(WALL, self.b)
        spell = self.spell("Target creature can't be blocked by creatures with power 2 or less this turn.")
        self.cast(spell, [bear])
        self.assertFalse(can_block(wall, bear))
        self.game.turn += 1
        self.assertTrue(can_block(wall, bear))

    def test_rejects(self):
        for s in ("Target creature can't be blocked by more than one creature this turn.",
                  "~ can't be blocked except by artifact creatures and/or black creatures."):
            self.assertIsNone(parse_sentence(s), s)


class AIUse(Base):
    def test_ai_attacks_past_blockers_that_cant_block(self):
        lord = card("Test Lord", "{R}", "Creature — Goblin", "Other Goblins you control can't be blocked by Walls.", 1, 1)
        self.perm(lord, self.a).sick = False
        for _ in range(2):
            self.perm(GOBLIN, self.a).sick = False
        for _ in range(2):
            self.perm(WALL, self.b)
        self.game.turn = 3
        life = self.b.life
        self.game.take_turn(self.a)
        self.assertLess(self.b.life, life - 1)          # the Goblins got through the Walls

    def test_ai_aims_the_one_shot_at_its_own_creature(self):
        mine = self.perm(BEAR, self.a)
        self.perm(BEAR, self.b)
        spell = self.spell("Target creature can't be blocked by creatures with power 2 or less this turn.")
        with self.game.targeting(spell):
            self.assertIs(self.a.ai.choose_target(self.game, self.a, spell.spell_effects[0], spell), mine)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_scarabs(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Black Scarab", "Blue Scarab", "Green Scarab"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()

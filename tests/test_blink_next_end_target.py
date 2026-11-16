"""Audit 2026-11-16 (opus-cast), #774: "exile target <permanent>, return it at the beginning of the next end step"
(blink_next_end) always chose the chooser's own best permanent: Mistmeadow Vanisher exiled itself, and a mandatory
trigger with only opposing legal targets fizzled (Skybind; CR 603.3d)."""
import unittest

from mtgsim.engine.policy import default_choose_target
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

WURM = card("Test Wurm", "{4}{G}{G}", "Creature — Wurm", "", 6, 4)
ELK = card("Test Elk", "{2}{G}", "Creature — Elk", "When this creature enters, you gain 3 life.", 2, 2)
VANISHER = card("Test Vanisher", "{2}{W}", "Creature — Kithkin Wizard", "Whenever this creature becomes tapped, exile up "
                "to one target nonland, nontoken permanent. Return that card to the battlefield under its owner's "
                "control at the beginning of the next end step.", 3, 2)
SKYBIND = card("Test Skybind", "{3}{W}{W}", "Enchantment", "Constellation — Whenever this enchantment or another "
               "enchantment you control enters, exile target nonenchantment permanent. Return that card to the "
               "battlefield under its owner's control at the beginning of the next end step.")


class Chooser(Base):
    def choose(self, c, source):
        eff = c.triggers[0].effects[0]
        with self.game.targeting(source):
            return default_choose_target(self.game, self.a, eff)

    def test_not_itself_but_the_opponents_best(self):
        v = self.perm(VANISHER, self.a)
        wurm = self.perm(WURM, self.b)
        self.perm(BEAR, self.b)
        self.assertIs(self.choose(VANISHER, v), wurm)

    def test_own_creature_with_an_enters_ability_is_worth_blinking(self):
        v = self.perm(VANISHER, self.a)
        elk = self.perm(ELK, self.a)
        self.perm(BEAR, self.b)
        self.assertIs(self.choose(VANISHER, v), elk)

    def test_optional_with_nothing_good_chooses_nothing(self):
        v = self.perm(VANISHER, self.a)
        self.assertIsNone(self.choose(VANISHER, v))

    def test_mandatory_trigger_targets_when_it_can(self):
        """Skybind's own entry: only the opponent's Wurm is a legal target; the trigger must not fizzle."""
        wurm = self.perm(WURM, self.b)
        self.game.enter_battlefield(self.a, SKYBIND)
        self.game.settle()
        self.assertNotIn(wurm, self.b.battlefield)
        self.game.begin_end_step(self.a)
        self.game.settle()
        self.assertEqual([x.card.name for x in self.b.battlefield], ["Test Wurm"])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def test_flickerwisp_takes_the_opponents_best(self):
        from mtgsim.carddb import CardDB
        wurm = self.perm(WURM, self.b)
        self.game.enter_battlefield(self.a, CardDB(offline=True).get("Flickerwisp"))
        self.game.settle()
        self.assertNotIn(wurm, self.b.battlefield)


if __name__ == "__main__":
    unittest.main()

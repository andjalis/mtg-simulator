"""'Outlaw' (rule 700.12: Assassin, Mercenary, Pirate, Rogue or Warlock) in selectors and condition filters, so
'... instead if you control an outlaw' (Take the Fall, #321) and the other outlaw cards read; Wizards are not outlaws."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from mtgsim.engine.state import OUTLAWS
from mtgsim.permanent_templates import selector
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card

ROGUE = card("Test Rogue", "{1}{B}", "Creature — Human Rogue", "", 2, 2)
WIZARD = card("Test Wizard", "{1}{U}", "Creature — Human Wizard", "", 1, 1)
SHIFTER = card("Test Shifter", "{1}{U}", "Creature — Shapeshifter", "Changeling", 1, 1)
OGRE = card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 5, 5)
FALL = card("Test Fall", "{2}{B}", "Instant", "Target creature gets -1/-0 until end of turn. It gets -4/-0 until end of "
            "turn instead if you control an outlaw.")


def game():
    a, b = Player("a", [ISLAND] * 10, HeuristicAI()), Player("b", [ISLAND] * 10, HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    for p in (a, b):
        p.library = [ISLAND] * 20
    return g, a, b


class Parse(unittest.TestCase):
    def test_outlaws_constant(self):
        self.assertEqual(set(OUTLAWS), {"Assassin", "Mercenary", "Pirate", "Rogue", "Warlock"})

    def test_selector(self):
        self.assertEqual(sorted(selector("outlaws you control", plural=True)["any_subtypes"]),
                         ["assassin", "mercenary", "pirate", "rogue", "warlock"])
        self.assertIn("not_subtypes", selector("non-outlaw creature"))

    def test_instead_condition(self):
        self.assertEqual(FALL.unsupported, [])
        effects, _ = _parse_effects("Draw a card. Draw two cards instead if you control an outlaw.")
        self.assertEqual([e.amount for e in effects], [1, 2])


class Engine(unittest.TestCase):
    def fall(self, mine):
        g, a, b = game()
        if mine is not None:
            g.enter_battlefield(a, mine)
        ogre = g.enter_battlefield(b, OGRE)
        g.stack.append(StackItem(a, list(FALL.spell_effects), [ogre] + [None] * (len(FALL.spell_effects) - 1),
                                 card=FALL, name=FALL.name))
        g.resolve_top()
        return ogre.power

    def test_take_the_fall(self):
        self.assertEqual(self.fall(None), 4)
        self.assertEqual(self.fall(ROGUE), 1)
        self.assertEqual(self.fall(SHIFTER), 1)          # a changeling is every creature type
        self.assertEqual(self.fall(WIZARD), 4)           # not an outlaw

    def test_non_outlaw_target(self):
        effects, bad = _parse_effects("Destroy target non-outlaw creature.")
        self.assertEqual(bad, [])
        g, a, b = game()
        rogue, ogre, wizard = (g.enter_battlefield(b, c) for c in (ROGUE, OGRE, WIZARD))
        legal = g.legal_targets(a, effects[0])
        self.assertIn(ogre, legal)
        self.assertIn(wizard, legal)
        self.assertNotIn(rogue, legal)


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class Cards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Take the Fall", "Shoot the Sheriff", "Hellspur Posse Boss", "Vihaan, Goldwaker",
                     "Olivia, Opulent Outlaw", "Outlaws' Fury", "Caught in the Crossfire"):
            self.assertEqual(db.get(name).unsupported, [], name)

    def test_posse_boss_haste(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        g, a, b = game()
        g.enter_battlefield(a, db.get("Hellspur Posse Boss"))
        rogue, wizard = g.enter_battlefield(a, ROGUE), g.enter_battlefield(a, WIZARD)
        g.settle()
        self.assertTrue(rogue.has("haste"))
        self.assertFalse(wizard.has("haste"))


if __name__ == "__main__":
    unittest.main()

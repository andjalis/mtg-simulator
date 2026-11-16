"""#625: "As long as <condition>, you may cast <kind> spells as though they had flash" and "Any player may cast
<kind> spells as though they had flash" (mtgsim.cx_flash_perm flash_gated)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent
from tests.test_cx_flash_perm import setup
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import card

QUICK = card("Test Quick", "{3}{R}", "Legendary Creature — Human Hero",
             "As long as ~ is tapped, you may cast spells as though they had flash.", 3, 3)
KIANNE = card("Test Kianne", "{2}{G}{U}", "Legendary Creature — Elf Wizard",
              "As long as ~'s power is even, you may cast noncreature spells as though they had flash.\n"
              "As long as ~'s power is odd, you may cast creature spells as though they had flash.", 2, 2)
EQUINOX = card("Test Equinox", "{3}{G}", "Enchantment",
               "Any player may cast creature and enchantment spells as though they had flash.")
SORC = card("Test Sorcery", "{1}", "Sorcery", "Draw a card.")
BEAST = card("Test Beast", "{2}", "Creature — Beast", "", 2, 2)


def castable(game, p, c):
    p.hand.append(c)
    try:
        return game.can_cast_now(p, c)
    finally:
        p.hand.remove(c)


class Gated(unittest.TestCase):
    def test_parse(self):
        for c in (QUICK, KIANNE, EQUINOX):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(len(KIANNE.advanced_rules["flash_gated"]), 2)
        self.assertTrue(EQUINOX.advanced_rules["flash_gated"][0][2])

    def test_refusals(self):
        for text in ("As long as you control a foo, you may cast spells as though they had flash.",
                     "As long as ~ is tapped, you may cast foo spells as though they had flash.",
                     "Any player may cast spells as though they had flash if they control a Forest."):
            c = card("Test Refused", "{2}", "Enchantment", text)
            self.assertTrue(c.unsupported, text)

    def test_tapped_source(self):
        game, a = setup()
        quick = Permanent(QUICK, a)
        a.battlefield.append(quick)
        self.assertFalse(castable(game, a, SORC))
        quick.tapped = True
        self.assertTrue(castable(game, a, SORC))

    def test_power_parity(self):
        game, a = setup()
        kianne = Permanent(KIANNE, a)
        a.battlefield.append(kianne)
        self.assertTrue(castable(game, a, SORC))             # power 2: noncreature spells
        self.assertFalse(castable(game, a, BEAST))
        kianne.counters["+1/+1"] = 1                          # power 3: creature spells
        self.assertFalse(castable(game, a, SORC))
        self.assertTrue(castable(game, a, BEAST))

    def test_any_player(self):
        game, a = setup()
        b = game.opponent(a)
        b.battlefield.append(Permanent(EQUINOX, b))           # the opponent's Equinox works for a too
        self.assertTrue(castable(game, a, BEAST))
        self.assertFalse(castable(game, a, SORC))

    def test_cast_on_the_opponents_turn(self):
        game, a = setup()
        a.battlefield.append(Permanent(EQUINOX, a))
        bear = card("Test Bear", "{1}", "Creature — Bear", "", 2, 2)
        a.hand.append(bear)
        self.assertTrue(game.can_cast_now(a, bear))
        self.assertTrue(game.cast(a, bear))
        game.settle()
        self.assertIn("Test Bear", [x.card.name for x in a.battlefield])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Quicksilver, Speedster", "Kianne, Corrupted Memory", "Tidal Barracuda", "Vernal Equinox",
                     "Quick Sliver"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()

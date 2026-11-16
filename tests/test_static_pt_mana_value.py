"""#520: static group animation with base power and toughness each equal to its mana value (Opalescence), also
behind an "as long as" gate (Starfield of Nyx)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card

OPAL = card("Test Opal", "{2}{W}{W}", "Enchantment", "Each other non-Aura enchantment is a creature in addition to its "
            "other types and has base power and base toughness each equal to its mana value.")
STAR = card("Test Star", "{2}{W}", "Enchantment", "As long as you control five or more enchantments, each other "
            "non-Aura enchantment you control is a creature in addition to its other types and has base power and "
            "base toughness each equal to its mana value.")
AURA = card("Test Aura", "{1}{W}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1.")


def ench(name, n):
    return card(name, "{%d}{W}" % (n - 1), "Enchantment", "")


def game():
    a, b = Player("a", [ISLAND] * 10, HeuristicAI()), Player("b", [ISLAND] * 10, HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    for p in (a, b):
        p.library = [ISLAND] * 20
    return g, a, b


class Parse(unittest.TestCase):
    def test_full(self):
        self.assertEqual(OPAL.unsupported, [])
        spec, ops = OPAL.advanced_rules["cx_chars@group"][0]
        self.assertEqual(ops, (("add_types", ("Creature",)), ("set_base", "mv", "mv")))
        self.assertEqual(STAR.unsupported, [])
        self.assertEqual(STAR.advanced_rules["gated"][0][3][:2], ("rule", "cx_chars"))

    def test_refused(self):
        for text in ("Each noncreature artifact is an artifact creature with power and toughness each equal to its "
                     "mana value.",                         # changes its own group (rule 613.6): not yet
                     "Each other enchantment is a creature in addition to its other types and has base power and base "
                     "toughness each equal to its power."):
            self.assertTrue(card("Test Static", "{3}", "Enchantment", text).unsupported, text)


class Engine(unittest.TestCase):
    def test_opalescence(self):
        g, a, b = game()
        theirs = g.enter_battlefield(b, ench("Glory", 3))
        opal = g.enter_battlefield(a, OPAL)
        g.settle()
        self.assertTrue(theirs.is_creature)
        self.assertEqual((theirs.power, theirs.toughness), (3, 3))
        self.assertFalse(opal.is_creature)                       # "each other"
        late = g.enter_battlefield(a, ench("Late", 5))
        g.settle()
        self.assertEqual((late.power, late.toughness), (5, 5))
        g.leave_battlefield(opal, "graveyard")
        g.settle()
        self.assertFalse(theirs.is_creature or late.is_creature)

    def test_aura_and_zero_mana_value(self):
        g, a, b = game()
        g.enter_battlefield(a, OPAL)
        bear = g.enter_battlefield(a, card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2))
        g._aura_host = bear
        aura = g.enter_battlefield(a, AURA)
        g._aura_host = None
        zero = g.enter_battlefield(a, card("Zero", "", "Enchantment", ""))
        g.settle()
        self.assertFalse(aura.is_creature)                       # non-Aura
        self.assertNotIn(zero, a.battlefield)                    # a 0/0 creature dies

    def test_starfield_gate(self):
        g, a, b = game()
        g.enter_battlefield(a, STAR)
        mine = [g.enter_battlefield(a, ench(f"E{n}", n)) for n in (2, 3, 4)]
        theirs = g.enter_battlefield(b, ench("Theirs", 3))
        g.settle()
        self.assertFalse(any(e.is_creature for e in mine))      # four enchantments
        fifth = g.enter_battlefield(a, ench("E5", 5))
        g.settle()
        self.assertEqual([(e.power, e.toughness) for e in mine + [fifth]], [(2, 2), (3, 3), (4, 4), (5, 5)])
        self.assertFalse(theirs.is_creature)                     # "you control"
        g.leave_battlefield(fifth, "graveyard")
        g.settle()
        self.assertFalse(any(e.is_creature for e in mine))


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class Cards(unittest.TestCase):
    def test_real(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Opalescence", "Starfield of Nyx"):
            self.assertEqual(db.get(name).unsupported, [], name)
        self.assertTrue(db.get("March of the Machines").unsupported)


if __name__ == "__main__":
    unittest.main()

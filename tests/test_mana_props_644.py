"""#644: restricted mana by spell property (mtgsim.cx_abil_mana._PROPERTIES): mana value 5 or greater or {X} in the
cost, one or more colors without {X}, devoid, and "a legendary spell, and that spell can't be countered"."""
import random
import unittest
from pathlib import Path

from mtgsim import cx_abil_mana as M
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Delighted Halfling", "Troyan, Gutsy Explorer")
TROYAN = card("Test Troyan", "{2}", "Creature — Human", "{T}: Add {C}. Spend this mana only to cast spells with mana "
              "value 5 or greater or spells with {X} in their mana costs.", 1, 1)
NEST = card("Test Nest", "{1}", "Artifact", "{T}: Add {C}. Spend this mana only to cast a spell that's one or more "
                                            "colors without {X} in its mana cost.")
CROSS = card("Test Cross", "", "Land", "{T}: Add {C}. Spend this mana only to cast a spell with devoid.")
HALFLING = card("Test Halfling", "{G}", "Creature — Halfling", "{T}: Add {C}. Spend this mana only to cast a legendary "
                "spell, and that spell can't be countered.", 1, 1)
BIG = card("Test Big", "{4}{G}", "Creature — Beast", "", 5, 5)
SMALL = card("Test Small", "{1}{G}", "Creature — Bear", "", 2, 2)
XSPELL = card("Test Blaze", "{X}{R}", "Sorcery", "Test Blaze deals X damage to any target.")
ART = card("Test Rock", "{2}", "Artifact", "{T}: You gain 1 life.")
DEVOID = card("Test Scion", "{1}{B}", "Creature — Eldrazi", "Devoid", 2, 1)
HERO = card("Test Hero", "{1}", "Legendary Creature — Human", "", 2, 2)


def game():
    a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 2, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


def ready(g, p, c):
    perm = g.enter_battlefield(p, c)
    perm.sick = False
    return perm


class Parse(unittest.TestCase):
    def test_codes(self):
        for c in (TROYAN, NEST, CROSS, HALFLING):
            self.assertEqual(c.unsupported, [], c.name)
            self.assertTrue(c.mana_restriction.startswith("pred:"), c.name)
        self.assertTrue(M.uncounterable(HALFLING.mana_restriction))
        self.assertFalse(M.uncounterable(TROYAN.mana_restriction))

    def test_refusals(self):
        for text in ("to cast spells with mana value 4 or less", "to cast a spell with flying",
                     "to cast a legendary spell, and that spell can't be copied"):
            self.assertIsNone(M.parse(text), text)


class Pay(unittest.TestCase):
    def test_properties(self):
        g, a, b = game()
        troyan, nest, cross = (ready(g, a, c) for c in (TROYAN, NEST, CROSS))
        cases = {troyan: {BIG: True, XSPELL: True, SMALL: False},
                 nest: {SMALL: True, XSPELL: False, ART: False},
                 cross: {DEVOID: True, SMALL: False}}
        for src, spells in cases.items():
            for spell, want in spells.items():
                self.assertEqual(g.mana_allowed(src, spell), want, (src.card.name, spell.name))

    def test_halfling_mana_makes_the_legend_uncounterable(self):
        for paid_with_halfling in (True, False):
            g, a, b = game()
            if paid_with_halfling:
                ready(g, a, HALFLING)
            else:
                ready(g, a, card("Test Wastes", "", "Land", "{T}: Add {C}."))
            seen = []

            class Recording(list):
                def append(self, x):
                    seen.append(x)
                    super().append(x)
            g.stack = Recording(g.stack)
            a.hand = [HERO]
            self.assertTrue(g.cast(a, HERO, None))
            item = next(x for x in seen if isinstance(x, StackItem) and x.card and x.card.name == HERO.name)
            self.assertEqual(bool(getattr(item, "uncounterable", False)), paid_with_halfling)

    def test_halfling_mana_cannot_cast_a_nonlegendary_spell(self):
        g, a, b = game()
        ready(g, a, HALFLING)
        a.hand = [ART]
        self.assertFalse(g.spell_payable(a, ART))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in FULL:
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)


if __name__ == "__main__":
    unittest.main()

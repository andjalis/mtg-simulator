"""A bare "{T}: Add <mana>" line must make mana or leave the card unsupported (it used to make nothing and count as full)."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

BARE = ("{T}: Add two mana of any one color.", "{T}: Add three mana of any one color.",
        "{T}: Add two mana of different colors.", "{T}: Add two mana in any combination of colors.",
        "{T}: Add one mana of any type that a land you control could produce.",
        "{T}: Add X mana of any one color, where X is ~'s power.", "{T}: Add {∞}.",
        "{T}: Add one mana of any of the exiled cards' colors.")


class BareMana(unittest.TestCase):
    def test_never_full_and_silent(self):
        for text in BARE:
            with self.subTest(text=text):
                c = card("Test Rock", "{2}", "Artifact", text)
                makes_mana = bool(c.produces) or any(e.kind == "add_mana" for a in c.activated for e in a.effects)
                self.assertTrue(makes_mana or c.unsupported, text)
                if c.unsupported:
                    self.assertIn(text.replace("~", "this"), " ".join(c.unsupported).replace("~", "this"))

    def test_three_of_one_color_is_added_and_spendable(self):
        rock = card("Test Lotus", "{2}", "Artifact", "{T}: Add three mana of any one color.")
        self.assertEqual(rock.unsupported, [])
        self.assertEqual(rock.produces, frozenset())
        a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 2, "main1"
        a.library = b.library = [ISLAND] * 10
        perm = game.enter_battlefield(a, rock)
        perm.sick = False
        self.assertTrue(game.activate_ability(a, perm, 0))
        game.settle()
        self.assertEqual(len(a.pool), 3)
        self.assertEqual(len({next(iter(m.card.produces)) for m in a.pool}), 1)
        self.assertTrue(game.can_pay(a, {"generic": 3}))          # the floating mana pays
        self.assertIsNotNone(game.pay(a, {"generic": 3}))


if __name__ == "__main__":
    unittest.main()

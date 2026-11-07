"""A bare "{T}: Add <mana>" line must make mana or leave the card unsupported (it used to make nothing and count as full)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
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

    def test_three_of_one_color_is_a_real_mana_source(self):
        rock = card("Test Lotus", "{5}", "Artifact", "{T}: Add three mana of any one color.")
        self.assertEqual(rock.unsupported, [])
        self.assertEqual(rock.mana_amount, 3)
        self.assertEqual(len(rock.produces), 5)
        self.assertTrue(any("any combination" in x for x in rock.approximations))      # simplified, not full
        game, a, _ = self.game()
        perm = game.enter_battlefield(a, rock)
        perm.sick = False
        self.assertTrue(game.can_pay(a, {"generic": 2, "U": 1}))        # three mana, one of them blue
        self.assertIsNotNone(game.pay(a, {"generic": 2, "U": 1}))
        self.assertTrue(perm.tapped)

    def test_heuristic_ai_casts_off_the_rock(self):
        rock = card("Test Lotus", "{5}", "Artifact", "{T}: Add three mana of any one color.")
        draw = card("Test Divination", "{2}{U}", "Sorcery", "Draw two cards.")
        game, a, _ = self.game(HeuristicAI)
        game.enter_battlefield(a, rock).sick = False
        a.hand = [draw]
        a.ai.main_phase(game, a)
        self.assertIn(draw, a.graveyard)
        self.assertEqual(len(a.hand), 2)

    def test_combination_is_exact(self):
        rock = card("Test Rock", "{2}", "Artifact", "{T}: Add two mana in any combination of colors.")
        self.assertEqual(rock.unsupported, [])
        self.assertFalse(any("any combination" in x for x in rock.approximations))

    @staticmethod
    def game(ai=Scripted):
        a, b = Player("a", [], ai()), Player("b", [], ai())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 2, "main1"
        a.library = b.library = [ISLAND] * 10
        return game, a, b


if __name__ == "__main__":
    unittest.main()

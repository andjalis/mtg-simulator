"""#714: an Aura's "at the beginning of the upkeep of enchanted <permanent>'s controller" trigger fires once."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def enchant(self, aura_card, host):
        aura = self.game.enter_battlefield(self.a, aura_card)
        aura.aura_host = host
        host.auras.append(aura)
        return aura

    def upkeep(self, p):
        self.game.begin_upkeep(p)
        self.game.settle()

    def triggers(self, name):
        return sum(1 for e in self.game.events if e.endswith(f"{name} trigger goes on the stack"))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def card(self, name):
        from mtgsim.carddb import CardDB
        return CardDB().get(name)

    def test_power_taint_once(self):
        charm = self.game.enter_battlefield(self.b, card("Test Charm", "{3}", "Enchantment", ""))
        self.enchant(self.card("Power Taint"), charm)
        self.upkeep(self.b)
        self.assertEqual(self.triggers("Power Taint"), 1)
        self.assertEqual(self.b.life, 18)

    def test_cursed_land_once(self):
        land = self.game.enter_battlefield(self.b, card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)"))
        self.enchant(self.card("Cursed Land"), land)
        self.upkeep(self.b)
        self.assertEqual(self.triggers("Cursed Land"), 1)
        self.assertEqual(self.b.life, 19)

    def test_not_on_the_auras_controllers_upkeep(self):
        charm = self.game.enter_battlefield(self.b, card("Test Charm", "{3}", "Enchantment", ""))
        self.enchant(self.card("Power Taint"), charm)
        self.upkeep(self.a)
        self.assertEqual(self.b.life, 20)


class OlderTemplate(Base):
    def test_that_player_loses_life_once(self):
        """batch1_templates' own host_lose kind still fires (once) from its dispatcher."""
        aura = card("Test Curse", "{B}", "Enchantment — Aura", "Enchant creature\nAt the beginning of the upkeep of "
                    "enchanted creature's controller, that player loses 1 life.")
        self.assertEqual(aura.unsupported, [])
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.enchant(aura, bear)
        self.upkeep(self.b)
        self.assertEqual(self.b.life, 19)


if __name__ == "__main__":
    unittest.main()

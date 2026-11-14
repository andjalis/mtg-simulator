"""#361: an Aura's or Equipment's trigger for its creature ("Whenever enchanted creature is dealt damage, its
controller creates that many ... tokens") gets the event's amount, like the permanent's own triggers do."""
import random
import unittest

from mtgsim import auras

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import PLAINS, card

CALL = card("Test Call", "{1}{G}", "Enchantment — Aura",
            "Enchant creature\nWhenever enchanted creature is dealt damage, its controller creates that many 1/1 "
            "green Squirrel creature tokens.")


def setup(host_side):
    a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [PLAINS] * 10
    owner = b if host_side == "theirs" else a
    host = g.enter_battlefield(owner, card("Host", "{3}", "Creature — Ogre", "", 4, 4))
    aura = g.enter_battlefield(a, CALL)
    auras.attach(g, aura, host)
    g.settle()
    return g, a, b, host


def squirrels(p):
    return sum(1 for x in p.battlefield if x.is_creature and "Squirrel" in x.card.subtypes)


class HostTriggerThatMuch(unittest.TestCase):
    def test_parsed_as_host_trigger(self):
        self.assertTrue(CALL.host_triggers[0].effects[0].data.get("that_much"))

    def test_my_creature(self):
        g, a, b, host = setup("mine")
        g.deal_damage(host, 3, by=b)
        g.settle()
        self.assertEqual((squirrels(a), squirrels(b)), (3, 0))

    def test_their_creature_gives_its_controller_the_tokens(self):
        g, a, b, host = setup("theirs")
        g.deal_damage(host, 2, by=a)
        g.settle()
        self.assertEqual((squirrels(a), squirrels(b)), (0, 2))

    def test_damage_from_a_permanent_still_names_the_creatures_controller(self):
        g, a, b, host = setup("theirs")
        shooter = g.enter_battlefield(a, card("Shooter", "{1}", "Creature — Human", "", 1, 1))
        g.deal_damage(host, 2, by=a, source=shooter)
        g.settle()
        self.assertEqual((squirrels(a), squirrels(b)), (0, 2))


if __name__ == "__main__":
    unittest.main()

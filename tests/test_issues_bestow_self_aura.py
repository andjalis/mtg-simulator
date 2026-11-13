"""Issue 285 follow-up: "~ gets +1/+0. If it's an Aura, enchanted creature gets +1/+0 instead." (Everflame Eidolon).

"it" is the object of the sentence before, ~ itself; it used to be read as the previous effect's target, which a
self pump doesn't have, so a bestowed Eidolon pumped itself (an Aura) instead of the enchanted creature."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import MOUNTAIN, card

TEXT = ("Bestow {2}{R}\n{R}: Everflame Eidolon gets +1/+0 until end of turn. If it's an Aura, enchanted creature gets "
        "+1/+0 until end of turn instead.\nEnchanted creature gets +1/+1.")


def eidolon():
    return card("Everflame Eidolon", "{1}{R}", "Enchantment Creature — Spirit", TEXT, 1, 1)


def game():
    a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 2, "main1"
    a.library = b.library = [MOUNTAIN] * 10
    for _ in range(6):
        g.enter_battlefield(a, MOUNTAIN).sick = False
    g.settle()
    return g, a


class ItsAnAuraIsTheSource(unittest.TestCase):
    def test_parse_reads_the_source(self):
        conds = [e.cond for e in eidolon().activated[0].effects]
        self.assertTrue(all("src_is" in c and "prev_is" not in c for c in conds), conds)

    def test_bestowed_pumps_the_enchanted_creature(self):
        g, a = game()
        host = g.enter_battlefield(a, card("Test Host", "{1}", "Creature — Human", "", 1, 1))
        g.settle()
        a.hand.append(eidolon())
        g.cast(a, next(v for v in g.spell_options(a) if g._origin(v)[1] == "bestow"))
        g.settle()
        aura = next(x for x in a.battlefield if x.card.name.startswith("Everflame"))
        self.assertFalse(aura.is_creature)
        self.assertEqual((host.power, host.toughness), (2, 2))
        self.assertTrue(g.activate(a, aura, "ability:0"))
        g.settle()
        self.assertEqual((host.power, host.toughness), (3, 2))

    def test_creature_pumps_itself(self):
        g, a = game()
        me = g.enter_battlefield(a, eidolon())
        g.settle()
        self.assertTrue(g.activate(a, me, "ability:0"))
        g.settle()
        self.assertEqual(me.power, 2)


if __name__ == "__main__":
    unittest.main()

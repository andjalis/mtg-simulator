"""Tiered spells (choose one mode and its extra cost), attaching Equipment you control to a creature (Thorin,
Blacksmith's Talent), and "return target spell or permanent" read as a permanent."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

FIRE = card("Test Fire Magic", "{R}", "Sorcery", "Tiered\n• Fire — {0} — ~ deals 1 damage to each creature.\n"
                                                 "• Fira — {2} — ~ deals 2 damage to each creature.\n"
                                                 "• Firaga — {5} — ~ deals 3 damage to each creature.")
THORIN = card("Test Thorin", "{3}{R}", "Legendary Creature — Dwarf Noble",
              "Trample\nWhen ~ enters, attach any number of target Equipment you control to target creature you control. "
              "When one or more Equipment become attached to that creature this way, that creature deals damage equal "
              "to its power to up to one target creature.", 3, 4)
BLADE = card("Test Blade", "{1}", "Artifact — Equipment", "Equipped creature gets +2/+0.\nEquip {2}")
HELM = card("Test Helm", "{1}", "Artifact — Equipment", "Equipped creature gets +0/+2.\nEquip {2}")
REVEAL = card("Test Revelation", "{4}{U}{R}{W}", "Sorcery", "Return target spell or permanent to its owner's hand.")


class TieredGear(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c, n=1):
        for _ in range(n):
            perm = self.game.enter_battlefield(who, c)
            perm.sick = False
        self.game.settle()
        return perm

    def test_templates(self):
        for c in (FIRE, THORIN, REVEAL):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(REVEAL.approximations, ["returns a nonland permanent, not a spell"])

    def test_tiered_offers_one_mode_at_a_time(self):
        self.put(self.a, MOUNTAIN, 3)
        self.a.hand[:] = [FIRE]
        options = [o for o in self.game.spell_options(self.a) if self.game._origin(o)[1].startswith("spree_")]
        self.assertEqual(sorted(sum(o.mana_cost.values()) for o in options), [1, 3, 6])
        fira = next(o for o in options if sum(o.mana_cost.values()) == 3)
        bear = self.put(self.b, BEAR)
        self.assertTrue(self.game.cast(self.a, fira))
        self.game.settle()
        self.assertNotIn(bear, self.b.battlefield)

    def test_thorin_attaches_everything_then_strikes(self):
        blade, helm = self.put(self.a, BLADE), self.put(self.a, HELM)
        bear = self.put(self.b, BEAR)
        thorin = self.put(self.a, THORIN)
        self.assertIs(blade.attached_to, thorin)
        self.assertIs(helm.attached_to, thorin)
        self.assertEqual((thorin.power, thorin.toughness), (5, 6))
        self.assertNotIn(bear, self.b.battlefield)


if __name__ == "__main__":
    unittest.main()

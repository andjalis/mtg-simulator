"""Coverage batch: subtype and combat-state pump targets, keyword counters on your creatures, Rule of Law, player
hexproof, opponents' creatures entering tapped, attack-count triggers, Timetwister, subtype token statics,
"other creatures with flying" anthems and mana granted by Equipment and Auras."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

UNDORAK = card("Test Undorak", "{2}{G}{G}", "Creature — Beast", "{2}{G}: Target Beast creature gets +1/+1 until end of "
               "turn.", 3, 3)
RIGHTEOUS = card("Test Righteousness", "{W}", "Instant", "Target blocking creature gets +7/+7 until end of turn.")
REX = card("Test Rex", "{7}{G}", "Creature — Dinosaur", "When ~ enters, put a trample counter on target creature you "
           "control.", 11, 11)
KNIGHTLY = card("Test Venerable", "{W}", "Creature — Human Knight", "When ~ dies, put a +1/+1 counter on target Knight you "
                "control.", 2, 1)
KNIGHT = card("Test Knight", "{W}", "Creature — Human Knight", "", 2, 2)
LAW = card("Test Law", "{2}{W}", "Enchantment", "Each player can't cast more than one spell each turn.")
LEYLINE = card("Test Leyline", "{2}{W}{W}", "Enchantment", "You have hexproof.")
SOVEREIGN = card("Test Sovereign", "{1}{W}", "Creature — Human Soldier", "Creatures your opponents control enter tapped.", 2, 1)
INTEL = card("Test Intel", "{2}{U}", "Enchantment", "Whenever you attack with two or more creatures, draw a card.")
TWISTER = card("Test Twister", "{2}{U}", "Sorcery", "Each player shuffles their hand and graveyard into their library, then "
               "draws seven cards.")
SKYLORD = card("Test Skylord", "{3}{U}", "Creature — Zombie Wizard", "Zombie tokens you control have flying.", 3, 3)
WYVERN = card("Test Wyvern", "{2}{W}{U}", "Creature — Drake", "Flying\nOther creatures you control with flying get +1/+1.", 2, 3)
MANTLE = card("Test Mantle", "{0}", "Artifact — Equipment", "Equipped creature has \"{T}: Add one mana of any color.\"\n"
              "Equip {1}")
SPIES = card("Test Spies", "{2}{U}", "Creature — Human Rogue", "When ~ enters, look at target opponent's hand.", 2, 2)
CARRIAGE = card("Test Carriage", "{4}", "Artifact Creature — Construct", "Trample\nWhen ~ attacks or blocks, sacrifice it at "
                "end of combat.", 5, 6)
ALL = (UNDORAK, RIGHTEOUS, REX, KNIGHTLY, LAW, LEYLINE, SOVEREIGN, INTEL, TWISTER, SKYLORD, WYVERN, MANTLE, SPIES, CARRIAGE)


class CoverageBatch7(unittest.TestCase):
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
        for c in ALL:
            self.assertEqual(c.unsupported, [], c.name)

    def test_subtype_and_blocking_targets(self):
        beast, bear = self.put(self.a, UNDORAK), self.put(self.a, BEAR)
        eff = UNDORAK.activated[0].effects[0]
        self.assertEqual(self.game.legal_targets(self.a, eff), [beast])
        self.game.blocks = {self.put(self.b, BEAR): [bear]}
        self.assertEqual(self.game.legal_targets(self.a, RIGHTEOUS.spell_effects[0]), [bear])
        knight, _ = self.put(self.a, KNIGHT), self.put(self.a, BEAR)
        self.assertEqual(self.game.legal_targets(self.a, KNIGHTLY.triggers[0].effects[0]), [knight])
        self.game.resolve(self.a, REX.triggers[0].effects[0], bear)
        self.assertTrue(bear.has("trample"))

    def test_rule_of_law(self):
        self.put(self.b, LAW)
        bolt = card("Test Bolt", "{0}", "Instant", "Draw a card.")
        self.a.hand[:] = [bolt, bolt]
        self.assertTrue(self.game.can_cast_now(self.a, bolt))
        self.game.spells_cast = {"turn": self.game.turn, self.a.name: 1}
        self.assertFalse(self.game.can_cast_now(self.a, bolt))

    def test_player_hexproof_and_enter_tapped(self):
        self.put(self.a, LEYLINE)
        self.assertFalse(self.game.targetable(self.a, self.b))
        self.assertTrue(self.game.targetable(self.a, self.a))
        self.put(self.a, SOVEREIGN)
        self.assertTrue(self.game.enter_battlefield(self.b, BEAR).tapped)
        self.assertFalse(self.game.enter_battlefield(self.a, BEAR).tapped)

    def test_attack_count_trigger(self):
        trig = INTEL.triggers[0]
        self.assertEqual((trig.event, trig.filter), ("you_attack", "count>=2"))
        self.put(self.a, INTEL)
        self.game.attackers = [self.put(self.a, BEAR)]
        self.game.fire(self.a, "you_attack")
        self.game.settle()
        self.assertEqual(len(self.a.hand), 0)
        self.game.attackers.append(self.put(self.a, BEAR))
        self.game.fire(self.a, "you_attack")
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_timetwister(self):
        self.a.hand[:] = [BEAR]
        self.a.graveyard[:] = [BEAR, BEAR]
        self.game.resolve(self.a, TWISTER.spell_effects[0], None)
        self.assertEqual((len(self.a.hand), len(self.a.graveyard), len(self.a.library)), (7, 0, 16))
        self.assertEqual(len(self.b.hand), 7)

    def test_statics_and_mana(self):
        wyvern = self.put(self.a, WYVERN)
        flier = self.put(self.a, card("Test Bird", "{W}", "Creature — Bird", "Flying", 1, 1))
        self.assertEqual((wyvern.power, flier.power), (2, 2))
        bear = self.put(self.a, BEAR)
        mantle = self.put(self.a, MANTLE)
        mantle.attached_to = bear
        self.assertEqual(bear.granted_mana(), frozenset("WUBRG"))


if __name__ == "__main__":
    unittest.main()

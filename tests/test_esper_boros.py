"""Esper and Boros Dwarves pool gaps: "its controller draws a card", connive X, Equipment tokens (attached when
created), hone counters, equipped attackers gaining a keyword, exile instead of a graveyard, and "one or more
creature cards are put into graveyards"."""
import random
import unittest

from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

ERTAI_COUNTER = card("Test Rebuff", "{1}{U}", "Instant", "Counter target spell, activated ability, or triggered ability. "
                                                         "Its controller draws a card.")
ERTAI_KILL = card("Test Ruin", "{1}{B}", "Instant", "Destroy another target creature or planeswalker. Its controller "
                                                    "draws a card.")
RAFFINE = card("Test Raffine", "{1}{W}{U}{B}", "Legendary Creature — Sphinx Demon",
               "Flying, ward {1}\nWhenever you attack, target attacking creature connives X, where X is the number of "
               "attacking creatures.", 1, 4)
DAIN = card("Test Dain", "{2}{R}{W}", "Legendary Creature — Dwarf Noble",
            'When ~ enters, create a colorless Equipment artifact token named Axe with "Equipped creature gets +1/+0" '
            "and equip {2}. When you do, attach it to target creature you control.\nWhenever ~ attacks, each equipped "
            "attacking creature gains double strike until end of turn.", 3, 3)
MABEL = card("Test Mabel", "{2}{R}{W}", "Legendary Creature — Mouse Soldier",
             "When ~ enters, create Cragflame, a legendary colorless Equipment artifact token with \"Equipped creature "
             'gets +1/+1 and has vigilance, trample, and haste" and equip {2}.', 3, 3)
DWALIN = card("Test Dwalin", "{1}{R}{W}", "Legendary Creature — Dwarf Warrior",
              "First strike\nWhenever ~ enters or attacks, put a hone counter on each Equipment you control.", 2, 2)
APPARITION = card("Test Apparition", "{1}{W}{U}", "Creature — Spirit",
                  "Flying\nWhenever one or more creature cards are put into graveyards from anywhere, investigate. This "
                  "ability triggers only once each turn.\nIf ~ would be put into a graveyard from anywhere, exile it "
                  "instead.", 2, 2)
TENTACLES = card("Test Tentacles", "{1}", "Artifact — Equipment",
                 "Whenever a creature you control with mana value 5 or greater enters, you may attach this Equipment to "
                 "it.\nEquipped creature gets +4/+4.\nEquip {5}")
GIANT = card("Test Giant", "{5}", "Creature — Giant", "", 5, 5)
SHOCK = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to any target.")


class EsperBoros(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def test_templates(self):
        for c in (TENTACLES, ERTAI_COUNTER, ERTAI_KILL, RAFFINE, DAIN, MABEL, DWALIN, APPARITION):
            self.assertEqual(c.unsupported, [], c.name)

    def test_its_controller_draws(self):
        item = StackItem(self.b, list(SHOCK.spell_effects), [self.a], card=SHOCK, kind="spell")
        self.game.stack.append(item)
        hand = len(self.b.hand)
        mine = StackItem(self.a, list(ERTAI_COUNTER.spell_effects), [item, None], card=ERTAI_COUNTER, kind="spell")
        self.game.stack.append(mine)
        self.game.settle()
        self.assertNotIn(item, self.game.stack)
        self.assertEqual(len(self.b.hand), hand + 1)
        bear = self.put(self.b, BEAR)
        self.game.stack.append(StackItem(self.a, list(ERTAI_KILL.spell_effects), [bear, None], card=ERTAI_KILL,
                                         kind="spell"))
        self.game.settle()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(len(self.b.hand), hand + 2)

    def test_connive_per_attacker(self):
        raffine = self.put(self.a, RAFFINE)
        bears = [self.put(self.a, BEAR), self.put(self.a, BEAR)]
        self.a.hand[:] = [BEAR, BEAR, BEAR]
        self.a.ai.attack = [raffine] + bears
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(sum(x.p1 for x in [raffine] + bears), 3)   # three nonland cards discarded

    def test_equipment_token_attached_and_double_strike(self):
        dain = self.put(self.a, DAIN)
        axe = next(x for x in self.a.battlefield if x.card.name == "Axe token")
        self.assertIs(axe.attached_to, dain)
        self.assertEqual(dain.power, 4)
        self.a.ai.attack = [dain]
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(self.b.life, 12)                           # 4 power, double strike

    def test_legendary_equipment_token_keywords(self):
        self.put(self.a, MABEL)
        crag = next(x for x in self.a.battlefield if x.card.name == "Cragflame token")
        self.assertTrue(crag.card.legendary)
        bear = self.put(self.a, BEAR)
        crag.attached_to = bear
        self.assertTrue(bear.has("haste") and bear.has("trample"))
        self.assertEqual((bear.power, bear.toughness), (3, 3))

    def test_attach_to_the_creature_that_entered(self):
        tentacles = self.put(self.a, TENTACLES)
        self.put(self.a, BEAR)
        self.assertIsNone(tentacles.attached_to)
        giant = self.put(self.a, GIANT)
        self.assertIs(tentacles.attached_to, giant)
        self.assertEqual(giant.power, 9)

    def test_hone_counters(self):
        self.put(self.a, DAIN)
        self.put(self.a, DWALIN)
        dain = next(x for x in self.a.battlefield if x.card.name == DAIN.name)
        self.assertEqual(dain.power, 5)                             # 3 + Axe's 1 + a hone counter

    def test_exiled_instead_and_creature_cards_dying(self):
        ghost = self.put(self.a, APPARITION)
        self.put(self.b, BEAR)
        self.put(self.b, BEAR)
        for bear in list(self.b.creatures):
            self.game.destroy(bear)
        self.game.settle()
        self.assertEqual(sum(1 for x in self.a.battlefield if x.card.token_kind == "clue"), 1)   # once each turn
        self.game.destroy(ghost)
        self.game.settle()
        self.assertIn(APPARITION.name, [c.name for c in self.a.exile])
        self.assertNotIn(APPARITION.name, [c.name for c in self.a.graveyard])


if __name__ == "__main__":
    unittest.main()

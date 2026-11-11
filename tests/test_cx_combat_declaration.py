"""Declaration-time restrictions use the creatures actually attacking/blocking."""
import os
import random
import unittest

from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player
from mtgsim.batch1_templates import drop_solo, drop_solo_blocks
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class CombatDeclaration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0))
        self.g.turn, self.g.step = 3, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def put(self, c=BEAR, p=None):
        if isinstance(c, str):
            c = self.db.get(c)
        perm = self.g.enter_battlefield(p or self.a, c)
        perm.sick = False
        return perm

    def test_real_oracle_clauses_are_consumed(self):
        for name in ("Orcish Conscripts", "Okk", "Scarred Puma"):
            with self.subTest(name=name):
                self.assertEqual(self.db.get(name).unsupported, [])
        master = self.db.get("Master of Cruelties")
        self.assertEqual(len(master.unsupported), 1)  # unrelated unblocked trigger stays unmatched
        self.assertNotIn("~ can only attack alone.", master.unsupported)

    def test_conscripts_need_two_declared_companions(self):
        c, b1, b2 = self.put("Orcish Conscripts"), self.put(), self.put()
        self.a.ai.attack = (c, b1)
        self.g.combat(self.a, self.b)
        self.assertEqual(self.g.last_attackers, [b1])
        self.assertFalse(c.tapped)
        b1.tapped = False
        self.a.ai.attack = (c, b1, b2)
        self.g.combat(self.a, self.b)
        self.assertEqual(self.g.last_attackers, [c, b1, b2])

    def test_tapped_companion_is_not_counted(self):
        c, b1, b2 = self.put("Orcish Conscripts"), self.put(), self.put()
        b2.tapped = True
        self.a.ai.attack = (c, b1, b2)
        self.g.combat(self.a, self.b)
        self.assertEqual(self.g.last_attackers, [b1])

    def test_conscripts_count_blockers_across_attackers(self):
        a1, a2, a3 = self.put(), self.put(), self.put()
        c, b1, b2 = self.put("Orcish Conscripts", self.b), self.put(p=self.b), self.put(p=self.b)
        self.a.ai.attack = (a1, a2, a3)
        self.b.ai.block = {a1: [c], a2: [b1], a3: [b2]}
        self.g.combat(self.a, self.b)
        self.assertEqual(self.g.blocks, {a1: [c], a2: [b1], a3: [b2]})

    def test_duplicate_blocker_is_not_an_extra_companion(self):
        a1, a2 = self.put(), self.put()
        c, b = self.put("Orcish Conscripts", self.b), self.put(p=self.b)
        self.assertEqual(drop_solo_blocks({a1: [c, b], a2: [b]}), {a1: [b], a2: [b]})

    def test_okk_needs_strictly_greater_current_power(self):
        okk = self.put("Okk")
        equal = self.put(card("Equal", "{5}", "Creature — Giant", "", 4, 8))
        self.assertEqual(drop_solo([okk, equal]), [equal])
        equal.pump_p = 1
        self.assertEqual(drop_solo([okk, equal]), [okk, equal])
        attacker = self.put(p=self.b)
        self.assertEqual(drop_solo_blocks({attacker: [okk, equal]}), {attacker: [okk, equal]})

    def test_puma_needs_another_black_or_green_attacker(self):
        puma, blue = self.put("Scarred Puma"), self.put(card("Blue", "{U}", power=1, toughness=1))
        self.assertEqual(drop_solo([puma, blue]), [blue])
        green = self.put()
        self.assertEqual(drop_solo([puma, green]), [puma, green])
        puma.card = card("Green Puma", "{G}", text="~ can't attack unless a black or green creature also attacks.",
                         power=2, toughness=2)
        self.assertEqual(drop_solo([puma]), [])  # its own color is insufficient

    def test_only_alone_attack_and_block(self):
        solo = self.put(card("Solo", "{R}", text="~ can only attack alone.\n~ can block only alone.",
                             power=1, toughness=5))
        other, attacker = self.put(), self.put(p=self.b)
        self.assertEqual(solo.card.unsupported, [])
        self.assertEqual(drop_solo([solo]), [solo])
        self.assertEqual(drop_solo([solo, other]), [other])
        self.assertEqual(drop_solo_blocks({attacker: [solo, other]}), {attacker: [other]})
        self.assertEqual(drop_solo_blocks({attacker: [solo]}), {attacker: [solo]})

    def test_removal_cascades_and_rechecks_menace(self):
        okk = self.put("Okk")
        solo = self.put(card("Solo", "{G}", text="~ can only attack alone.", power=5, toughness=5))
        self.assertEqual(drop_solo([okk, solo]), [])
        menace = self.put(card("Test Threat", "{R}", text="Menace", power=2, toughness=2), self.b)
        c, b = self.put("Orcish Conscripts"), self.put()
        self.assertEqual(drop_solo_blocks({menace: [c, b]}), {})

    def test_suppressed_abilities_remove_group_restrictions(self):
        c = self.put("Orcish Conscripts")
        silence = self.put(card("Silence", "{2}", "Enchantment", ""))
        c.silenced_by = silence
        self.assertEqual(drop_solo([c]), [c])


if __name__ == "__main__":
    unittest.main()

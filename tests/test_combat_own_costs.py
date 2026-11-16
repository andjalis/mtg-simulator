"""Attack / block restrictions with a condition or a price the creature's controller pays (#325)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.cx_combat_costs import attack_cost, pay_attackers, pay_blockers
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card


class Parsing(unittest.TestCase):
    def test_refusals(self):
        for text, types in (
                ("~ can't attack unless its controller pays {2}.", "Creature — Beast"),       # ~ with "its controller"
                ("~ can't attack unless you pay {X}.", "Creature — Beast"),
                ("~ can't attack unless you pay {1} for each card in your hand.", "Creature — Beast"),
                ("~ can't attack unless you pay {2} and sacrifice a land.", "Creature — Beast"),
                ("~ can't attack unless there is another Mountain on the battlefield.", "Creature — Beast")):
            with self.subTest(text):
                self.assertTrue(card("Test", "{1}", types, text, 2, 2).unsupported)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class Cards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a, self.b = Player("a", [BEAR] * 10, HeuristicAI()), Player("b", [BEAR] * 10, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0))
        self.g.turn, self.g.step = 3, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 20

    def put(self, c=BEAR, p=None):
        c = self.db.get(c) if isinstance(c, str) else c
        perm = self.g.enter_battlefield(p or self.a, c)
        perm.sick = False
        return perm

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in ("Glacial Crasher", "Harbor Serpent", "Lovestruck Beast // Heart's Desire", "Qal Sisma Behemoth",
                     "Brainwash", "Myr Prototype", "Phyrexian Marauder", "Cowed by Wisdom"):
            with self.subTest(name):
                self.assertEqual(card_coverage(self.db.get(name)).status, "full")

    def test_glacial_crasher_needs_a_mountain_anywhere(self):
        crasher = self.put("Glacial Crasher")
        self.assertFalse(crasher.can_attack())
        self.put(MOUNTAIN, self.b)                      # an opponent's Mountain counts too
        self.assertTrue(crasher.can_attack())

    def test_harbor_serpent_counts_every_island(self):
        serpent = self.put("Harbor Serpent")
        for _ in range(2):
            self.put(ISLAND, self.a)
        for _ in range(2):
            self.put(ISLAND, self.b)
        self.assertFalse(serpent.can_attack())
        self.put(ISLAND, self.b)
        self.assertTrue(serpent.can_attack())

    def test_lovestruck_beast_needs_a_one_one(self):
        beast = self.put("Lovestruck Beast // Heart's Desire")
        self.put(BEAR)
        self.assertFalse(beast.can_attack())
        self.put(card("Test Elf", "{G}", "Creature — Elf", "", 1, 1))
        self.assertTrue(beast.can_attack())

    def test_behemoth_pays_two_to_attack_and_to_block(self):
        beh = self.put("Qal Sisma Behemoth")
        self.assertEqual(attack_cost(self.g, beh, self.b), {"generic": 2})
        self.assertEqual(pay_attackers(self.g, self.a, [beh], {beh: self.b}), [])     # no mana: it stays home
        lands = [self.put(ISLAND) for _ in range(2)]
        self.assertEqual(pay_attackers(self.g, self.a, [beh], {beh: self.b}), [beh])
        self.assertTrue(all(x.tapped for x in lands))
        attacker = self.put(BEAR, self.b)
        self.assertEqual(pay_blockers(self.g, self.a, {attacker: [beh]}), {})        # lands are spent

    def test_brainwash_taxes_the_enchanted_creature_only(self):
        mine, theirs = self.put(BEAR, self.a), self.put(BEAR, self.b)
        brainwash = self.db.get("Brainwash")
        self.assertTrue(brainwash.aura_hostile)
        self.g._aura_host = theirs
        self.g.enter_battlefield(self.a, brainwash)
        self.assertEqual(attack_cost(self.g, theirs, self.a), {"generic": 3})
        self.assertFalse(any(attack_cost(self.g, mine, self.b).values()))

    def test_myr_prototype_pays_per_counter(self):
        myr = self.put("Myr Prototype")
        myr.counters["+1/+1"] = 3
        self.assertEqual(attack_cost(self.g, myr, self.b), {"generic": 3})

    def test_ai_attacks_with_the_behemoth_when_it_can_pay(self):
        beh = self.put("Qal Sisma Behemoth")
        for _ in range(3):
            self.put(ISLAND)
        life = self.b.life
        self.b.library = [ISLAND] * 20
        self.g.take_turn(self.a)
        self.assertEqual(self.b.life, life - beh.power)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class Actions(unittest.TestCase):
    """Non-mana prices paid as the creature is declared (#325 slice 2)."""
    setUpClass = classmethod(lambda cls: setattr(cls, "db", CardDB(offline=True)))

    def setUp(self):
        Cards.setUp(self)

    put = Cards.put

    def test_refusals(self):
        for text in ("~ can't attack unless you sacrifice a Foo-bar of doom.",
                     "~ can't attack unless you return an enchantment you control.",           # no "to ... hand"
                     "~ can't attack unless you tap an untapped creature you control.",
                     "~ can't attack unless you sacrifice a land you control to its owner's hand."):
            with self.subTest(text):
                self.assertTrue(card("Test", "{1}", "Creature — Beast", text, 2, 2).unsupported)

    def test_exalted_dragon_sacrifices_a_land(self):
        dragon = self.put("Exalted Dragon")
        self.assertEqual(pay_attackers(self.g, self.a, [dragon], {dragon: self.b}), [])     # no land: stays home
        lands = [self.put(ISLAND) for _ in range(2)]
        self.assertEqual(pay_attackers(self.g, self.a, [dragon], {dragon: self.b}), [dragon])
        self.assertEqual(sum(x in self.a.battlefield for x in lands), 1)
        self.assertEqual(len(self.a.graveyard), 1)

    def test_floodtide_serpent_returns_an_enchantment(self):
        serpent = self.put("Floodtide Serpent")
        altar = card("Test Altar", "{1}", "Enchantment", "")
        self.assertEqual(pay_attackers(self.g, self.a, [serpent], {serpent: self.b}), [])
        a = self.put(altar)
        self.assertEqual(pay_attackers(self.g, self.a, [serpent], {serpent: self.b}), [serpent])
        self.assertNotIn(a, self.a.battlefield)
        self.assertIn(altar, self.a.hand)

    def test_hollow_warrior_taps_a_creature_that_isnt_declared(self):
        warrior = self.put("Hollow Warrior")
        bear = self.put(BEAR)
        self.assertEqual(pay_attackers(self.g, self.a, [warrior, bear], {warrior: self.b, bear: self.b}), [warrior])
        # the Bear can't both attack and pay: the declaration sheds it, and then it pays for the Warrior
        self.assertTrue(bear.tapped)
        attacker = self.put(BEAR, self.b)
        other = self.put(BEAR)
        self.assertEqual(pay_blockers(self.g, self.a, {attacker: [warrior]}), {attacker: [warrior]})
        self.assertTrue(other.tapped)

    def test_flooded_woodlands_charges_each_green_attacker(self):
        self.put("Flooded Woodlands", self.b)
        bears = [self.put(BEAR), self.put(BEAR)]
        self.put(ISLAND)
        got = pay_attackers(self.g, self.a, bears, {b: self.b for b in bears})
        self.assertEqual(len(got), 1)                                   # one land: one green attacker
        self.assertFalse(any(x.card.is_land for x in self.a.battlefield))

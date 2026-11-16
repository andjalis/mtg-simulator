"""'~ costs {N} less to cast if it targets <description>' (#341): the discount is read from the chosen targets."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import BEAR, ISLAND, card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
KNIGHT = card("Test Knight", "{1}{W}", "Creature — Human Knight", "", 2, 2)


class Parsing(unittest.TestCase):
    def test_shapes_and_refusals(self):
        from mtgsim.cx_static_cost import target_spec
        self.assertEqual(target_spec("a white creature"), ("permanent", {"colors": ["W"], "types_all": ["creature"]}))
        self.assertEqual(target_spec("a blue spell"), ("spell", {"colors": ["U"]}))
        self.assertEqual(target_spec("a creature card with mana value 3 or less")[0], "card")
        self.assertTrue(target_spec("a creature that was dealt damage this turn")[1]["damaged"])
        for s in ("a creature that was dealt damage this turn or a land", "white creatures", "a Foo-ish thing that x"):
            self.assertIsNone(target_spec(s), s)
        c = card("Test", "{3}{B}", "Instant", "This spell costs {3} less to cast if it targets a white creature and "
                 "you control a Swamp.\\nTarget creature gets -4/-4 until end of turn.")
        self.assertTrue(c.unsupported)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class Casting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a, self.b = Player("a", [BEAR] * 10, HeuristicAI()), Player("b", [BEAR] * 10, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0))
        self.g.turn, self.g.step = 3, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 20

    def put(self, c, p):
        x = self.g.enter_battlefield(p, c)
        x.sick = False
        return x

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in ("Whack", "Mystical Dispute", "Bouncer's Beatdown", "Price of Fame", "Ride's End", "Torch Breath",
                     "Out of Air", "Revoke Demise", "Dire Downdraft", "This Town Ain't Big Enough", "Savage Stomp"):
            with self.subTest(name):
                self.assertEqual(card_coverage(self.db.get(name)).status, "full")

    def test_whack_costs_b_only_when_it_targets_a_white_creature(self):
        whack = self.db.get("Whack")
        knight, bear = self.put(KNIGHT, self.b), self.put(BEAR, self.b)
        self.put(SWAMP, self.a)
        self.a.hand.append(whack)
        self.assertTrue(self.g.can_cast_now(self.a, whack))        # some white creature could be targeted
        self.assertTrue(self.g.cast(self.a, whack, [knight]))
        self.assertNotIn(knight, self.b.battlefield)
        self.assertIn(bear, self.b.battlefield)

    def test_no_qualifying_target_full_price(self):
        whack = self.db.get("Whack")
        self.put(BEAR, self.b)
        self.put(SWAMP, self.a)
        self.a.hand.append(whack)
        self.assertFalse(self.g.can_cast_now(self.a, whack))

    def test_a_non_qualifying_choice_is_swapped_when_only_the_discount_pays(self):
        whack = self.db.get("Whack")
        knight, bear = self.put(KNIGHT, self.b), self.put(BEAR, self.b)
        self.put(SWAMP, self.a)
        self.a.hand.append(whack)
        self.assertTrue(self.g.cast(self.a, whack, [bear]))
        self.assertNotIn(knight, self.b.battlefield)               # retargeted at the white creature
        self.assertIn(bear, self.b.battlefield)

    def test_full_price_with_enough_mana_keeps_the_choice(self):
        whack = self.db.get("Whack")
        self.put(KNIGHT, self.b)
        bear = self.put(BEAR, self.b)
        lands = [self.put(SWAMP, self.a) for _ in range(4)]
        self.a.hand.append(whack)
        self.assertTrue(self.g.cast(self.a, whack, [bear]))
        self.assertNotIn(bear, self.b.battlefield)
        self.assertTrue(all(x.tapped for x in lands))               # paid {3}{B}

    def test_bitter_downfall_needs_a_damaged_creature(self):
        downfall = self.db.get("Bitter Downfall")
        bear = self.put(BEAR, self.b)
        for _ in range(downfall.cmc - 3):
            self.put(SWAMP, self.a)
        self.a.hand.append(downfall)
        self.assertFalse(self.g.can_cast_now(self.a, downfall))
        bear.damage = 1
        self.assertTrue(self.g.can_cast_now(self.a, downfall))
        self.assertTrue(self.g.cast(self.a, downfall, [bear]))
        self.assertNotIn(bear, self.b.battlefield)

    def test_mystical_dispute_on_a_blue_spell(self):
        dispute = self.db.get("Mystical Dispute")
        blue = card("Test Blue", "{1}{U}", "Sorcery", "Draw two cards.")
        spell = StackItem(self.b, list(blue.spell_effects), [None], card=blue, name=blue.name)
        self.g.stack.append(spell)
        self.put(ISLAND, self.a)
        self.a.hand.append(dispute)
        self.assertTrue(self.g.cast(self.a, dispute, [spell]))
        self.assertNotIn(spell, self.g.stack)                      # countered (b can't pay {3})
        red = card("Test Red", "{1}{R}", "Sorcery", "Draw two cards.")
        self.g.stack.clear()
        self.g.stack.append(StackItem(self.b, list(red.spell_effects), [None], card=red, name=red.name))
        self.a.hand.append(dispute)
        self.assertFalse(self.g.cast(self.a, dispute, [self.g.stack[-1]]))     # {2}{U} with one Island

    def test_ai_casts_whack_at_the_white_creature(self):
        whack = self.db.get("Whack")
        knight = self.put(KNIGHT, self.b)
        self.put(card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3), self.b)
        self.put(SWAMP, self.a)
        self.a.hand = [whack]
        plan = self.a.ai.plan_spell(self.g, self.a, whack, precombat=True)
        self.assertIsNotNone(plan)
        self.assertTrue(self.g.cast(self.a, whack, plan[1]))      # with one Swamp only the Knight is affordable
        self.assertNotIn(knight, self.b.battlefield)
        self.assertEqual(len(self.b.battlefield), 1)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class Conditions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        Casting.setUp(self)

    def cost(self, name):
        return self.g.cost_of(self.a, self.db.get(name))

    def test_assassins_ink_neither_either_both(self):
        base = self.db.get("Assassin's Ink").mana_cost
        self.assertEqual(self.cost("Assassin's Ink"), base)
        self.g.enter_battlefield(self.a, card("Test Relic", "{2}", "Artifact", ""))
        self.assertEqual(self.cost("Assassin's Ink")["generic"], base["generic"] - 1)
        self.g.enter_battlefield(self.a, card("Test Altar", "{2}", "Enchantment", ""))
        self.assertEqual(self.cost("Assassin's Ink")["generic"], base["generic"] - 2)
        self.assertEqual({k: v for k, v in self.cost("Assassin's Ink").items() if k != "generic"},
                         {k: v for k, v in base.items() if k != "generic"})     # the coloured part stays

    def test_avatar_of_might_boundary(self):
        base = self.db.get("Avatar of Might").mana_cost
        self.g.enter_battlefield(self.a, BEAR)
        for _ in range(4):
            self.g.enter_battlefield(self.b, BEAR)
        self.assertEqual(self.cost("Avatar of Might"), base)                # three more: no
        self.g.enter_battlefield(self.b, BEAR)
        self.assertEqual(self.cost("Avatar of Might")["generic"], max(0, base["generic"] - 6))     # four more

    def test_wolf_or_werewolf(self):
        base = self.db.get("Wolfkin Outcast // Wedding Crasher").mana_cost
        self.assertEqual(self.cost("Wolfkin Outcast // Wedding Crasher"), base)
        self.g.enter_battlefield(self.a, card("Test Werewolf", "{1}{G}", "Creature — Human Werewolf", "", 2, 2))
        self.assertEqual(self.cost("Wolfkin Outcast // Wedding Crasher")["generic"], base["generic"] - 2)


class TempDiscounts(unittest.TestCase):
    """One-shot discounts for a group of spells (#341 slice 2)."""
    def setUp(self):
        self.a, self.b = Player("a", [BEAR] * 10, HeuristicAI()), Player("b", [BEAR] * 10, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0))
        self.g.turn, self.g.step = 3, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 20

    def run_spell(self, text):
        c = card("Test Spell", "{1}", "Sorcery", text)
        self.assertEqual(c.unsupported, [], text)
        for e in c.spell_effects:
            self.g.resolve(self.a, e, None)

    def test_next_dragon_spell_once(self):
        dragon = card("Test Dragon", "{3}{R}", "Creature — Dragon", "Flying", 4, 4)
        self.run_spell("The next Dragon spell you cast costs {2} less to cast.")
        self.assertEqual(self.g.cost_of(self.a, BEAR), BEAR.mana_cost)               # not a Dragon
        self.assertEqual(self.g.cost_of(self.a, dragon)["generic"], 1)
        self.g.turn += 1
        self.assertEqual(self.g.cost_of(self.a, dragon)["generic"], 1)               # no "this turn": it waits
        self.assertEqual(self.g.cost_of(self.b, dragon)["generic"], 3)               # only its caster's
        for _ in range(3):
            self.g.enter_battlefield(self.a, card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)"))
        self.a.hand.append(dragon)
        self.assertTrue(self.g.cast(self.a, dragon))
        self.assertEqual(self.g.cost_of(self.a, dragon)["generic"], 3)               # spent

    def test_this_turn_group_discount(self):
        relic = card("Test Relic", "{3}", "Artifact", "")
        self.run_spell("Artifact spells you cast this turn cost {1} less to cast.")
        self.assertEqual(self.g.cost_of(self.a, relic)["generic"], 2)
        self.assertEqual(self.g.cost_of(self.a, BEAR), BEAR.mana_cost)
        self.g.turn += 1
        self.assertEqual(self.g.cost_of(self.a, relic)["generic"], 3)

    def test_refusals(self):
        for s in ("The next Foo-thing spell an opponent casts costs {1} less to cast.",
                  "The next wibbly spell you cast costs {2} less to cast.",     # matched, group unread: kept
                  "The next Dragon spell you cast costs {X} less to cast, where X is the frobs you wibble."):
            self.assertTrue(card("Test", "{1}", "Sorcery", s).unsupported, s)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class Quantities(unittest.TestCase):
    """'costs {N} less for each <quantity>' readers and {X} one-shots fixed on resolution (#341)."""
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        Casting.setUp(self)

    def generic(self, name, who=None):
        return self.g.cost_of(who or self.a, self.db.get(name)).get("generic", 0)

    def test_hamza_counts_creatures_with_counters(self):
        base = self.generic("Hamza, Guardian of Arashin")
        bears = [self.g.enter_battlefield(self.a, BEAR) for _ in range(3)]
        bears[0].counters["+1/+1"] = 2
        bears[1].counters["+1/+1"] = 1
        self.assertEqual(self.generic("Hamza, Guardian of Arashin"), base - 2)       # two creatures, not 3 counters

    def test_eris_counts_distinct_mana_values(self):
        base = self.generic("Eris, Roar of the Storm")
        self.a.graveyard = [card("I1", "{1}", "Instant", ""), card("I2", "{1}", "Instant", ""),
                            card("S3", "{3}", "Sorcery", ""), BEAR]
        self.assertEqual(self.generic("Eris, Roar of the Storm"), base - 4)          # mana values 1 and 3

    def test_licia_and_delightful_discovery(self):
        base = self.generic("Licia, Sanguine Tribune")
        self.a.life_gained_turn = 3
        self.assertEqual(self.generic("Licia, Sanguine Tribune"), base - 3)
        base = self.generic("Delightful Discovery")
        self.g.spells_cast = {"turn": self.g.turn, self.b.name: 2, self.a.name: 5}
        self.assertEqual(self.generic("Delightful Discovery"), max(0, base - 2))      # only the opponents'

    def test_kaza_fixes_x_on_resolution(self):
        kaza = self.db.get("Kaza, Roil Chaser")
        k = self.g.enter_battlefield(self.a, kaza)
        wizard = card("Test Wizard", "{U}", "Creature — Human Wizard", "", 1, 1)
        self.g.enter_battlefield(self.a, wizard)
        effs = kaza.activated[0].effects
        item = StackItem(self.a, list(effs), [None] * len(effs), source=k)
        for e in effs:
            self.g.resolve(self.a, e, None, item)
        self.g.enter_battlefield(self.a, wizard)                                     # later Wizards don't count
        bolt = card("Test Bolt", "{3}{R}", "Instant", "Draw a card.")
        self.assertEqual(self.g.cost_of(self.a, bolt)["generic"], 1)                # Kaza + 1 Wizard = 2

    def test_draconic_debut_uses_the_x_paid(self):
        debut = self.db.get("Draconic Debut")
        e = next(e for e in debut.spell_effects if e.kind == "cx_temp_cost")
        item = StackItem(self.a, [e], [None], card=debut)
        item.x = 3
        self.g.resolve(self.a, e, None, item)
        dragon = card("Test Dragon", "{4}{R}", "Creature — Dragon", "Flying", 5, 5)
        self.assertEqual(self.g.cost_of(self.a, dragon)["generic"], 1)

"""Spell additional costs with counted, filtered and alternative payments (cx_spell_costs, #342)."""
import os
import random
import unittest

from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.cx_spell_costs import KEY, alternatives, parse_cost
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, SWAMP, card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
MOUNTAIN = card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")
TOKEN_BEAR = card("Test Cub", "{0}", "Creature — Bear", "", 1, 1)
BIG = card("Test Giant", "{5}", "Creature — Giant", "", 5, 5)


class Parse(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(parse_cost("sacrifice two creatures"), ((("sac", 2, {"types": ["creature"]}),),))
        self.assertEqual(parse_cost("sacrifice a creature, discard a card, or pay 4 life"),
                         ((("sac", 1, {"types": ["creature"]}),), (("discard", 1, {}),), (("life", 4, {}),)))
        self.assertEqual(parse_cost("discard a card and sacrifice a creature"),
                         ((("discard", 1, {}), ("sac", 1, {"types": ["creature"]})),))
        self.assertEqual(parse_cost("sacrifice a creature or pay {3}{B}")[1], (("mana", 0, {"generic": 3, "B": 1}),))
        self.assertEqual(parse_cost("tap two untapped artifacts, creatures, and/or lands you control"),
                         ((("tap", 2, {"any": ["artifact", "creature", "land"]}),),))
        self.assertEqual(parse_cost("pay 5 life or sacrifice a creature or enchantment")[1],
                         (("sac", 1, {"any": ["creature", "enchantment"]}),))

    def test_refusals(self):
        for text in ("sacrifice a creature that dealt damage this turn", "sacrifice half the lands you control",
                     "behold a Goblin", "behold a Goblin and sacrifice it", "blight X", "blight X or pay {1}",
                     "sacrifice a creature or pay {X}", "discard a widget"):
            self.assertIsNone(parse_cost(text), text)

    def test_optional_cost_is_not_parsed_here(self):
        c = card("Test Optional", "{B}", "Sorcery", "As an additional cost to cast ~, you may sacrifice a creature.\n"
                 "Draw a card.")
        self.assertNotIn(KEY, c.advanced_rules)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class RealCards(unittest.TestCase):
    FULL = ("Abjure", "Angelic Purge", "Bankrupt in Blood", "Bone Shards", "Cathartic Reunion", "Daring Buccaneer",
            "Deprive", "Dusk Mangler", "Final Payment", "Kaervek's Spite", "Lethal Sting", "Natural Order",
            "Phyrexian Tribute", "Ruthless Disposal", "Savage Order", "Shared Discovery", "Spark Harvest",
            "Surge of Strength", "Magmatic Insight", "Guardian of the Great Door", "Soaring Stoneglider")
    STILL_PARTIAL = ("Treacherous Greed",)

    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def test_full(self):
        for name in self.FULL:
            c = self.db.get(name)
            self.assertEqual(c.unsupported, [], name)
            self.assertTrue(alternatives(c), name)

    def test_unmodelled_stay_partial(self):
        for name in self.STILL_PARTIAL:
            c = self.db.get(name)
            self.assertTrue(any("additional cost" in u for u in c.unsupported), name)
            self.assertFalse(alternatives(c), name)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class Casting(unittest.TestCase):
    def setUp(self):
        self.db = CardDB(offline=True)
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def lands(self, land, n, who=None):
        for _ in range(n):
            self.g.enter_battlefield(who or self.a, land).sick = False

    def snapshot(self):
        return ([x.card.name for x in self.a.battlefield], [c.name for c in self.a.hand],
                [c.name for c in self.a.graveyard], self.a.life, [x.tapped for x in self.a.battlefield])

    def test_bone_shards_sacrifices_or_discards(self):
        shards = self.db.get("Bone Shards")
        self.lands(SWAMP, 1)
        enemy = self.g.enter_battlefield(self.b, BIG)
        self.a.hand = [shards]
        before = self.snapshot()
        self.assertFalse(self.g.can_cast_now(self.a, shards))      # no creature, no other card
        self.assertFalse(self.g.cast(self.a, shards, [enemy]))
        self.assertEqual(self.snapshot(), before)                  # rejected cast changes nothing
        cub = self.g.enter_battlefield(self.a, TOKEN_BEAR)
        self.assertTrue(self.g.cast(self.a, shards, [enemy]))
        self.g.settle()
        self.assertNotIn(cub, self.a.battlefield)
        self.assertNotIn(enemy, self.b.battlefield)
        # with a spare land in hand it discards the land rather than the creature
        self.g.turn += 1
        self.lands(SWAMP, 1)
        cub = self.g.enter_battlefield(self.a, BIG)
        enemy = self.g.enter_battlefield(self.b, BIG)
        self.a.hand = [self.db.get("Bone Shards"), FOREST]
        self.assertTrue(self.g.cast(self.a, self.a.hand[0], [enemy]))
        self.g.settle()
        self.assertIn(cub, self.a.battlefield)
        self.assertIn("Forest", [c.name for c in self.a.graveyard])

    def test_phyrexian_tribute_needs_two_distinct_creatures(self):
        tribute = self.db.get("Phyrexian Tribute")
        self.lands(SWAMP, 3)
        rock = self.g.enter_battlefield(self.b, card("Test Rock", "{2}", "Artifact", "", None, None))
        self.g.enter_battlefield(self.a, TOKEN_BEAR)
        self.a.hand = [tribute]
        self.assertFalse(self.g.can_cast_now(self.a, tribute))
        self.g.enter_battlefield(self.a, TOKEN_BEAR)
        self.assertTrue(self.g.cast(self.a, tribute, [rock]))
        self.g.settle()
        self.assertEqual(self.a.creatures, [])
        self.assertNotIn(rock, self.b.battlefield)
        self.assertEqual(self.a.sacrificed_turn, 2)

    def test_spark_harvest_pays_mana_without_a_creature(self):
        harvest = self.db.get("Spark Harvest")
        enemy = self.g.enter_battlefield(self.b, BIG)
        self.lands(SWAMP, 2)
        self.a.hand = [harvest]
        self.assertEqual(self.g.cost_of(self.a, harvest), {"generic": 3, "B": 2})
        self.assertFalse(self.g.can_cast_now(self.a, harvest))          # 2 lands: {B} + {3}{B} not payable
        self.lands(SWAMP, 3)
        self.assertTrue(self.g.cast(self.a, harvest, [enemy]))
        self.g.settle()
        self.assertNotIn(enemy, self.b.battlefield)
        self.assertTrue(all(x.tapped for x in self.a.battlefield if x.card.is_land))
        # with a creature it sacrifices and pays only {B}
        self.g.turn += 1
        for x in self.a.battlefield:
            x.tapped = False
        cub = self.g.enter_battlefield(self.a, TOKEN_BEAR)
        enemy = self.g.enter_battlefield(self.b, BIG)
        harvest = self.db.get("Spark Harvest")
        self.a.hand = [harvest]
        self.assertEqual(self.g.cost_of(self.a, harvest), {"generic": 0, "B": 1})
        self.assertTrue(self.g.cast(self.a, harvest, [enemy]))
        self.g.settle()
        self.assertNotIn(cub, self.a.battlefield)
        self.assertEqual(sum(x.tapped for x in self.a.battlefield if x.card.is_land), 1)

    def test_cathartic_reunion_discards_two_other_cards(self):
        reunion = self.db.get("Cathartic Reunion")
        self.lands(MOUNTAIN, 2)
        self.a.hand = [reunion, FOREST]
        self.assertFalse(self.g.can_cast_now(self.a, reunion))           # the spell itself isn't a discard
        self.a.hand = [reunion, FOREST, ISLAND]
        self.assertTrue(self.g.cast(self.a, reunion, []))
        self.g.settle()
        self.assertEqual(sorted(c.name for c in self.a.graveyard), ["Cathartic Reunion", "Forest", "Island"])
        self.assertEqual(len(self.a.hand), 3)

    def test_shared_discovery_taps_creatures_not_its_mana(self):
        discovery = self.db.get("Shared Discovery")
        self.lands(ISLAND, 1)
        cubs = [self.g.enter_battlefield(self.a, TOKEN_BEAR) for _ in range(3)]
        self.a.hand = [discovery]
        self.assertFalse(self.g.can_cast_now(self.a, discovery))
        cubs.append(self.g.enter_battlefield(self.a, TOKEN_BEAR))
        self.assertTrue(self.g.cast(self.a, discovery, []))
        self.g.settle()
        self.assertTrue(all(c.tapped for c in cubs))
        self.assertEqual(len(self.a.hand), 3)

    def test_guardian_cannot_tap_its_only_mana_twice(self):
        guardian = self.db.get("Guardian of the Great Door")
        self.lands(card("Plains", types="Basic Land — Plains", text="({T}: Add {W}.)"), 2)
        for _ in range(3):
            self.g.enter_battlefield(self.a, TOKEN_BEAR)
        self.a.hand = [guardian]
        self.assertFalse(self.g.can_cast_now(self.a, guardian))       # {W}{W} needs both Plains: only 3 others to tap
        self.g.enter_battlefield(self.a, TOKEN_BEAR)
        self.assertTrue(self.g.cast(self.a, guardian, []))
        self.g.settle()
        self.assertTrue(all(x.tapped for x in self.a.battlefield if x.card.name != guardian.name))

    def test_deprive_returns_a_land_and_counter_does_not_refund(self):
        deprive = self.db.get("Deprive")
        self.lands(ISLAND, 2)
        self.a.hand = [deprive]
        bolt = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")
        self.lands(MOUNTAIN, 1, self.b)
        self.b.hand = [bolt]
        self.g._priority_depth = 1          # both spells go on the stack before anything resolves
        self.assertTrue(self.g.cast(self.b, bolt, [self.a]))
        item = self.g.stack[-1]
        self.assertTrue(self.g.cast(self.a, deprive, [item]))
        self.g._priority_depth = 0
        self.g.settle()
        self.assertEqual(sum(x.card.is_land for x in self.a.battlefield), 1)
        self.assertIn("Island", [c.name for c in self.a.hand])
        self.assertEqual(self.a.life, 20)

    def test_final_payment_life_or_sacrifice(self):
        payment = self.db.get("Final Payment")
        self.lands(SWAMP, 2)
        self.lands(card("Plains", types="Basic Land — Plains", text="({T}: Add {W}.)"), 1)
        enemy = self.g.enter_battlefield(self.b, BIG)
        self.a.hand = [payment]
        self.a.life = 5
        self.assertTrue(self.g.can_cast_now(self.a, payment))        # CR 119.4: paying the last life is legal (#467)
        self.assertFalse(self.a.ai._can_cast(self.g, self.a, payment))   # but the AI won't pay itself to 0
        self.a.life = 20
        self.assertTrue(self.g.cast(self.a, payment, [enemy]))
        self.g.settle()
        self.assertEqual(self.a.life, 15)
        self.assertNotIn(enemy, self.b.battlefield)

    def test_lethal_sting_counter_on_own_creature(self):
        sting = self.db.get("Lethal Sting")
        self.lands(SWAMP, 3)
        enemy = self.g.enter_battlefield(self.b, BIG)
        mine = self.g.enter_battlefield(self.a, BIG)
        self.a.hand = [sting]
        self.assertTrue(self.g.cast(self.a, sting, [enemy]))
        self.g.settle()
        self.assertEqual(mine.counters.get("-1/-1"), 1)
        self.assertNotIn(enemy, self.b.battlefield)

    def test_daring_buccaneer_reveal_or_pay(self):
        buccaneer = self.db.get("Daring Buccaneer")
        self.lands(MOUNTAIN, 1)
        self.a.hand = [buccaneer]
        self.assertEqual(self.g.cost_of(self.a, buccaneer), {"generic": 2, "R": 1})
        self.assertFalse(self.g.can_cast_now(self.a, buccaneer))
        pirate = card("Test Pirate", "{1}{U}", "Creature — Human Pirate", "", 1, 1)
        self.a.hand = [buccaneer, pirate]
        self.assertEqual(self.g.cost_of(self.a, buccaneer), {"generic": 0, "R": 1})
        self.assertTrue(self.g.cast(self.a, buccaneer, []))
        self.g.settle()
        self.assertIn(pirate, self.a.hand)          # revealed, not spent
        self.assertIn("Daring Buccaneer", [x.card.name for x in self.a.battlefield])

    def test_kaervek_spite_sacrifices_everything_and_discards_hand(self):
        spite = self.db.get("Kaervek's Spite")
        self.lands(SWAMP, 3)
        self.g.enter_battlefield(self.a, TOKEN_BEAR)
        self.a.hand = [spite, FOREST, ISLAND]
        self.assertTrue(self.g.cast(self.a, spite, [self.b]))
        self.g.settle()
        self.assertEqual((self.a.battlefield, self.a.hand, self.b.life), ([], [], 15))

    def test_copies_pay_nothing(self):
        c = self.db.get("Bone Shards")
        c.spell_copy = True
        self.assertEqual(alternatives(c), ())


ELF = card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)
ELF_LORD = card("Test Elf Lord", "{2}{G}", "Creature — Elf", "", 3, 3)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class Behold(unittest.TestCase):
    """'behold an Elf and exile it' (Champions of the Perfect): the exiled card returns to its owner's hand when
    the champion leaves the battlefield."""
    def setUp(self):
        self.db = CardDB(offline=True)
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.respond = p.ai.respond_extras = lambda *args: None
        for _ in range(4):
            self.g.enter_battlefield(self.a, FOREST).sick = False
        self.champion = self.db.get("Champions of the Perfect")
        self.assertEqual(self.champion.unsupported, [])

    def champ(self):
        return next(x for x in self.a.battlefield if x.card.name == "Champions of the Perfect")

    def test_needs_an_elf_other_than_itself(self):
        self.a.hand = [self.champion, ISLAND]          # Champions of the Perfect is an Elf: it can't behold itself
        self.assertFalse(self.g.can_cast_now(self.a, self.champion))

    def test_from_hand_returns_when_it_leaves(self):
        self.a.hand = [self.champion, ELF]
        self.assertTrue(self.g.cast(self.a, self.champion, []))
        self.g.settle()
        self.assertEqual([c.name for c in self.a.exile], ["Test Elf"])
        self.assertEqual(self.a.hand, [])
        self.g.destroy(self.champ())
        self.g.settle()
        self.assertEqual([c.name for c in self.a.hand], ["Test Elf"])
        self.assertEqual(list(self.a.exile), [])

    def test_from_battlefield_returns_to_hand(self):
        elf = self.g.enter_battlefield(self.a, ELF)
        self.a.hand = [self.champion]
        self.assertTrue(self.g.cast(self.a, self.champion, []))
        self.g.settle()
        self.assertNotIn(elf, self.a.battlefield)
        self.assertEqual([c.name for c in self.a.exile], ["Test Elf"])
        self.g.leave_battlefield(self.champ(), "hand")
        self.g.settle()
        self.assertEqual(sorted(c.name for c in self.a.hand), ["Champions of the Perfect", "Test Elf"])

    def test_countered_spell_leaves_the_card_in_exile(self):
        self.a.hand = [self.champion, ELF]
        counter = card("Test Negate", "{U}", "Instant", "Counter target spell.")
        self.g.enter_battlefield(self.b, ISLAND).sick = False
        self.b.hand = [counter]
        self.g._priority_depth = 1
        self.assertTrue(self.g.cast(self.a, self.champion, []))
        self.assertTrue(self.g.cast(self.b, counter, [self.g.stack[-1]]))
        self.g._priority_depth = 0
        self.g.settle()
        self.assertEqual([c.name for c in self.a.exile], ["Test Elf"])
        self.assertIn("Champions of the Perfect", [c.name for c in self.a.graveyard])

    def test_champions_of_the_shoal_stuns_the_target_not_itself(self):
        """'Whenever ~ enters or becomes tapped, tap up to one target creature and put a stun counter on it':
        "it" is the target (the becomes-tapped head used to read it as ~)."""
        shoal = self.db.get("Champions of the Shoal")
        merfolk = card("Test Merfolk", "{U}", "Creature — Merfolk", "", 1, 1)
        for _ in range(4):
            self.g.enter_battlefield(self.a, ISLAND).sick = False
        enemy = self.g.enter_battlefield(self.b, BIG)
        self.a.hand = [shoal, merfolk]
        self.assertTrue(self.g.cast(self.a, shoal, []))
        self.g.settle()
        champ = next(x for x in self.a.battlefield if x.card.name == "Champions of the Shoal")
        self.assertTrue(enemy.tapped)
        self.assertEqual(enemy.counters.get("stun"), 1)
        self.assertFalse(champ.counters.get("stun"))

    def test_ai_beholds_the_cheap_card(self):
        from mtgsim.ai import HeuristicAI
        self.a.ai = HeuristicAI()
        lord = self.g.enter_battlefield(self.a, ELF_LORD)
        self.a.hand = [self.champion, ELF]
        self.a.ai.main_phase(self.g, self.a)
        self.g.settle()
        self.assertIn(lord, self.a.battlefield)
        self.assertEqual([c.name for c in self.a.exile], ["Test Elf"])
        self.assertTrue(any(x.card.name == "Champions of the Perfect" for x in self.a.battlefield))


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class AICasts(unittest.TestCase):
    def setUp(self):
        from mtgsim.ai import HeuristicAI
        self.db = CardDB(offline=True)
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 20

    def test_ai_casts_bone_shards_at_the_enemy_paying_with_its_least(self):
        for _ in range(1):
            self.g.enter_battlefield(self.a, SWAMP).sick = False
        cub = self.g.enter_battlefield(self.a, TOKEN_BEAR)
        mine = self.g.enter_battlefield(self.a, BIG)
        enemy = self.g.enter_battlefield(self.b, BIG)
        self.a.hand = [self.db.get("Bone Shards")]
        self.a.ai.main_phase(self.g, self.a)
        self.g.settle()
        self.assertNotIn(enemy, self.b.battlefield)
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(cub, self.a.battlefield)

    def test_ai_keeps_good_creatures_for_a_weak_payoff(self):
        for _ in range(3):
            self.g.enter_battlefield(self.a, SWAMP).sick = False
        mine = [self.g.enter_battlefield(self.a, BIG) for _ in range(2)]
        rock = self.g.enter_battlefield(self.b, card("Test Rock", "{1}", "Artifact", "", None, None))
        self.a.hand = [self.db.get("Phyrexian Tribute")]
        self.a.ai.main_phase(self.g, self.a)
        self.g.settle()
        self.assertTrue(all(x in self.a.battlefield for x in mine))
        self.assertIn(rock, self.b.battlefield)


if __name__ == "__main__":
    unittest.main()


class CountedParse(unittest.TestCase):
    def test_x_and_any_number(self):
        self.assertEqual(parse_cost("discard X cards"), ((("discard", "x", {}),),))
        self.assertEqual(parse_cost("discard X cards at random"), ((("discard_random", "x", {}),),))
        self.assertEqual(parse_cost("pay X life"), ((("life", "x", {}),),))
        self.assertEqual(parse_cost("sacrifice any number of creatures"), ((("sac", "any", {"types": ["creature"]}),),))

    def test_counted_refusals(self):
        for text in ("discard X cards or pay {2}", "discard X cards and pay X life", "pay any number of life",
                     "reveal X cards from your hand", "sacrifice X widgets"):
            self.assertIsNone(parse_cost(text), text)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class CountedGames(unittest.TestCase):
    """X chosen as the spell is cast is the spell's X; 'any number of' counts as 'this way'."""
    def setUp(self):
        self.db = CardDB(offline=True)
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.respond = p.ai.respond_extras = lambda *args: None
        for land in (FOREST, FOREST, ISLAND, MOUNTAIN, SWAMP, SWAMP, SWAMP, SWAMP):
            self.g.enter_battlefield(self.a, land).sick = False

    def choose(self, n):
        self.a.ai.choose_cost_count = lambda game, me, card, kind, pool, mode: n

    def test_sickening_dreams_discards_x_and_deals_x(self):
        self.choose(2)
        enemy = self.g.enter_battlefield(self.b, BIG)
        spell = self.db.get("Sickening Dreams")
        self.a.hand = [spell, ISLAND, FOREST, ISLAND]
        self.assertTrue(self.g.cast(self.a, spell, []))
        self.g.settle()
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual((self.a.life, self.b.life, enemy.damage), (18, 18, 2))

    def test_x_zero_is_legal(self):
        self.choose(0)
        spell = self.db.get("Sickening Dreams")
        self.a.hand = [spell]
        self.assertTrue(self.g.can_cast_now(self.a, spell))
        self.assertTrue(self.g.cast(self.a, spell, []))
        self.g.settle()
        self.assertEqual((self.a.life, self.b.life), (20, 20))

    def test_hatred_pays_x_life(self):
        self.choose(3)
        mine = self.g.enter_battlefield(self.a, TOKEN_BEAR)
        spell = self.db.get("Hatred")
        self.a.hand = [spell]
        self.assertTrue(self.g.cast(self.a, spell, [mine]))
        self.g.settle()
        self.assertEqual((self.a.life, mine.power, mine.toughness), (17, 4, 1))

    def test_life_x_never_reaches_zero(self):
        self.choose(50)
        self.a.life = 4
        mine = self.g.enter_battlefield(self.a, TOKEN_BEAR)
        spell = self.db.get("Hatred")
        self.a.hand = [spell]
        self.assertTrue(self.g.cast(self.a, spell, [mine]))
        self.g.settle()
        self.assertEqual((self.a.life, mine.power), (1, 4))

    def test_restless_and_nostalgic_dreams_return_x(self):
        self.choose(2)
        self.a.graveyard.extend([BIG, TOKEN_BEAR, FOREST])
        spell = self.db.get("Restless Dreams")
        self.a.hand = [spell, ISLAND, ISLAND]
        self.assertTrue(self.g.cast(self.a, spell, []))
        self.g.settle()
        self.assertEqual(sorted(c.name for c in self.a.hand), ["Test Cub", "Test Giant"])
        spell = self.db.get("Nostalgic Dreams")
        self.a.hand.append(spell)
        self.assertTrue(self.g.cast(self.a, spell, []))
        self.g.settle()
        self.assertEqual(len(self.a.hand), 2)            # discarded two, got two back
        self.assertIn("Nostalgic Dreams", [c.name for c in self.a.exile])

    def test_vicious_betrayal_sacrifices_cheap_others_and_counts_them(self):
        target = self.g.enter_battlefield(self.a, BIG)
        cubs = [self.g.enter_battlefield(self.a, TOKEN_BEAR) for _ in range(2)]
        spell = self.db.get("Vicious Betrayal")
        self.a.hand = [spell]
        self.assertTrue(self.g.cast(self.a, spell, [target]))
        self.g.settle()
        self.assertTrue(all(c not in self.a.battlefield for c in cubs))
        self.assertEqual((target.power, target.toughness), (9, 9))

    def test_restock_returns_two_cards(self):
        """'Return two target cards from your graveyard' read 'two target' as a card type and returned nothing
        (targeted graveyard cards since #546: cx_card_move)."""
        self.a.graveyard.extend([BIG, FOREST, ISLAND])
        spell = self.db.get("Restock")
        self.a.hand = [spell]
        self.assertTrue(self.g.cast(self.a, spell, self.a.graveyard[:2]))
        self.g.settle()
        self.assertEqual(len(self.a.hand), 2)

    def test_ai_chooses_x_for_restless_dreams(self):
        """The AI discards a spare land to return a good creature card."""
        from mtgsim.ai import HeuristicAI
        self.a.ai = HeuristicAI()
        self.a.graveyard.extend([BIG, BIG])
        self.a.hand = [self.db.get("Restless Dreams"), FOREST, ISLAND]
        self.a.ai.main_phase(self.g, self.a)
        self.g.settle()
        # it plays the Forest as its land, discards the Island (X=1), returns a Giant and casts it
        self.assertIn("Restless Dreams", [c.name for c in self.a.graveyard])
        self.assertIn("Island", [c.name for c in self.a.graveyard])
        self.assertEqual([c.name for c in self.a.graveyard].count("Test Giant"), 1)

    def test_ai_life_x_is_bounded_by_the_value(self):
        from mtgsim import cx_spell_costs
        from mtgsim.ai import HeuristicAI
        self.a.ai = HeuristicAI()
        self.a.life = 6
        self.g.enter_battlefield(self.a, TOKEN_BEAR)
        x = cx_spell_costs.cost_x(self.g, self.a, self.db.get("Hatred"))
        self.assertLess(x, 5)


PLAINS = card("Plains", types="Basic Land — Plains", text="({T}: Add {W}.)")
KNIGHT = card("Test Knight", "{W}{W}", "Creature — Human Knight", "", 2, 2)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class Defilers(unittest.TestCase):
    """'As an additional cost to cast white permanent spells, you may pay 2 life. Those spells cost {W} less ...'"""
    def setUp(self):
        self.db = CardDB(offline=True)
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.respond = p.ai.respond_extras = lambda *args: None
        self.defiler = self.g.enter_battlefield(self.a, self.db.get("Defiler of Faith"))

    def test_pays_life_only_when_it_needs_the_discount(self):
        self.g.enter_battlefield(self.a, PLAINS).sick = False
        self.a.hand = [KNIGHT]
        self.assertEqual(self.g.cost_of(self.a, KNIGHT), {"generic": 0, "W": 1})
        self.assertTrue(self.g.cast(self.a, KNIGHT, []))
        self.g.settle()
        self.assertEqual(self.a.life, 18)
        self.assertIn("Test Knight", [x.card.name for x in self.a.battlefield])
        # with enough white mana it pays the full cost and no life
        self.g.enter_battlefield(self.a, PLAINS).sick = False
        for x in self.a.battlefield:
            x.tapped = False
        knight2 = card("Test Knight", "{W}{W}", "Creature — Human Knight", "", 2, 2)
        self.a.hand = [knight2]
        self.assertTrue(self.g.cast(self.a, knight2, []))
        self.assertEqual(self.a.life, 18)

    def test_only_its_color_permanents_and_not_at_low_life(self):
        self.g.enter_battlefield(self.a, PLAINS).sick = False
        sorcery = card("Test Ray", "{W}{W}", "Sorcery", "You gain 1 life.")
        self.assertEqual(self.g.cost_of(self.a, sorcery), {"generic": 0, "W": 2})      # not a permanent spell
        green = card("Test Elk", "{G}{G}", "Creature — Elk", "", 2, 2)
        self.assertEqual(self.g.cost_of(self.a, green), {"generic": 0, "G": 2})
        self.a.life = 7
        self.assertEqual(self.g.cost_of(self.a, KNIGHT), {"generic": 0, "W": 2})
        self.assertFalse(self.g.can_cast_now(self.a, KNIGHT))

    def test_ai_casts_with_the_discount(self):
        from mtgsim.ai import HeuristicAI
        self.a.ai = HeuristicAI()
        self.g.enter_battlefield(self.a, PLAINS).sick = False
        self.a.hand = [KNIGHT]
        self.a.ai.main_phase(self.g, self.a)
        self.g.settle()
        self.assertIn("Test Knight", [x.card.name for x in self.a.battlefield])
        self.assertEqual(self.a.life, 18)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class OptionalReductions(unittest.TestCase):
    """'As an additional cost, you may <any number of ...>. This spell costs {N} less for each ... this way.'"""
    def setUp(self):
        self.db = CardDB(offline=True)
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def lands(self, land, n):
        for _ in range(n):
            self.g.enter_battlefield(self.a, land).sick = False

    def test_parse(self):
        rules = self.db.get("Hierophant Bio-Titan").advanced_rules
        self.assertEqual(rules[KEY], ((("rm_p1", "any", {"reduce": 2}),),))
        self.assertEqual(self.db.get("Explosive Singularity").advanced_rules[KEY][0][0][:2], ("tap", "any"))
        for name in ("Hierophant Bio-Titan", "Explosive Singularity"):
            self.assertEqual(self.db.get(name).unsupported, [], name)

    def test_explosive_singularity_taps_creatures_only_as_needed(self):
        singularity = self.db.get("Explosive Singularity")          # {8}{R}{R}
        self.lands(MOUNTAIN, 7)
        cubs = [self.g.enter_battlefield(self.a, TOKEN_BEAR) for _ in range(4)]
        self.a.hand = [singularity]
        self.assertEqual(self.g.cost_of(self.a, singularity), {"generic": 5, "R": 2})   # 3 creatures tapped
        self.assertTrue(self.g.cast(self.a, singularity, [self.b]))
        self.g.settle()
        self.assertEqual(self.b.life, 10)
        self.assertEqual(sum(c.tapped for c in cubs), 3)

    def test_without_units_the_full_cost(self):
        singularity = self.db.get("Explosive Singularity")
        self.lands(MOUNTAIN, 9)
        self.a.hand = [singularity]
        self.assertFalse(self.g.can_cast_now(self.a, singularity))

    def test_hierophant_removes_counters(self):
        titan = self.db.get("Hierophant Bio-Titan")                 # {12}{G}{G}? read its cost
        need = sum(v for k, v in titan.mana_cost.items() if k != "X")
        big = self.g.enter_battlefield(self.a, BIG)
        big.counters["+1/+1"] = 3
        self.lands(FOREST, need - 6)
        self.a.hand = [titan]
        self.assertTrue(self.g.cast(self.a, titan, []))
        self.g.settle()
        self.assertEqual(big.counters["+1/+1"], 0)
        self.assertIn("Hierophant Bio-Titan", [x.card.name for x in self.a.battlefield])

    def test_x_spells_keep_the_reduction_visible(self):
        """The engine pays {X} after the reduction, so 'costs {2} less for each card exiled' couldn't lower X."""
        march = self.db.get("March of Wretched Sorrow")
        self.assertTrue(march.unsupported)
        self.assertFalse(alternatives(march))

    def test_ai_casts_explosive_singularity(self):
        from mtgsim.ai import HeuristicAI
        self.a.ai = HeuristicAI()
        self.lands(MOUNTAIN, 7)
        for _ in range(3):
            self.g.enter_battlefield(self.a, TOKEN_BEAR).sick = True
        self.b.life = 10
        self.a.hand = [self.db.get("Explosive Singularity")]
        self.a.ai.main_phase(self.g, self.a)
        self.g.settle()
        self.assertLessEqual(self.b.life, 0)

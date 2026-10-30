"""le-chonk-8 engine + foundation + AI batch.

- the "As ~ enters, roll a dN/d6 ... enters with a number of <kind> counters equal to the
  result" entry hook (Hydradoodle, Neverwinter Hydra, Jumbo Imp, Hammer Jammer, Temp of the
  Damned): the roll happens in enter_battlefield via dungeon_mechanics.roll, the counters
  arrive before state-based actions, and the parsed etb die_roll trigger is spent
- the combined cast filter "spell:colorless&cmc>=7" (Sanctum of Ugin)
- "Whenever a permanent you control enters tapped" (Amulet of Vigor): the enters_tapped
  trigger flag
- card_matches vocabulary: outlaw, snow, nontoken historic, "1/1 creature", stat
  comparisons like "toughness greater than its power", and fail-closed unknown words
- "~ or another Zombie enters" (Noxious Ghoul): the any_controller trigger flag hears
  any player's entries; controller-scoped triggers do not
- multi-exile graveyard costs ("Exile two cards from your graveyard", Psychatog, Bearscape,
  and the {X} "Exile X cards" variant, Necropolis Fiend)
- the "Tap another untapped <desc> creature you control" ability cost (Ranger's Hawk,
  Dungeon Descent, Chicken a la King)
- "{X}{G}: ~ becomes an X/X creature" self-animation (Lair of the Hydra)
- the "coven" ability condition (three or more creatures with different powers)
- Shimmer: choose a land type as it enters; each land of the chosen type has phasing
- a deterministic fight-simulation budget so lethal_setup degrades instead of hanging
- Bloodthirsty Adversary delegates its payments to phasing.pay_repeat: pay any number of
  times, that many +1/+1 counters and that many graveyard copies
"""
import dataclasses
import random
import unittest

import mtgsim.ai as ai
from mtgsim import costs as planner
from mtgsim.ai import HeuristicAI
from mtgsim.cards import Activated, Effect, Trigger
from mtgsim.engine import Game, Permanent, Player
from mtgsim.engine.state import card_matches
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, SWAMP, card

DOODLE = card("Test Doodle", "{X}{X}{G}{G}", "Creature — Plant", "Reach, trample\n"
              "As this creature enters, roll X six-sided dice. This creature enters with "
              "a number of +1/+1 counters on it equal to the total of those results.", 0, 0)
HYDRA_D6 = card("Test Neverwinter", "{X}{X}{G}{G}", "Creature — Hydra", "Trample\n"
                "As this creature enters, roll X d6. It enters with a number of +1/+1 "
                "counters on it equal to the total of those results.", 0, 0)
JUMBO = card("Test Jumbo", "{2}{B}", "Creature — Imp", "Flying\n"
             "As this creature enters, roll a six-sided die. This creature enters with a "
             "number of +1/+1 counters on it equal to the result.", 0, 0)
FUNK = card("Test Funk", "{2}{B}", "Creature — Zombie", "As this creature enters, roll a "
            "six-sided die. This creature enters with a number of funk counters on it equal "
            "to the result.", 3, 3)
PLAINS_CARD = card("Test Plains", types="Basic Land — Plains", text="({T}: Add {W}.)")
TAPPED_LAND = card("Test Tapland", "", "Land",
                   "This land enters tapped.\n{T}: Add {G}.")
GHOUL = card("Test Ghoul", "{3}{B}", "Creature — Zombie",
             "Whenever Test Ghoul or another Zombie enters, you gain 1 life.", 3, 3)
SMALL_ZOMBIE = card("Test Walker", "{1}{B}", "Creature — Zombie", "", 2, 2)
LEGENDARY_DUDE = card("Test Legend", "{1}{W}", "Legendary Creature — Bird Soldier", "Flying", 2, 2)
BIRD = card("Test Bird", "{1}{W}", "Creature — Bird", "", 1, 1)
SHIMMER = card("Test Shimmer", "{1}{U}", "Enchantment",
               "As this enchantment enters, choose a land type.\nEach land of the chosen "
               "type has phasing.")
LAIR = card("Test Lair", "", "Land",
            "{T}: Add {G}.\n{X}{G}: Until end of turn, this land becomes an X/X green Hydra "
            "creature. It's still a land. X can't be 0.")
ADVERSARY = card("Test Adversary", "{2}{R}", "Creature — Vampire",
                 "Haste\nWhen Test Adversary enters, you may pay {2}{R} any number of times. "
                 "When you pay this cost one or more times, put that many +1/+1 counters on "
                 "it, then exile up to that many target instant and sorcery cards with mana "
                 "value 3 or less from your graveyard and copy them.", 2, 2)
SMALL_SPELL = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 1 damage to any target.")
MID_SPELL = card("Test Cut", "{2}{R}", "Instant", "Test Cut deals 3 damage to any target.")


class Chonk8(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        self.g.active_idx = 0
        for p in (self.a, self.b):
            p.ai.attack, p.ai.block = (), {}
        self.a.library = [ISLAND] * 20
        self.b.library = [ISLAND] * 20

    def perm(self, c, owner, **kw):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        for k, v in kw.items():
            setattr(p, k, v)
        owner.battlefield.append(p)
        return p

    def land(self, p, n, c=MOUNTAIN):
        return [self.perm(c, p) for _ in range(n)]


class AsEntersRoll(Chonk8):
    def test_x_dice_total_becomes_counters(self):
        perm = self.g.enter_battlefield(self.a, DOODLE, x=3)
        total = self.g._die_rolls.get(self.a, 0)
        self.assertEqual(perm.counters["+1/+1"], total)
        self.assertEqual((perm.power, perm.toughness), (total, total))
        self.assertIn(perm, self.a.battlefield)       # the 0/0 survived state-based actions

    def test_d6_wording(self):
        perm = self.g.enter_battlefield(self.a, HYDRA_D6, x=2)
        total = self.g._die_rolls.get(self.a, 0)
        self.assertEqual(perm.counters["+1/+1"], total)
        self.assertEqual(perm.power, total)

    def test_single_die_and_named_counter(self):
        perm = self.g.enter_battlefield(self.a, JUMBO)
        total = self.g._die_rolls.get(self.a, 0)
        self.assertGreaterEqual(total, 1)
        self.assertEqual(perm.counters["+1/+1"], total)
        perm = self.g.enter_battlefield(self.a, FUNK)
        total = self.g._die_rolls.get(self.a, 0)
        self.assertEqual(perm.counters["funk"], total)

    def test_the_parsed_etb_die_roll_trigger_is_spent(self):
        rolled = dataclasses.replace(JUMBO, triggers=[Trigger("etb", [Effect("die_roll", data={"sides": 6})])])
        self.g.pending.clear()
        self.g.enter_battlefield(self.a, rolled)
        self.assertFalse(any(e and e.kind == "die_roll" for _, e, *_ in self.g.pending))

    def test_no_rolls_for_cards_without_the_counter_clause(self):
        from mtgsim.engine.battlefield import as_enters_roll
        self.assertIsNone(as_enters_roll(BEAR))
        plain = card("Plain Roller", "{1}{R}", "Creature — Goblin",
                     "When this creature enters, roll a six-sided die. It deals damage "
                     "equal to the result to any target.", 1, 1)
        self.assertIsNone(as_enters_roll(plain))


class SanctumCombinedCastFilter(Chonk8):
    def setUp(self):
        super().setUp()
        land = self.land(self.a, 8)
        for x in land:
            x.tapped = False
        self.sanctum = self.perm(dataclasses.replace(
            card("Test Sanctum", types="Land", text=""),
            triggers=[Trigger("cast_spell", [Effect("gain_life", 1)],
                               filter="spell:colorless&cmc>=7")]), self.a)

    def cast(self, c):
        self.a.hand = [c]
        self.g.cast(self.a, c)
        self.g.settle()

    def test_colorless_spell_with_cmc_7_fires(self):
        big = card("Test Golem", "{7}", "Artifact Creature — Golem", "", 7, 7)
        life = self.a.life
        self.cast(big)
        self.assertEqual(self.a.life, life + 1)

    def test_colorless_spell_with_too_small_cmc_does_not_fire(self):
        small = card("Test Idol", "{4}", "Artifact", "", 0, 0, cmc=4)
        life = self.a.life
        self.cast(small)
        self.assertEqual(self.a.life, life)

    def test_colored_spell_with_cmc_7_does_not_fire(self):
        spell = card("Test Big Burn", "{5}{R}{R}", "Sorcery", "Test Big Burn deals 7 damage to any target.")
        life = self.a.life
        self.cast(spell)
        self.assertEqual(self.a.life, life)


class AmuletEntersTapped(Chonk8):
    def setUp(self):
        super().setUp()
        self.amulet = self.perm(dataclasses.replace(
            card("Test Amulet", "{1}", "Artifact", ""),
            triggers=[Trigger("permanent_enters", [Effect("untap_prev", target="trigger_subject")],
                              filter="noself|any|permanent", data={"enters_tapped": True})]), self.a)

    def test_entering_tapped_permanent_is_untapped(self):
        perm = self.g.enter_battlefield(self.a, TAPPED_LAND)
        self.g.settle()
        self.assertIn(perm, self.a.battlefield)
        self.assertFalse(perm.tapped)

    def test_entering_untapped_permanent_does_not_queue(self):
        self.g.pending.clear()
        self.g.enter_battlefield(self.a, MOUNTAIN)
        self.g.settle()
        self.assertFalse(self.g.pending)


class CardMatchesVocabulary(unittest.TestCase):
    OUTLAW = card("Test Rogue", "{1}{B}", "Creature — Human Rogue", "", 1, 1)
    WIZARD = card("Test Wizard", "{1}{U}", "Creature — Human Wizard", "", 1, 1)
    NOT_OUTLAW = card("Test Soldier", "{1}{W}", "Creature — Human Soldier", "", 1, 1)
    SNOW_CREATURE = card("Test Snowman", "{1}{U}", "Creature — Construct", "", 1, 1)
    SAGA = card("Test Saga", "{2}{W}", "Enchantment — Saga", "", 0, 0)
    TOKEN = dataclasses.replace(card("Test Token", types="Creature — Saproling", text="", cmc=0),
                               is_token=True)

    def setUp(self):
        self.SNOW_CREATURE.snow = True

    def test_outlaw(self):
        self.assertTrue(card_matches(self.OUTLAW, "an outlaw you control"))
        self.assertTrue(card_matches(self.WIZARD, "an outlaw you control"))
        self.assertFalse(card_matches(self.NOT_OUTLAW, "an outlaw you control"))

    def test_snow(self):
        self.assertTrue(card_matches(self.SNOW_CREATURE, "a snow permanent you control"))
        self.assertFalse(card_matches(BEAR, "a snow permanent you control"))

    def test_nontoken_historic(self):
        artifact = card("Test Relic", "{2}", "Artifact", "")
        self.assertTrue(card_matches(artifact, "a nontoken historic permanent you control"))
        self.assertTrue(card_matches(LEGENDARY_DUDE, "a nontoken historic permanent you control"))
        self.assertFalse(card_matches(BEAR, "a nontoken historic permanent you control"))
        self.assertFalse(card_matches(self.TOKEN, "a nontoken historic permanent you control"))

    def test_one_one_creature(self):
        self.assertFalse(card_matches(BEAR, "a 1/1 creature you control"))
        self.assertTrue(card_matches(card("Test Weenie", "{W}", "Creature — Human", "", 1, 1),
                                     "a 1/1 creature you control"))

    def test_toughness_greater_than_power(self):
        wall = card("Test Wall", "{1}{G}", "Creature — Wall", "", 1, 4)
        self.assertTrue(card_matches(wall, "a creature you control with toughness greater than its power"))
        self.assertFalse(card_matches(BEAR, "a creature you control with toughness greater than its power"))

    def test_you_control_tail_is_scope_not_vocabulary(self):
        self.assertTrue(card_matches(BEAR, "a creature you control"))
        self.assertTrue(card_matches(BEAR, "a creature you own"))

    def test_color_words(self):
        black = card("Black Dude", "{1}{B}", "Creature — Human", "", 1, 1)
        white = card("White Dude", "{1}{W}", "Creature — Human", "", 1, 1)
        self.assertTrue(card_matches(black, "a black creature"))
        self.assertFalse(card_matches(white, "a black creature"))
        self.assertTrue(card_matches(white, "a nonblack creature"))
        self.assertFalse(card_matches(black, "a nonblack creature"))

    def test_unknown_words_fail_closed(self):
        self.assertFalse(card_matches(BEAR, "a zibzab creature"))
        self.assertFalse(card_matches(BEAR, "a kind creature card"))
        self.assertTrue(card_matches(BEAR, "a creature card"))
        self.assertTrue(card_matches(BEAR, "a card"))

    def test_sample_corpus_shapes(self):
        """Desc shapes found by a 4000-card vocabulary sample of the card database."""
        bear3 = card("Bear3", "{3}{G}", "Creature — Bear", "", 3, 3)
        aura = card("Test Aura", "{1}{W}", "Enchantment — Aura", "")
        land = card("Test Wastes", "", "Land", "")
        self.assertTrue(card_matches(BEAR, "creatures"))                      # plural type word
        self.assertFalse(card_matches(land, "creatures"))
        exact = card("Exact2", "{2}", "Artifact", "")
        self.assertTrue(card_matches(exact, "an artifact card with mana value 2, reveal that card"))
        self.assertFalse(card_matches(bear3, "an artifact card with mana value 2, reveal that card"))
        # the target slots of one spell are alternatives (Relive the Past, Pull from the Deep)
        saga = card("Test Saga2", "{2}{W}", "Enchantment — Saga", "")
        self.assertFalse(card_matches(aura, "artifact card, up to one target land card, and up to "
                                            "one target non-Aura enchantment"))   # it IS an Aura
        self.assertTrue(card_matches(saga, "artifact card, up to one target land card, and up to "
                                           "one target non-Aura enchantment"))
        self.assertTrue(card_matches(land, "artifact card, up to one target land card, and up to "
                                           "one target non-Aura enchantment"))
        self.assertFalse(card_matches(bear3, "instant card and up to one target sorcery"))
        self.assertTrue(card_matches(card("Test Bolt2", "{2}{R}", "Instant", ""), "instant card and "
                                     "up to one target sorcery"))


class AnyControllerEnters(Chonk8):
    def ghoul(self):
        return self.perm(dataclasses.replace(
            GHOUL, triggers=[Trigger("permanent_enters", [Effect("gain_life", 1)],
                                     filter="self|other|Zombie", data={"any_controller": True})]), self.a)

    def scoped_watcher(self):
        return self.perm(dataclasses.replace(
            card("Test Watcher", "{1}{W}", "Creature — Human", "", 1, 1),
            triggers=[Trigger("permanent_enters", [Effect("gain_life", 5)],
                              filter="noself|other|creature")]), self.a)

    def test_own_zombie_entry_fires(self):
        self.ghoul()
        life = self.a.life
        self.g.enter_battlefield(self.a, SMALL_ZOMBIE)
        self.g.settle()
        self.assertEqual(self.a.life, life + 1)

    def test_opponents_zombie_entry_fires_the_flagged_trigger(self):
        self.ghoul()
        life = self.a.life
        self.g.enter_battlefield(self.b, SMALL_ZOMBIE)
        self.g.settle()
        self.assertEqual(self.a.life, life + 1)

    def test_opponents_creature_entry_does_not_fire_controller_scoped_trigger(self):
        self.ghoul()
        self.scoped_watcher()
        life = self.a.life
        self.g.enter_battlefield(self.b, BEAR)
        self.g.settle()
        self.assertEqual(self.a.life, life)

    def test_own_creature_entry_fires_the_controller_scoped_trigger(self):
        self.ghoul()
        self.scoped_watcher()
        life = self.a.life
        self.g.enter_battlefield(self.a, BEAR)
        self.g.settle()
        self.assertEqual(self.a.life, life + 5)   # the zombie filter misses BEAR, the scoped one fires

    def test_the_ghoul_itself_entering_fires(self):
        life = self.a.life
        self.g.enter_battlefield(self.a, dataclasses.replace(
            GHOUL, triggers=[Trigger("permanent_enters", [Effect("gain_life", 1)],
                                     filter="self|other|Zombie", data={"any_controller": True})]))
        self.g.settle()
        self.assertEqual(self.a.life, life + 1)


class MultiExileGraveyardCost(Chonk8):
    def setUp(self):
        super().setUp()
        self.tog = Activated("ability", {"generic": 1},
                             effects=[Effect("pump", 1, 1, target="self")],
                             extra_costs={"exile_gy_card": "card", "exile_gy_count": 2},
                             text="{1}, Exile two cards from your graveyard: ~ gets +1/+1.")
        self.tog_perm = self.perm(dataclasses.replace(
            card("Test Tog", "{1}{U}{B}", "Creature — Horror", "", 1, 2), activated=[self.tog]), self.a)
        self.land(self.a, 3)

    def test_two_cards_are_required_and_exiled(self):
        self.a.graveyard = [BEAR]
        self.assertFalse(self.g.can_activate(self.a, self.tog_perm, 0))
        self.a.graveyard = [BEAR, SMALL_SPELL, MID_SPELL]
        self.assertTrue(self.g.can_activate(self.a, self.tog_perm, 0))
        self.assertTrue(self.g.activate_ability(self.a, self.tog_perm, 0))
        self.assertEqual([c.name for c in self.a.exile], ["Test Bolt", "Grizzly Bears"])
        self.assertEqual(self.tog_perm.power, 2)

    def test_x_count_exiles_x_cards(self):
        act = Activated("ability", {"X": 1}, effects=[Effect("debuff_one", 0, target="creature",
                                                             data={"x": True})],
                        extra_costs={"tap": True, "exile_gy_card": "card", "exile_gy_count": "x"},
                        text="{X}, {T}, Exile X cards from your graveyard: Target creature "
                             "gets -X/-X until end of turn.")
        fiend = self.perm(dataclasses.replace(
            card("Test Fiend", "{1}{B}", "Creature — Zombie", "", 4, 4), activated=[act]), self.a)
        victim = self.perm(BEAR, self.b)
        self.a.graveyard = [BEAR, SMALL_SPELL, MID_SPELL]
        plan = planner.ability_plan(self.g, self.a, fiend, act, {"generic": 2}, x=2)
        self.assertEqual(len(plan.exile_gy_cards), 2)
        self.assertTrue(self.g.can_activate(self.a, fiend, 0, x=2))
        self.a.graveyard = [BEAR, SMALL_SPELL, MID_SPELL]
        self.assertTrue(self.g.activate_ability(self.a, fiend, 0, [victim], x=2))
        self.assertEqual(len(self.a.exile), 2)
        self.g.settle()
        self.assertLessEqual(victim.toughness, 2)    # -2/-2 hit the 2/2


class TapAnotherCreatureCost(Chonk8):
    def setUp(self):
        super().setUp()
        self.hawk = self.perm(dataclasses.replace(
            card("Test Hawk", "{2}{W}", "Creature — Bird", "Flying", 1, 1),
            activated=[Activated(
                "ability", {"generic": 3}, effects=[Effect("gain_life", 1)],
                extra_costs={"tap": True, "tap_other": "another legendary creature"},
                sorcery=True,
                text="{3}, {T}, Tap another untapped legendary creature you control: "
                     "You gain 1 life.")]), self.a)
        self.land(self.a, 4)

    def test_needs_an_untapped_other_matching_creature(self):
        self.assertFalse(self.g.can_activate(self.a, self.hawk, 0))
        dude = self.perm(LEGENDARY_DUDE, self.a)
        self.assertTrue(self.g.can_activate(self.a, self.hawk, 0))
        dude.tapped = True
        self.assertFalse(self.g.can_activate(self.a, self.hawk, 0))

    def test_activate_taps_source_and_donor(self):
        dude = self.perm(LEGENDARY_DUDE, self.a)
        life = self.a.life
        self.assertTrue(self.g.activate_ability(self.a, self.hawk, 0))
        self.g.settle()
        self.assertTrue(self.hawk.tapped)
        self.assertTrue(dude.tapped)
        self.assertEqual(self.a.life, life + 1)

    def test_self_tappable_wording(self):
        king = self.perm(dataclasses.replace(
            card("Test King", "{2}{W}", "Creature — Bird Noble", "", 2, 2),
            activated=[Activated(
                "ability", {"generic": 0}, effects=[Effect("gain_life", 1)],
                extra_costs={"tap_other": "Bird"},
                text="Tap an untapped Bird you control: You gain 1 life.")]), self.a)
        other_bird = self.perm(BIRD, self.a)
        self.assertTrue(self.g.can_activate(self.a, king, 0))
        self.assertTrue(self.g.activate_ability(self.a, king, 0))
        self.g.settle()
        self.assertTrue(other_bird.tapped)
        self.assertFalse(king.tapped)       # the cheaper donor was tapped, not the source
        self.assertEqual(self.a.life, 21)


class LairAnimateX(Chonk8):
    def setUp(self):
        super().setUp()
        self.lair = self.perm(dataclasses.replace(
            LAIR, activated=[Activated("animate", {"X": 1, "G": 1}, -1, -1,
                                       text="{X}{G}: Until end of turn, ~ becomes an X/X "
                                            "green Hydra creature. It's still a land.")]), self.a)
        self.land(self.a, 4, SWAMP)
        self.land(self.a, 3, card("Test Forest", types="Basic Land — Forest", text="({T}: Add {G}.)"))

    def test_animates_with_x_paid(self):
        self.assertTrue(self.g.activate(self.a, self.lair, "animate"))
        x = self.lair.animated.power
        self.assertGreaterEqual(x, 1)
        self.assertEqual((self.lair.animated.power, self.lair.animated.toughness), (x, x))
        self.assertEqual(self.lair.power, x)
        self.assertTrue(self.lair.is_creature)
        self.assertTrue(self.lair.card.is_land)      # still a land


class CovenCondition(Chonk8):
    def setUp(self):
        super().setUp()
        self.signpost = self.perm(dataclasses.replace(
            card("Test Signpost", "{1}{G}", "Creature — Human", "", 1, 2),
            activated=[Activated(
                "ability", {"generic": 1}, effects=[Effect("gain_life", 1)], condition="coven",
                text="{1}: You gain 1 life. Activate only if you control three or more "
                     "creatures with different powers.")]), self.a)
        self.land(self.a, 2)

    def test_needs_three_different_powers(self):
        self.assertFalse(self.g.can_activate(self.a, self.signpost, 0))
        self.perm(card("P2", "{1}{G}", "Creature — Elf", "", 2, 2), self.a)
        self.assertFalse(self.g.can_activate(self.a, self.signpost, 0))
        self.perm(card("P3", "{1}{G}", "Creature — Elf", "", 3, 3), self.a)
        self.assertTrue(self.g.can_activate(self.a, self.signpost, 0))


class ShimmerChosenLandType(Chonk8):
    def setUp(self):
        super().setUp()
        self.shimmer = dataclasses.replace(SHIMMER, choose_type="land",
                                           keyword_sub=(("@chosen", "phasing", False),))

    def test_lands_of_the_chosen_type_have_phasing(self):
        self.b.library = [ISLAND] * 20
        self.a.library = [SWAMP] * 20
        perm = self.g.enter_battlefield(self.a, self.shimmer)
        self.assertEqual(perm.chosen_type, "Island")   # the opponent's most common type
        opp_island = self.perm(ISLAND, self.b)
        my_swamp = self.perm(SWAMP, self.a)
        self.assertTrue(opp_island.has("phasing"))
        self.assertFalse(my_swamp.has("phasing"))

    def test_phasing_at_the_untap_step(self):
        self.b.library = [ISLAND] * 20
        self.g.enter_battlefield(self.a, self.shimmer)
        opp_island = self.perm(ISLAND, self.b)
        opp_island.tapped = True
        self.b.library = [ISLAND] * 20
        self.g.untap_step(self.b)
        self.assertNotIn(opp_island, self.b.battlefield)   # phased out
        self.g.untap_step(self.b)
        self.assertIn(opp_island, self.b.battlefield)      # and back in


class SetupBudget(unittest.TestCase):
    def test_budget_aborts_the_search_without_breaking_the_game(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        g = Game(a, b, random.Random(0), log=False)
        g.turn, g.step = 6, "main1"
        g.active_idx = 0
        land = Permanent(MOUNTAIN, a)
        land.sick = False
        a.battlefield.append(land)
        for _ in range(3):
            p = Permanent(BEAR, a)
            p.sick = False
            a.battlefield.append(p)
        a.hand = [card("Test Pump", "{R}", "Instant", "Target creature you control gets "
                       "+2/+2 until end of turn.")] * 4
        original = ai.SETUP_FIGHT_BUDGET
        ai.SETUP_FIGHT_BUDGET = 10
        try:
            self.assertFalse(HeuristicAI.lethal_setup(a.ai, g, a))   # aborted, not hung
            self.assertEqual(a.hand and len(a.hand), 4)               # nothing was cast
        finally:
            ai.SETUP_FIGHT_BUDGET = original
        # with the real budget the same setup search runs to completion
        HeuristicAI.lethal_setup(a.ai, g, a)
        self.assertIsNone(ai._fight_budget)                          # always disarmed


class AdversaryPayRepeat(Chonk8):
    def paid_card(self):
        return dataclasses.replace(ADVERSARY, triggers=[
            Trigger("etb", [Effect("adversary", data={"cost": {"generic": 2, "R": 1}})])])

    def test_pays_per_copy_and_counters(self):
        self.land(self.a, 8)
        self.a.graveyard = [SMALL_SPELL, MID_SPELL, SMALL_SPELL]
        perm = self.g.enter_battlefield(self.a, self.paid_card())
        self.g.settle()
        paid = perm.counters.get("+1/+1", 0)
        self.assertGreaterEqual(paid, 1)
        self.assertLessEqual(paid, 3)          # pay_repeat pays at most three times
        self.assertEqual(paid, len(self.a.exile))          # one graveyard card exiled per payment
        self.assertFalse(self.g.stack)                      # the copies resolved

    def test_no_mana_no_payment(self):
        self.a.graveyard = [MID_SPELL]
        perm = self.g.enter_battlefield(self.a, self.paid_card())
        self.g.settle()
        self.assertEqual(perm.counters.get("+1/+1", 0), 0)
        self.assertEqual(self.a.exile, [])


if __name__ == "__main__":
    unittest.main()

"""smol-chonk-5 batch 6, part 2: typed discard, named fetch, party, reveal/tap/arith X-quantities.

End-to-end checks for the parser templates of this batch against the engine halves already
on the branch base: the typed-discard trigger filters (Waste Not), "up to three cards
named ~" fetches (Squadron Hawk), the Dark Confidant reveal rider, Energy Tap's tap gate,
the Skullcrack life-gain ban scopes, Meddling Mage's choose_name, the "3 minus the number
of cards in their hand" arith X (Rackling), Candelabra's untap lands, the party X-quantity
and cost reduction, and the stay_tapped flag of the "choose not to untap" permanents.
"""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import _parse_effects, card_from_scryfall
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

BIG = card("Test Giant", "{4}", "Creature — Giant", "", 4, 5)     # cmc 4
SHOCK = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 1 damage to any target.")
BLAST = card("Test Blast", "{2}{R}", "Sorcery", "Test Blast deals 2 damage to any target.")

WASTE_NOT = card("Waste Not", "{1}{B}", "Enchantment",
                 "Whenever an opponent discards a creature card, create a 2/2 black Zombie "
                 "creature token.\nWhenever an opponent discards a land card, add {B}{B}.\n"
                 "Whenever an opponent discards a noncreature, nonland card, draw a card.")
HAWK = card("Squadron Hawk", "{1}{W}", "Creature — Bird",
            "Flying\nWhen Squadron Hawk enters, you may search your library for up to "
            "three cards named Squadron Hawk, reveal them, put them into your hand, then "
            "shuffle.")
CONFIDANT = card("Dark Confidant", "{1}{B}", "Creature — Human Wizard",
                 "At the beginning of your upkeep, reveal the top card of your library and "
                 "put that card into your hand. You lose life equal to its mana value.", 2, 1)
ENERGY_TAP = card("Energy Tap", "{U}", "Sorcery",
                  "Tap target untapped creature you control. If you do, add an amount of "
                  "{C} equal to that creature's mana value.")
SKULLCRACK = card("Skullcrack", "{1}{R}", "Instant",
                  "Players can't gain life this turn. Damage can't be prevented this turn. "
                  "Skullcrack deals 3 damage to target player or planeswalker.")
ATARKA = card("Atarka's Command", "{R}{G}", "Instant",
              "Choose two —\n• Your opponents can't gain life this turn.\n• Atarka's Command "
              "deals 3 damage to each opponent.\n• You may put a land card from your hand onto "
              "the battlefield.\n• Creatures you control get +1/+1 and gain reach until end of turn.")
MAGE = card("Meddling Mage", "{W}{U}", "Creature — Human Wizard",
            "As Meddling Mage enters, choose a nonland card name.\nSpells with the chosen "
            "name can't be cast.", 2, 2)
RACKLING = card("Rackling", "{4}", "Artifact Creature — Phyrexian Construct",
                "At the beginning of each opponent's upkeep, Rackling deals X damage to that "
                "player, where X is 3 minus the number of cards in their hand.", 2, 2)
IRON_MAIDEN = card("Iron Maiden", "{3}", "Artifact",
                   "At the beginning of each opponent's upkeep, Iron Maiden deals X damage "
                   "to that player, where X is the number of cards in their hand minus 4.")
CANDELABRA = card("Candelabra of Tawnos", "{1}", "Artifact", "{X}, {T}: Untap X target lands.")
PRIZE = card("Coveted Prize", "{4}{B}", "Sorcery",
             "This spell costs {1} less to cast for each creature in your party.\nSearch your "
             "library for a card, put it into your hand, then shuffle. If you have a full "
             "party, you may cast a spell with mana value 4 or less from your hand without "
             "paying its mana cost.")
EXPERT = card("Acquisitions Expert", "{1}{B}", "Creature — Human Rogue",
              "When Acquisitions Expert enters, target opponent reveals a number of cards "
              "from their hand equal to the number of creatures in your party. You choose "
              "one of those cards. That player discards that card.", 2, 2)
COMMANDER = card("Squad Commander", "{3}{W}", "Creature — Kor Warrior",
                 "When Squad Commander enters, create a 1/1 white Kor Warrior creature token "
                 "for each creature in your party.", 2, 2)
AMBER_PRISON = card("Amber Prison", "{4}", "Artifact",
                    "You may choose not to untap Amber Prison during your untap step.\n{4}, "
                    "{T}: Tap target artifact, creature, or land. That permanent doesn't untap "
                    "during its controller's untap step for as long as Amber Prison remains tapped.")
FLOE = card("Test Floe", "", "Land",
            "You may choose not to untap Test Floe during your untap step.\n{T}: Add {C}.")

CLERIC = card("Test Cleric", "{1}{W}", "Creature — Human Cleric", "", 1, 1)
ROGUE = card("Test Rogue", "{1}{B}", "Creature — Human Rogue", "", 1, 1)
WARRIOR = card("Test Warrior", "{1}{R}", "Creature — Human Warrior", "", 1, 1)


class Chonk5Templates(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        self.g.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def perm(self, c, owner=None):
        perm = Permanent(c, owner or self.a)
        perm.sick, perm.tapped = False, False
        (owner or self.a).battlefield.append(perm)
        return perm

    def land(self, p, n, c=MOUNTAIN):
        for _ in range(n):
            land = Permanent(c, p)
            land.sick = False
            p.battlefield.append(land)

    def trigger_effects(self, cdef, event=None):
        return [e for t in cdef.triggers if event is None or t.event == event for e in t.effects]


class TypedDiscard(Chonk5Templates):
    def test_parse(self):
        self.assertEqual(WASTE_NOT.unsupported, [])
        self.assertEqual([(t.event, t.filter) for t in WASTE_NOT.triggers],
                         [("opp_discard", "creature card"), ("opp_discard", "land card"),
                          ("opp_discard", "noncreature, nonland card")])

    def fire_discard(self, discarded):
        self.b.hand = [discarded]
        self.b.graveyard = []
        self.g.discard_card(self.b, discarded)
        self.g.settle()

    def test_creature_discard_makes_a_zombie(self):
        self.perm(WASTE_NOT)
        self.fire_discard(BEAR)
        self.assertEqual(sum(x.card.name.startswith("Zombie") for x in self.a.battlefield), 1)
        self.assertEqual(len(self.a.pool), 0)         # the land rider did not fire

    def test_land_discard_adds_mana(self):
        self.perm(WASTE_NOT)
        self.fire_discard(ISLAND)
        self.assertEqual(len(self.a.pool), 2)
        self.assertEqual(sum(x.card.name.startswith("Zombie") for x in self.a.battlefield), 0)

    def test_noncreature_nonland_discard_draws(self):
        self.perm(WASTE_NOT)
        hand = len(self.a.hand)
        self.fire_discard(SHOCK)
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_no_trigger_fires_for_the_wrong_type(self):
        self.perm(WASTE_NOT)
        hand = len(self.a.hand)
        self.fire_discard(ISLAND)
        self.assertEqual(len(self.a.hand), hand)      # the draw rider is noncreature, nonland


class NamedFetch(Chonk5Templates):
    def test_parse(self):
        self.assertEqual(HAWK.unsupported, [])

    def test_fetches_up_to_three_cards_of_the_same_name(self):
        self.a.library = [ISLAND] * 5 + [HAWK, BIG, HAWK, ISLAND, HAWK]
        self.a.hand = []
        effects = self.trigger_effects(HAWK)
        item = StackItem(self.a, effects, [None] * len(effects), source=self.perm(HAWK),
                         kind="trigger")
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertEqual([c.name for c in self.a.hand], ["Squadron Hawk"] * 3)


class Confidant(Chonk5Templates):
    def test_reveal_rider_loses_the_revealed_mana_value(self):
        self.a.library = [ISLAND] * 5 + [BIG]
        life = self.a.life
        effects = self.trigger_effects(CONFIDANT)
        item = StackItem(self.a, effects, [None] * len(effects), source=self.perm(CONFIDANT),
                         kind="trigger")
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertEqual(len(self.a.hand), 1)         # the BIG revealed into the hand
        self.assertEqual(self.a.life, life - BIG.cmc)


class EnergyTap(Chonk5Templates):
    def test_tap_gate_pays_out_the_mana_value(self):
        engine5 = self.perm(BIG)
        self.assertEqual(ENERGY_TAP.unsupported, [])
        item = StackItem(self.a, list(ENERGY_TAP.spell_effects),
                         [None] * len(ENERGY_TAP.spell_effects), card=ENERGY_TAP, kind="spell")
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertTrue(engine5.tapped)
        self.assertEqual(len(self.a.pool), BIG.cmc)

    def test_no_untapped_creature_no_mana(self):
        engine5 = self.perm(BIG)
        engine5.tapped = True
        item = StackItem(self.a, list(ENERGY_TAP.spell_effects),
                         [None] * len(ENERGY_TAP.spell_effects), card=ENERGY_TAP, kind="spell")
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertEqual(len(self.a.pool), 0)


class NoLifegainTurn(Chonk5Templates):
    def test_skullcrack_blocks_everyones_gains(self):
        self.assertEqual(SKULLCRACK.unsupported, [])
        eff = next(e for e in SKULLCRACK.spell_effects if e.kind == "no_lifegain_turn")
        self.assertEqual(eff.data["scope"], "all")
        self.g.resolve(self.a, eff, None, StackItem(self.a, [eff], [None]))
        for p, life in ((self.a, self.a.life), (self.b, self.b.life)):
            self.g.change_life(p, 2, "test gain")
            self.assertEqual(p.life, life)

    def test_atarkas_opponents_scope(self):
        (mode,) = [m for m in ATARKA.modes if any(e.kind == "no_lifegain_turn" for e in m)]
        eff = next(e for e in mode if e.kind == "no_lifegain_turn")
        self.assertEqual(eff.data["scope"], "opponents")
        self.g.resolve(self.a, eff, None, StackItem(self.a, [eff], [None]))
        self.g.change_life(self.a, 2, "test gain")
        self.assertEqual(self.a.life, 22)              # the caster may still gain
        self.g.change_life(self.b, 2, "test gain")
        self.assertEqual(self.b.life, 20)


class ChooseName(Chonk5Templates):
    def test_parse_and_ban(self):
        self.assertEqual(MAGE.unsupported, [])
        self.g.active_idx = 1                       # b may cast in their main phase
        self.land(self.b, 3)
        self.b.deck = [BLAST] * 4 + [BEAR]
        self.b.hand = [BLAST]
        mage = self.perm(MAGE)
        self.assertTrue(self.g.can_cast_now(self.b, BLAST))   # no name chosen yet
        effects = self.trigger_effects(MAGE)
        item = StackItem(self.a, effects, [None] * len(effects), source=mage, kind="trigger")
        self.g.resolve(self.a, effects[0], None, item)
        self.assertEqual(mage.chosen_name, "Test Blast")      # 4 copies beat one Bear
        self.assertFalse(self.g.can_cast_now(self.b, BLAST))
        self.a.battlefield.remove(mage)                      # leaving lifts the ban
        self.assertTrue(self.g.can_cast_now(self.b, BLAST))


class ArithWhereX(Chonk5Templates):
    def resolve_upkeep(self, cdef, hand):
        self.b.hand = list(hand)
        effects = self.trigger_effects(cdef)
        item = StackItem(self.a, effects, [None] * len(effects), context=self.b, kind="trigger")
        self.g.stack.append(item)
        self.g.resolve_top()

    def test_rackling_is_three_minus_their_hand(self):
        self.assertEqual(RACKLING.unsupported, [])
        life = self.b.life
        self.resolve_upkeep(RACKLING, [ISLAND, ISLAND, ISLAND])
        self.assertEqual(self.b.life, life - 0)      # 3 - 3 cards

    def test_rackling_damage_grows_on_an_empty_hand(self):
        life = self.b.life
        self.resolve_upkeep(RACKLING, [])
        self.assertEqual(self.b.life, life - 3)

    def test_iron_maiden_floors_at_zero(self):
        self.assertEqual(IRON_MAIDEN.unsupported, [])
        life = self.b.life
        self.resolve_upkeep(IRON_MAIDEN, [ISLAND, ISLAND])
        self.assertEqual(self.b.life, life)          # 2 - 4 floors at 0


class UntapXLands(Chonk5Templates):
    def test_candelabra_untaps_x_lands(self):
        self.assertEqual(CANDELABRA.unsupported, [])
        candelabra = self.perm(CANDELABRA)
        lands = []
        self.land(self.a, 5)
        lands = [x for x in self.a.battlefield if x.card.is_land]
        for x in lands[:3]:
            x.tapped = True
        # {X} paid with the two untapped Mountains: X = 2 untaps two of the three tapped lands
        self.assertTrue(self.g.can_activate(self.a, candelabra, 0, x=2))
        self.assertTrue(self.g.activate_ability(self.a, candelabra, 0, x=2))
        self.assertEqual([x.tapped for x in lands[:3]], [False, False, True])
        self.assertTrue(candelabra.tapped)


class Party(Chonk5Templates):
    def party(self):
        self.perm(CLERIC)
        self.perm(ROGUE)
        self.perm(WARRIOR)

    def test_coveted_prize_cost_reduction(self):
        self.assertEqual(PRIZE.cost_reduction, "party")
        self.assertEqual(self.g.cost_of(self.a, PRIZE)["generic"], 4)
        self.party()
        self.assertEqual(self.g.cost_of(self.a, PRIZE)["generic"], 1)   # {4}{B} - three members

    def test_squad_commander_makes_a_token_per_member(self):
        self.assertEqual(COMMANDER.unsupported, [])
        self.party()
        effects = self.trigger_effects(COMMANDER)
        item = StackItem(self.a, effects, [None] * len(effects), source=self.perm(COMMANDER),
                         kind="trigger")
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertEqual(sum(x.card.name.startswith("Kor Warrior") for x in self.a.battlefield), 3)

    def test_acquisitions_expert_discards_party_many_cards(self):
        self.assertEqual(EXPERT.unsupported, [])
        self.party()
        self.b.hand = [ISLAND] * 5
        effects = self.trigger_effects(EXPERT)
        item = StackItem(self.a, effects, [self.b], source=self.perm(EXPERT), kind="trigger")
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertEqual(len(self.b.hand), 2)         # party of 3: three cards discarded

    def test_for_each_party_rider_scales_the_base_effect(self):
        self.party()
        effects, bad = _parse_effects("you gain 2 life for each creature in your party")
        self.assertEqual(bad, [])
        self.assertEqual([(e.kind, e.amount, e.data.get("xq")) for e in effects],
                         [("gain_life", 2, ("party",))])
        item = StackItem(self.a, effects, [None])
        self.g.resolve(self.a, effects[0], None, item)
        self.assertEqual(self.a.life, 26)


class StayTapped(Chonk5Templates):
    def test_choose_not_to_untap_sets_the_flag(self):
        self.assertTrue(AMBER_PRISON.stay_tapped)
        # the "as long as ~ remains tapped" freeze ability is still an open engine gap
        self.assertTrue(any("remains tapped" in u for u in AMBER_PRISON.unsupported))

    def test_storage_lands_keep_their_own_hold_rule(self):
        # storage.parse_line consumes the line for lands: no stay_tapped flag is set
        self.assertFalse(FLOE.stay_tapped)


if __name__ == "__main__":
    unittest.main()


class RealCards(unittest.TestCase):
    """The real Scryfall wordings of this batch's queue cards, from the built card DB."""

    FULLY_SUPPORTED = [
        "Waste Not", "Squadron Hawk", "Howling Wolf", "Screaming Seahawk", "Dark Confidant",
        "Dark Tutelage", "Pain Seer", "Energy Tap", "Skullcrack", "Atarka's Command",
        "Meddling Mage", "Nevermore", "Rackling", "Iron Maiden", "Candelabra of Tawnos",
        "Magus of the Candelabra", "Acquisitions Expert", "Broadside Bombardiers",
        "Makeshift Mauler", "Corpse Lunge", "Molten-Tail Masticore", "Moorland Haunt",
        "Graveyard Marshal", "Architect of the Untamed", "Gonti's Aether Heart",
        "Roil Cartographer", "Stone Idol Generator", "Aethersquall Ancient",
        "Aethertorch Renegade", "Lathnu Hellion", "Electrozoa", "Static Prison",
        "Liberty Prime, Recharged",
    ]

    def card(self, name):
        import json
        import sqlite3
        row = sqlite3.connect("mtgsim/data/cards.sqlite3").execute(
            "select data from cards where name = ?", (name,)).fetchone()
        if row is None:                                   # card DB not built: skip
            self.skipTest("cards.sqlite3 is missing")
        return card_from_scryfall(json.loads(row[0]))

    def test_fully_supported_queue_cards(self):
        for name in self.FULLY_SUPPORTED:
            with self.subTest(card=name):
                cdef = self.card(name)
                self.assertEqual(cdef.unsupported, [])

    def test_partial_cards_keep_their_remaining_gaps_visible(self):
        # multi-card exile costs stay approximate; the hold items stay unsupported
        ruinator = self.card("Skaab Ruinator")
        self.assertIn("You may cast this card from your graveyard.", ruinator.unsupported)
        self.assertTrue(any("instead of three" in a for a in ruinator.approximations))
        oculus = self.card("Abhorrent Oculus")
        self.assertTrue(any("instead of six" in a for a in oculus.approximations))
        commander = self.card("Squad Commander")
        self.assertTrue(any("full party" in u for u in commander.unsupported))
        prize = self.card("Coveted Prize")
        self.assertEqual(prize.cost_reduction, "party")
        self.assertTrue(any("full party" in u for u in prize.unsupported))
        # Psychatog's "Exile two cards from your graveyard" needs multi-exile engine support
        tog = self.card("Psychatog")
        self.assertTrue(any("Exile two cards" in u for u in tog.unsupported))
        # the tap-another-creature ability cost has no engine half yet
        for name, needle in (("Ranger's Hawk", "Tap another untapped creature"),
                             ("Dungeon Descent", "Tap an untapped legendary creature"),
                             ("Chicken à la King", "Tap an untapped Bird")):
            with self.subTest(card=name):
                self.assertTrue(any(needle in u for u in self.card(name).unsupported))
        # Acererak's completed-dungeon gate now parses to "!dungeon_complete" (any-dungeon
        # narrowing recorded as an approximation note); the per-opponent Zombie attack
        # line is the remaining gap.
        acererak = self.card("Acererak the Archlich")
        self.assertTrue(any("for each opponent" in u for u in acererak.unsupported))
        self.assertTrue(any("Tomb of Annihilation" in a for a in acererak.approximations))

    def test_stay_tapped_flag_on_real_cards(self):
        self.assertTrue(self.card("Amber Prison").stay_tapped)
        self.assertTrue(self.card("Giant Oyster").stay_tapped)
        self.assertFalse(self.card("Maze of Shadows").stay_tapped)   # a land: storage's own rule

"""Oracle-text templates for current Standard: activated abilities, restricted mana, land
conditions and the effects they use. Card text is written out so the tests don't need the card DB."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Game, Permanent, Player, can_block, card_matches


def card(name, cost="", types="Creature — Human", text="", power=None, toughness=None, cmc=None):
    data = {"name": name, "mana_cost": cost, "type_line": types, "oracle_text": text,
            "cmc": cmc if cmc is not None else sum(int(x) if x.isdigit() else 1
                                                   for x in cost.strip("{}").split("}{") if x)}
    if power is not None:
        data.update(power=str(power), toughness=str(toughness))
    return card_from_scryfall(data)


ISLAND = card("Island", types="Basic Land — Island", text="({T}: Add {U}.)")
PLAINS = card("Plains", types="Basic Land — Plains", text="({T}: Add {W}.)")
MOUNTAIN = card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")
BEAR = card("Grizzly Bears", "{1}{G}", "Creature — Bear", "", 2, 2)
DRAGON = card("Test Dragon", "{1}{R}", "Creature — Dragon", "Flying", 2, 2)
DRAGON3 = card("Big Dragon", "{2}{R}", "Creature — Dragon", "Flying", 3, 3)
SHOCK = card("Shock", "{R}", "Instant", "Shock deals 2 damage to any target.")
COUNTERSPELL = card("Counterspell", "{U}{U}", "Instant", "Counter target spell.")
CAVERN = card("Cavern of Souls", types="Land", text=(
    "As Cavern of Souls enters, choose a creature type.\n{T}: Add {C}.\n{T}: Add one mana of any color. Spend "
    "this mana only to cast a creature spell of the chosen type, and that spell can't be countered."))
ROCKFACE = card("Rockface Village", types="Land", text=(
    "{T}: Add {C}.\n{T}: Add {R}. Spend this mana only to cast a creature spell."))
TEMPLE = card("Abandoned Air Temple", types="Land", text=(
    "This land enters tapped unless you control a basic land.\n{T}: Add {W}.\n{3}{W}, {T}: Put a +1/+1 counter "
    "on each creature you control."))
CANDY = card("Candy Trail", "{1}", "Artifact — Food Clue", "When this artifact enters, scry 2.\n{2}, {T}, "
             "Sacrifice this artifact: You gain 3 life and draw a card.")
PROWLER = card("Desolation Prowler", "{2}{B}", "Creature — Horror", "Pay 2 life: This creature gets +2/+2 until "
               "end of turn. Activate only once each turn.", 2, 2)
MINER = card("Forsaken Miner", "{B}", "Creature — Skeleton Rogue", "This creature can't block.", 2, 2)
CONQUEROR = card("Clarion Conqueror", "{2}{W}", "Creature — Dragon", "Flying\nActivated abilities of artifacts, "
                 "creatures, and planeswalkers can't be activated.", 3, 3)
TREASURE_MAKER = card("Fountainport", types="Land", text=(
    "{T}: Add {C}.\n{4}, {T}: Create a Treasure token."))
MAELSTROM = card("Maelstrom of the Spirit Dragon", types="Land", text=(
    "{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast a Dragon spell or an Omen "
    "spell.\n{4}, {T}, Sacrifice this land: Search your library for a Dragon card, reveal it, put it into your "
    "hand, then shuffle."))
SANCTUM = card("Theorist's Sanctum", types="Land", text=(
    "As this land enters, you may behold a Jace. If you don't, this land enters tapped.\n{T}: Add {U}."))


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [DRAGON] * 10 + [BEAR] * 2, HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn = 1
        self.game.step = "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner, sick=False):
        p = Permanent(c, owner)
        p.sick, p.tapped = sick, False
        owner.battlefield.append(p)
        return p


class TemplateTests(Base):
    # ------------------------------------------------------- parsing
    def test_templates_match_every_line(self):
        for c in (CAVERN, ROCKFACE, TEMPLE, CANDY, PROWLER, MINER, CONQUEROR, TREASURE_MAKER, MAELSTROM, SANCTUM):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual(CAVERN.choose_type, "creature")
        self.assertEqual(ROCKFACE.mana_restriction, "creature")
        self.assertEqual(MAELSTROM.mana_restriction, "subtype:Dragon|Omen")
        self.assertEqual(TEMPLE.tapped_condition, "unless_control:basic")
        self.assertEqual(SANCTUM.tapped_condition, "behold:Jace")
        self.assertTrue(MINER.cant_block)
        act = CANDY.activated[0]
        self.assertEqual((act.cost, act.extra_costs), ({"generic": 2}, {"tap": True, "sac_self": True}))
        self.assertEqual([e.kind for e in act.effects], ["gain_life", "draw"])
        self.assertTrue(PROWLER.activated[0].once)
        self.assertEqual(DRAGON.subtypes, frozenset({"Dragon"}))

    def test_cavern_of_souls_pays_only_for_chosen_type_and_stops_counters(self):
        self.game.enter_battlefield(self.a, CAVERN)
        cavern = self.a.battlefield[0]
        cavern.tapped = False
        self.assertEqual(cavern.chosen_type, "Dragon")     # the deck's most common creature type
        self.perm(MOUNTAIN, self.a)
        self.a.hand = [DRAGON, BEAR, SHOCK]
        self.assertTrue(self.game.can_cast_now(self.a, DRAGON))
        self.assertFalse(self.game.can_cast_now(self.a, BEAR))      # needs {G}: Cavern only for Dragons
        self.assertTrue(self.game.can_cast_now(self.a, SHOCK))      # Mountain
        for _ in range(2):
            self.perm(ISLAND, self.b)
        self.b.hand = [COUNTERSPELL]
        self.game.cast(self.a, DRAGON)
        self.assertIn("Test Dragon", [c.card.name for c in self.a.creatures])
        self.assertEqual(self.b.hand, [COUNTERSPELL])

    def test_restricted_mana_is_not_spent_on_other_spells_or_abilities(self):
        self.perm(ROCKFACE, self.a)
        self.assertTrue(self.game.can_pay(self.a, {"R": 1}, spell=DRAGON))
        self.assertFalse(self.game.can_pay(self.a, {"R": 1}, spell=SHOCK))
        self.assertFalse(self.game.can_pay(self.a, {"R": 1}, spell="ability"))
        self.assertTrue(self.game.can_pay(self.a, {"generic": 1}, spell=SHOCK))     # its {C}
        self.perm(MAELSTROM, self.a)
        self.assertTrue(self.game.can_pay(self.a, {"R": 2}, spell=DRAGON))

    def test_lands_enter_tapped_unless_condition(self):
        self.game.enter_battlefield(self.a, TEMPLE)
        self.assertTrue(self.a.battlefield[-1].tapped)
        self.perm(ISLAND, self.a)
        self.game.enter_battlefield(self.a, TEMPLE)
        self.assertFalse(self.a.battlefield[-1].tapped)
        self.game.enter_battlefield(self.a, SANCTUM)
        self.assertTrue(self.a.battlefield[-1].tapped)
        self.a.hand = [card("Jace, Test", "{2}{U}", "Legendary Planeswalker — Jace", "")]
        self.game.enter_battlefield(self.a, SANCTUM)
        self.assertFalse(self.a.battlefield[-1].tapped)

    def test_cant_block(self):
        miner = self.perm(MINER, self.b)
        bear = self.perm(BEAR, self.a)
        self.assertFalse(can_block(miner, bear))
        self.assertTrue(can_block(bear, miner))

    def test_activated_ability_costs_and_effects(self):
        for _ in range(2):
            self.perm(ISLAND, self.a)
        candy = self.perm(CANDY, self.a)
        self.a.life = 10
        self.assertTrue(self.game.activate(self.a, candy, "ability:0"))
        self.assertEqual(self.a.life, 13)
        self.assertEqual(len(self.a.hand), 1)
        self.assertNotIn(candy, self.a.battlefield)
        self.assertFalse(self.game.activate(self.a, candy, "ability:0"))

    def test_once_each_turn_and_combat_pump(self):
        prowler = self.perm(PROWLER, self.a)
        self.assertTrue(self.game.activate(self.a, prowler, "ability:0"))
        self.assertEqual((prowler.power, self.a.life), (4, 18))
        self.assertFalse(self.game.activate(self.a, prowler, "ability:0"))
        self.game.turn += 2
        self.game.step = "declare_blockers"
        self.game.attackers = [prowler]
        self.assertEqual(self.game.hook(self.a, "respond_extras")(self.game, self.a), ("activate", prowler, "ability:0"))

    def test_ai_uses_abilities_with_spare_mana(self):
        for _ in range(5):
            self.perm(ISLAND, self.a)
        port = self.perm(TREASURE_MAKER, self.a)
        self.game.step = "main2"
        self.game.hook(self.a, "use_abilities")(self.game, self.a)
        self.assertTrue(port.tapped)
        self.assertEqual(sum(x.card.token_kind == "treasure" for x in self.a.battlefield), 1)

    def test_clarion_conqueror_stops_artifact_and_creature_abilities(self):
        for _ in range(4):
            self.perm(ISLAND, self.a)
        candy = self.perm(CANDY, self.a)
        self.game.create_token(self.a, card_from_scryfall({"name": "x", "type_line": "Instant", "oracle_text":
                                                           "Create a Treasure token."}).spell_effects[0])
        n = len(self.game.mana_sources(self.a))
        self.perm(CONQUEROR, self.b)
        self.assertEqual(len(self.game.mana_sources(self.a)), n - 1)    # the Treasure
        self.assertFalse(self.game.activate(self.a, candy, "ability:0"))

    def test_tutor_and_mass_effects(self):
        self.a.library = [ISLAND] * 5 + [DRAGON3]
        for _ in range(4):
            self.perm(ISLAND, self.a)
        maelstrom = self.perm(MAELSTROM, self.a)
        self.assertTrue(self.game.activate(self.a, maelstrom, "ability:0"))
        self.assertEqual(self.a.hand, [DRAGON3])
        self.assertTrue(card_matches(ISLAND, "a basic Island card"))
        self.assertTrue(card_matches(DRAGON, "a basic Plains card or a creature card with mana value 2 or less"))
        self.assertFalse(card_matches(DRAGON3, "a basic Plains card or a creature card with mana value 2 or less"))
        bear, bear2 = self.perm(BEAR, self.a), self.perm(BEAR, self.a)
        self.perm(PLAINS, self.a)
        temple = self.perm(TEMPLE, self.a)
        for x in self.a.battlefield:
            x.tapped = False
        self.assertTrue(self.game.activate(self.a, temple, "ability:0"))
        self.assertEqual((bear.power, bear2.toughness), (3, 3))
        anthem = card("Rally", "{W}", "Instant", "Creatures you control get +1/+0 and gain trample until end of turn.")
        self.assertEqual(anthem.unsupported, [])
        self.game.resolve(self.a, anthem.spell_effects[0], None)
        self.assertEqual(bear.power, 4)
        self.assertTrue(bear.has("trample"))



BOOTS = card("Lavaspur Boots", "{1}", "Artifact — Equipment",
             "Equipped creature gets +1/+0 and has haste and ward {1}.\nEquip {1}")
AXE = card("Leyline Axe", "{4}", "Artifact — Equipment", "If this card is in your opening hand, you may begin the "
           "game with it on the battlefield.\nEquipped creature gets +1/+1 and has double strike and trample.\n"
           "Equip {3}")
MAULER = card("Dwarven Mauler", "{3}{R}", "Creature — Dwarf Berserker", "Trample\nEquip abilities you activate "
              "that target this creature cost {2} less to activate.", 4, 3)
COMPANY = card("Dain's Company", "{1}{R}", "Creature — Dwarf Warrior", "This creature has lifelink as long as you "
               "control another Dwarf.", 2, 2)
GHAST = card("Bloodghast", "{B}{B}", "Creature — Vampire Spirit", "Bloodghast has haste as long as an opponent "
             "has 10 or less life.", 2, 1)
KILI = card("Kili", "{1}{R}", "Legendary Creature — Dwarf", "Whenever another Dwarf or Equipment you control "
            "enters, draw a card. This ability triggers only once each turn.", 2, 2)
SANCTIFIER = card("Hinterland Sanctifier", "{W}", "Creature — Rabbit Cleric",
                  "Whenever another creature you control enters, you gain 1 life.", 1, 2)


class EquipmentTests(Base):
    def test_parsing(self):
        for c in (BOOTS, AXE, MAULER, COMPANY, GHAST, KILI, SANCTIFIER):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual((BOOTS.equip_cost, BOOTS.equip_bonus, BOOTS.equip_ward), ({"generic": 1}, (1, 0), 1))
        self.assertTrue(AXE.leyline)

    def test_equip_gives_stats_and_keywords_and_falls_off(self):
        for _ in range(4):
            self.perm(MOUNTAIN, self.a)
        axe = self.perm(AXE, self.a)
        mauler = self.perm(MAULER, self.a)
        self.assertTrue(self.game.equip(self.a, axe, mauler))
        self.assertEqual(sum(x.tapped for x in self.a.battlefield), 1)     # {3} minus Mauler's {2}
        self.assertEqual((mauler.power, mauler.toughness), (5, 4))
        self.assertTrue(mauler.has("double strike"))
        self.game.destroy(mauler)
        self.assertIsNone(axe.attached_to)
        self.assertIn(axe, self.a.battlefield)

    def test_default_policy_equips_before_combat(self):
        for _ in range(2):
            self.perm(MOUNTAIN, self.a)
        boots = self.perm(BOOTS, self.a)
        bear = self.perm(BEAR, self.a, sick=True)
        self.game.hook(self.a, "use_abilities")(self.game, self.a)
        self.assertIs(boots.attached_to, bear)
        self.assertTrue(bear.can_attack())          # haste from the Boots
        self.assertEqual(bear.ward, 1)

    def test_leyline_starts_on_battlefield(self):
        self.a.deck = [AXE] * 30
        self.b.deck = [ISLAND] * 30
        self.game.setup()
        self.assertGreaterEqual(sum(x.card.name == "Leyline Axe" for x in self.a.battlefield), 1)

    def test_conditional_keywords(self):
        company = self.perm(COMPANY, self.a)
        self.assertFalse(company.has("lifelink"))
        self.perm(MAULER, self.a)
        self.assertTrue(company.has("lifelink"))
        ghast = self.perm(GHAST, self.a)
        self.assertFalse(ghast.has("haste"))
        self.b.life = 10
        self.assertTrue(ghast.has("haste"))

    def test_enters_triggers_with_type_filter_and_once_per_turn(self):
        self.perm(KILI, self.a)
        self.perm(SANCTIFIER, self.a)
        self.game.enter_battlefield(self.a, MAULER)
        self.game.enter_battlefield(self.a, BOOTS)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)           # once each turn
        self.assertEqual(self.a.life, 21)               # Mauler, not the Boots

    def test_dig_with_filter_and_lands(self):
        company = card("Dain's Company", "{1}{R}", "Creature — Dwarf", "When this creature enters, look at the top "
                       "four cards of your library. You may reveal a Dwarf or Equipment card from among them and put "
                       "it into your hand. Put the rest on the bottom of your library in a random order.", 2, 2)
        charts = card("Consult the Star Charts", "{1}{U}", "Instant", "Kicker {1}{U}\nLook at the top X cards of "
                      "your library, where X is the number of lands you control. Put one of those cards into your "
                      "hand. If this spell was kicked, put two of those cards into your hand instead. Put the rest "
                      "on the bottom of your library in a random order.")
        self.assertEqual(company.unsupported, [])
        self.a.library = [BEAR, BOOTS, ISLAND, ISLAND]
        self.game.enter_battlefield(self.a, company)
        self.game.settle()
        self.assertEqual(self.a.hand, [BOOTS])
        self.assertEqual(charts.unsupported, [])
        self.assertEqual([a.effects[0].amount2 for a in charts.alt_costs], [2])


    def test_removal_keeps_tapped_restriction(self):
        lullaby = card("Eriette's Lullaby", "{1}{W}", "Sorcery", "Destroy target tapped creature. You gain 2 life.")
        self.assertEqual(lullaby.spell_effects[0].filter, "tapped")



SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
DECEIT = card("Deceit", "{4}{U/B}{U/B}", "Creature — Elemental Incarnation", (
    "When this creature enters, if {U}{U} was spent to cast it, return up to one other target nonland permanent to "
    "its owner's hand.\nWhen this creature enters, if {B}{B} was spent to cast it, target opponent reveals their "
    "hand. You choose a nonland card from it. That player discards that card.\nEvoke {U/B}{U/B}"), 5, 5, cmc=6)
RIDDLER = card("Quantum Riddler", "{3}{U}{U}", "Creature — Sphinx", "Flying\nWhen this creature enters, draw a "
               "card.\nWarp {1}{U}", 4, 6)
VINELASHER = card("Iridescent Vinelasher", "{B}", "Creature — Lizard Assassin", "Offspring {2}\nLandfall — "
                  "Whenever a land you control enters, this creature deals 1 damage to target opponent.", 1, 2)
SHOWOFF = card("Slickshot Show-Off", "{1}{R}", "Creature — Bird Wizard", "Flying, haste\nPlot {1}{R}", 1, 2)
STEPS = card("Three Steps Ahead", "{U}", "Instant", "Spree\n+ {1}{U} — Counter target spell.\n+ {2} — Draw two "
             "cards, then discard a card.")
CRITIQUE = card("Traumatic Critique", "{X}{2}{R}", "Instant", "Traumatic Critique deals X damage to any target. "
                "Draw two cards, then discard a card.", cmc=3)
HYDRA = card("Guiding Hydra", "{X}{G}", "Creature — Hydra", "This creature enters with X +1/+1 counters on it.",
             0, 0, cmc=1)


class CostTests(Base):
    def test_parsing(self):
        for c in (DECEIT, RIDDLER, VINELASHER, SHOWOFF, STEPS, CRITIQUE, HYDRA):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual(DECEIT.hybrid, ("UB", "UB"))
        self.assertEqual(DECEIT.spent_colors, frozenset("UB"))

    def test_evoke_with_mana_spent_mode(self):
        for _ in range(2):
            self.perm(SWAMP, self.a)
        self.b.hand = [BEAR, ISLAND]
        self.a.hand = [DECEIT]
        names = [c.name for c in self.game.spell_options(self.a)]
        self.assertIn("Deceit (evoke_B)", names)
        evoke = next(c for c in self.game.spell_options(self.a) if c.name == "Deceit (evoke_B)")
        self.assertTrue(self.game.can_cast_now(self.a, evoke))
        self.game.cast(self.a, evoke)
        self.game.settle()
        self.assertEqual(self.b.hand, [ISLAND])          # the B trigger
        self.assertIn(DECEIT, self.a.graveyard)           # sacrificed

    def test_warp_exiles_and_returns_later(self):
        for _ in range(2):
            self.perm(ISLAND, self.a)
        self.a.hand = [RIDDLER]
        warp = next(c for c in self.game.spell_options(self.a) if c.name.endswith("(warp)"))
        self.game.cast(self.a, warp)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)             # drew a card
        self.a.library = [ISLAND] * 10
        self.game.step = "end_step"
        perm = self.a.creatures[0]
        self.assertTrue(perm.warped)
        # The end step exiles it; on a later turn it can be cast from exile.
        self.a.ai.choose_attackers = lambda g, me, opp: []
        self.b.ai.choose_attackers = lambda g, me, opp: []
        self.a.ai.main_phase = lambda g, me: None
        self.game.take_turn(self.a)
        self.assertEqual(self.a.warp_exile, [RIDDLER])
        self.game.turn += 1
        self.assertIn("Quantum Riddler (from_warp)", [c.name for c in self.game.spell_options(self.a)])

    def test_offspring_makes_a_token_copy(self):
        for _ in range(3):
            self.perm(SWAMP, self.a)
        self.a.hand = [VINELASHER]
        off = next(c for c in self.game.spell_options(self.a) if c.name.endswith("(offspring)"))
        self.game.cast(self.a, off)
        self.game.settle()
        self.assertEqual(sorted((c.card.name, c.power) for c in self.a.creatures),
                         [("Iridescent Vinelasher", 1), ("Iridescent Vinelasher token", 1)])
        self.game.enter_battlefield(self.a, SWAMP)
        self.game.settle()
        self.assertEqual(self.b.life, 18)                 # both landfall triggers

    def test_plot_then_cast_free(self):
        for _ in range(2):
            self.perm(MOUNTAIN, self.a)
        self.a.hand = [SHOWOFF]
        self.assertTrue(self.game.plot(self.a, SHOWOFF))
        self.assertEqual(self.game.spell_options(self.a), [])
        self.game.turn += 2
        for x in self.a.battlefield:
            x.tapped = True
        plotted = self.game.spell_options(self.a)[0]
        self.assertTrue(self.game.can_cast_now(self.a, plotted))
        self.game.cast(self.a, plotted)
        self.assertEqual(self.a.creatures[0].card.name, "Slickshot Show-Off")

    def test_spree_and_x(self):
        self.a.hand = [STEPS]
        self.assertEqual(sorted(c.name for c in self.game.spell_options(self.a)),
                         ["Three Steps Ahead (spree_1)", "Three Steps Ahead (spree_2)", "Three Steps Ahead (spree_3)"])
        both = next(c for c in self.game.spell_options(self.a) if c.name.endswith("_3)"))
        self.assertEqual(both.mana_cost, {"generic": 3, "U": 2})
        for _ in range(5):
            self.perm(MOUNTAIN, self.a)
        self.a.hand = [CRITIQUE]
        self.game.cast(self.a, CRITIQUE, [self.b])
        self.game.settle()
        self.assertEqual(self.b.life, 18)                  # X = 2
        for _ in range(4):
            self.perm(card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)"), self.a)
        self.a.hand = [HYDRA]
        self.game.cast(self.a, HYDRA)
        self.assertEqual(self.a.creatures[0].power, 3)


if __name__ == "__main__":
    unittest.main()

"""Oracle-text templates for current Standard: activated abilities, restricted mana, land
conditions and the effects they use. Card text is written out so the tests don't need the card DB."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Game, Permanent, Player, StackItem, can_block, card_matches


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



GET_LOST = card("Get Lost", "{1}{W}", "Instant", "Destroy target creature, enchantment, or planeswalker. Its "
                "controller creates two Map tokens.")
ERODE = card("Erode", "{W}", "Instant", "Destroy target creature or planeswalker. Its controller may search their "
             "library for a basic land card, put it onto the battlefield tapped, then shuffle.")
SEAM_RIP = card("Seam Rip", "{W}", "Enchantment", "When this enchantment enters, exile target nonland permanent an "
                "opponent controls with mana value 2 or less until this enchantment leaves the battlefield.")
DEFEAT = card("Inevitable Defeat", "{1}{B}{B}{R}", "Instant", "This spell can't be countered.\nExile target nonland "
              "permanent. Its controller loses 3 life and you gain 3 life.")
GHAST2 = card("Bloodghast", "{B}{B}", "Creature — Vampire Spirit", "Bloodghast can't block.\nLandfall — Whenever "
              "a land you control enters, you may return Bloodghast from your graveyard to the battlefield.", 2, 1)
CRYO = card("Seasoned Cryomancer", "{2}{U}", "Creature — Human Wizard", "{3}{U}{U}, Exile this card from your "
            "graveyard: Draw two cards.", 2, 2)
SMAUG = card("Smaug the Magnificent", "{3}{R}{R}", "Legendary Creature — Dragon", "Flying, haste\nWhenever Smaug "
             "attacks, he deals damage equal to the number of Treasures you control to any target.", 4, 4)


class ZoneTests(Base):
    def test_parsing(self):
        for c in (GET_LOST, ERODE, SEAM_RIP, DEFEAT, GHAST2, CRYO, SMAUG):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual(len(GHAST2.gy_triggers), 1)

    def test_map_tokens_explore(self):
        bear = self.perm(BEAR, self.b)
        self.game.resolve(self.a, GET_LOST.spell_effects[0], bear)
        self.game.resolve(self.a, GET_LOST.spell_effects[1], None, prev=bear)
        maps = [x for x in self.b.battlefield if x.card.token_kind == "map"]
        self.assertEqual(len(maps), 2)
        mine = self.perm(BEAR, self.b)
        self.perm(ISLAND, self.b)
        self.game.active_idx = 1
        self.b.library = [BEAR]
        self.assertTrue(self.game.activate(self.b, maps[0], "ability:0"))
        self.assertEqual(mine.p1, 1)

    def test_erode_gives_the_controller_a_land(self):
        bear = self.perm(BEAR, self.b)
        self.b.library = [ISLAND, BEAR]
        for e in ERODE.spell_effects:
            self.game.resolve(self.a, e, bear if e.kind == "destroy" else None, prev=bear)
        self.assertEqual([x.card.name for x in self.b.battlefield], ["Island"])

    def test_exile_until_leaves_and_exile_drain(self):
        bear = self.perm(BEAR, self.b)
        self.game.enter_battlefield(self.a, SEAM_RIP)
        self.game.settle()
        self.assertNotIn(bear, self.b.battlefield)
        rip = next(x for x in self.a.battlefield if x.card.name == "Seam Rip")
        self.game.destroy(rip)
        self.assertEqual([x.card.name for x in self.b.battlefield], ["Grizzly Bears"])
        target = self.b.battlefield[0]
        self.game.resolve(self.a, DEFEAT.spell_effects[0], target)
        self.game.resolve(self.a, DEFEAT.spell_effects[1], None, prev=target)
        self.game.resolve(self.a, DEFEAT.spell_effects[2], None, prev=target)
        self.assertEqual((self.b.life, self.a.life, self.b.battlefield), (17, 23, []))

    def test_graveyard_trigger_and_ability(self):
        self.a.graveyard = [GHAST2, CRYO]
        self.game.enter_battlefield(self.a, SWAMP)
        self.game.settle()
        self.assertIn("Bloodghast", [c.card.name for c in self.a.creatures])
        for _ in range(5):
            self.perm(ISLAND, self.a)
        ability = next(c for c in self.game.spell_options(self.a) if c.name.endswith("(gy_ability)"))
        self.game.cast(self.a, ability)
        self.assertEqual((len(self.a.hand), self.a.exile), (2, [CRYO]))

    def test_damage_equal_to_treasures(self):
        smaug = self.perm(SMAUG, self.a)
        self.game.resolve(self.a, card("Twin Hoard", "{R}", "Instant", "Create two Treasure tokens.").spell_effects[0], None)
        from mtgsim.engine import StackItem
        item = StackItem(self.a, SMAUG.triggers[0].effects, [self.b], source=smaug)
        self.game.resolve(self.a, SMAUG.triggers[0].effects[0], self.b, item)
        self.assertEqual(self.b.life, 18)



CLERIC = card("Starscape Cleric", "{1}{B}", "Creature — Human Cleric", "This creature can't block.\nWhenever you "
              "gain life, each opponent loses 1 life.", 2, 2)
CONVOCATION = card("Lunar Convocation", "{W}{B}", "Enchantment", "At the beginning of your end step, if you gained "
                   "life this turn, each opponent loses 1 life.")
HALIYA = card("Haliya", "{2}{W}", "Legendary Creature — Human", "At the beginning of your end step, draw a card if "
              "you've gained 3 or more life this turn.", 3, 3)
AMALIA = card("Amalia Benavides Aguirre", "{W}{B}", "Legendary Creature — Vampire", "Ward—Pay 3 life.", 2, 2)
GEV = card("Gev, Scaled Scorch", "{B}{R}", "Legendary Creature — Lizard", "Whenever you cast a Lizard spell, Gev "
           "deals 1 damage to target opponent.", 3, 2)
LIZARD = card("Small Lizard", "{R}", "Creature — Lizard", "", 1, 1)
CLAW = card("Hired Claw", "{R}", "Creature — Lizard Mercenary", "Whenever you attack with one or more Lizards, this "
            "creature deals 1 damage to target opponent.", 1, 2)
INGRIS = card("Ingris", "{1}{R}", "Creature — Wizard", "Whenever a creature you control attacks, that creature deals 1 "
              "damage to each opponent.", 2, 2)
RELIC = card("Cryogen Relic", "{1}{U}", "Artifact", "When this artifact enters or leaves the battlefield, draw a card.")
CHARM = card("Stingerquill Charm", "{1}{R}", "Instant", "Choose one —\n• Target creature gains first strike and "
             "deathtouch until end of turn.\n• Create a 2/2 colorless Wizard Soldier creature token named Cadet. It "
             "gains haste until end of turn.")
FRONT = card("United Battlefront", "{3}{W}", "Sorcery", "Look at the top seven cards of your library. Put up to two "
             "noncreature, nonland permanent cards with mana value 3 or less from among them onto the battlefield. "
             "Put the rest on the bottom of your library in a random order.")


class TriggerTests(Base):
    def test_parsing(self):
        for c in (CLERIC, CONVOCATION, HALIYA, AMALIA, GEV, CLAW, INGRIS, RELIC, CHARM, FRONT):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])

    def test_lifegain_triggers_and_conditions(self):
        self.perm(CLERIC, self.a)
        self.perm(CONVOCATION, self.a)
        self.perm(HALIYA, self.a)
        self.game.change_life(self.a, 2, "test")
        self.game.settle()
        self.assertEqual(self.b.life, 19)
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertEqual((self.b.life, len(self.a.hand)), (18, 0))     # gained 2, not 3
        self.game.change_life(self.a, 1, "test")
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_ward_pay_life(self):
        amalia = self.perm(AMALIA, self.b)
        for _ in range(1):
            self.perm(MOUNTAIN, self.a)
        self.a.hand = [SHOCK]
        self.game.cast(self.a, SHOCK, [amalia])
        self.assertEqual((self.a.life, amalia in self.b.battlefield), (17, False))

    def test_cast_and_attack_triggers(self):
        self.perm(GEV, self.a)
        self.perm(MOUNTAIN, self.a)
        self.a.hand = [LIZARD]
        self.game.cast(self.a, LIZARD)
        self.assertEqual(self.b.life, 19)
        claw = self.perm(CLAW, self.a)
        self.perm(INGRIS, self.a)
        self.a.ai.choose_attackers = lambda g, me, opp: [claw]
        self.b.ai.choose_blocks = lambda g, me, opp, attackers: {}
        self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 19 - 1 - 1 - 1)                  # Claw trigger, Ingris, combat

    def test_leaves_trigger_charm_token_and_battlefront(self):
        relic = self.perm(RELIC, self.a)
        self.game.leave_battlefield(relic, "graveyard")
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)
        token = CHARM.modes[1][0]
        self.assertIn("haste", token.data["temp_keywords"])
        self.assertNotIn("haste", token.data["keywords"])
        self.a.library = [ISLAND, RELIC, BEAR, CANDY, ISLAND, ISLAND, ISLAND]
        self.game.resolve(self.a, FRONT.spell_effects[0], None)
        self.assertEqual(sorted(x.card.name for x in self.a.battlefield), ["Candy Trail", "Cryogen Relic"])


if __name__ == "__main__":
    unittest.main()


FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
RELIC = card("Cryogen Relic", "{1}{U}", "Artifact", (
    "When this artifact enters or leaves the battlefield, draw a card.\n{1}{U}, Sacrifice this artifact: Put a stun "
    "counter on up to one target tapped creature."))
TUNNEL = card("Escape Tunnel", types="Land", text=(
    "{T}, Sacrifice Escape Tunnel: Target creature with power 2 or less can't be blocked this turn."))
EXPLORER = card("Icetill Explorer", "{2}{G}{G}", "Creature — Insect Scout", (
    "You may play an additional land on each of your turns.\nYou may play lands from your graveyard."), 2, 4)
NURSERY = card("Sapling Nursery", "{6}{G}{G}", "Enchantment", (
    "Affinity for Forests\nLandfall — Whenever a land you control enters, create a 3/4 green Treefolk creature "
    "token with reach."))
VAULT = card("Fomori Vault", types="Land", text=(
    "{T}: Add {C}.\n{3}, {T}, Discard a card: Look at the top X cards of your library, where X is the number of "
    "artifacts you control. Put one of those cards into your hand and the rest on the bottom of your library in a "
    "random order."))
ASCENSION = card("Earthbender Ascension", "{2}{G}", "Enchantment", (
    "When this enchantment enters, earthbend 2.\nLandfall — Whenever a land you control enters, put a quest counter "
    "on this enchantment. When you do, if it has four or more quest counters on it, put a +1/+1 counter on target "
    "creature you control. It gains trample until end of turn."))
SYNTH = card("Simulacrum Synthesizer", "{2}{U}", "Artifact", (
    "Whenever another artifact you control with mana value 3 or greater enters, create a 0/0 colorless Construct "
    "artifact creature token with \"This token gets +1/+1 for each artifact you control.\""))
BIG_ROCK = card("Big Rock", "{3}", "Artifact", "")
BIOTECH = card("Biotech Specialist", "{R}{G}", "Creature — Insect Scientist", (
    "Whenever you sacrifice an artifact, this creature deals 2 damage to target opponent."), 1, 3)
OFFERING = card("Fanatical Offering", "{1}{B}", "Instant", (
    "As an additional cost to cast this spell, sacrifice an artifact or creature.\nDraw two cards."))
PRECISION = card("Deadly Precision", "{B}", "Sorcery", (
    "As an additional cost to cast this spell, pay {4} or sacrifice an artifact or creature.\nDestroy target "
    "creature."))


class Round2Tests(Base):
    def test_parsing(self):
        for c in (RELIC, TUNNEL, EXPLORER, NURSERY, VAULT, ASCENSION, SYNTH, BIOTECH, OFFERING, PRECISION):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual(NURSERY.cost_reduction, "affinity:Forest")
        self.assertEqual((PRECISION.extra_sacrifice, PRECISION.extra_sac_or_pay), ("an artifact or creature", 4))

    def test_stun_on_tapped_creature(self):
        bear = self.perm(BEAR, self.b)
        relic = self.perm(RELIC, self.a)
        self.perm(ISLAND, self.a), self.perm(ISLAND, self.a)
        eff = RELIC.activated[0].effects[0]
        self.assertEqual(self.game.legal_targets(self.a, eff), [])
        bear.tapped = True
        self.assertEqual(self.game.legal_targets(self.a, eff), [bear])
        self.game.resolve(self.a, eff, bear)
        self.assertEqual(bear.counters["stun"], 1)
        self.assertIn(relic, self.a.battlefield)

    def test_cant_be_blocked_this_turn(self):
        bear = self.perm(BEAR, self.a)
        blocker = self.perm(BEAR, self.b)
        self.perm(DRAGON3, self.a)
        eff = TUNNEL.activated[0].effects[0]
        self.assertEqual(self.game.legal_targets(self.a, eff), [bear])
        self.game.resolve(self.a, eff, bear)
        self.assertFalse(can_block(blocker, bear))

    def test_additional_land_and_lands_from_graveyard(self):
        self.perm(EXPLORER, self.a)
        self.a.hand = [ISLAND]
        self.a.graveyard = [FOREST]
        self.game.play_land(self.a, ISLAND)
        self.assertFalse(self.a.land_played)
        self.game.play_land(self.a, FOREST)
        self.assertTrue(self.a.land_played)
        self.assertEqual(self.a.graveyard, [])
        self.a.land_played = False
        self.assertFalse(self.a.land_played)

    def test_affinity_and_dig_by_artifact_count(self):
        for _ in range(3):
            self.perm(FOREST, self.a)
        self.assertEqual(self.game.cost_of(self.a, NURSERY)["generic"], 3)
        self.perm(BIG_ROCK, self.a), self.perm(BIG_ROCK, self.a)
        self.a.library = [ISLAND] * 5 + [BEAR, DRAGON]
        dig = VAULT.activated[0].effects[0]
        self.assertEqual(dig.data, {"x_count": "artifact"})
        self.game.resolve(self.a, dig, None)
        self.assertEqual(len(self.a.hand), 1)

    def test_earthbend_and_quest_counters(self):
        land = self.perm(FOREST, self.a)
        self.game.enter_battlefield(self.a, ASCENSION)
        self.game.settle()
        self.assertTrue(land.is_creature)
        self.assertEqual((land.power, land.toughness), (2, 2))
        trig = next(t for t in ASCENSION.triggers if t.event == "land_enters")
        self.assertEqual(trig.effects[-2].cond, "counters:quest>=4")

    def test_synthesizer_makes_scaling_artifact_tokens(self):
        self.perm(SYNTH, self.a)
        self.game.enter_battlefield(self.a, BIG_ROCK)
        self.game.settle()
        token = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertTrue(token.card.is_artifact)
        self.assertEqual(token.power, 3)     # Synthesizer, Big Rock and the token itself

    def test_sacrifice_trigger_and_additional_cost(self):
        self.perm(BIOTECH, self.a)
        rock = self.perm(BIG_ROCK, self.a)
        self.perm(ISLAND, self.a)
        self.perm(SWAMP, self.a), self.perm(SWAMP, self.a)
        self.a.hand = [OFFERING]
        self.game.active_idx = 0
        self.assertTrue(self.game.can_cast_now(self.a, OFFERING))
        self.game.cast(self.a, OFFERING)
        self.game.settle()
        self.assertNotIn(rock, self.a.battlefield)
        self.assertEqual(self.b.life, 18)
        self.assertFalse(self.game.can_cast_now(self.a, PRECISION))   # no sacrifice, {4} too much


CACHE_GRAB = card("Cache Grab", "{1}{G}", "Instant", (
    "Mill four cards. You may put a permanent card from among the cards milled this way into your hand. If you "
    "control a Squirrel or returned a Squirrel card to your hand this way, create a Food token."))
SPEAKER = card("Formidable Speaker", "{2}{G}", "Creature — Elf Druid", (
    "When this creature enters, you may discard a card. If you do, search your library for a creature card, reveal "
    "it, put it into your hand, then shuffle.\n{1}, {T}: Untap another target permanent."), 2, 4)
BOOKWORM = card("Oblivious Bookworm", "{G}{U}", "Creature — Human Wizard", (
    "At the beginning of your end step, you may draw a card. If you do, discard a card unless a permanent entered "
    "the battlefield face down under your control this turn or you turned a permanent face up this turn."), 2, 3)
CRYOMANCER = card("Seasoned Cryomancer", "{1}{U}{U}", "Creature — Human Wizard", (
    "When this creature enters, draw two cards, then discard two cards. When you discard one or more nonland "
    "cards this way, tap up to that many target creatures and put a stun counter on each of them."), 2, 2)
OVERLORD = card("Overlord of the Balemurk", "{3}{B}{B}", "Enchantment Creature — Avatar Horror", (
    "Impending 5—{1}{B}\nWhenever this creature enters or attacks, mill four cards, then you may return a "
    "non-Avatar creature card or a planeswalker card from your graveyard to your hand."), 5, 5)
TERROR = card("Terror of the Peaks", "{3}{R}{R}", "Creature — Dragon", (
    "Flying\nSpells your opponents cast that target this creature cost an additional 3 life to cast.\nWhenever "
    "another creature you control enters, this creature deals damage equal to that creature's power to any "
    "target."), 5, 4)
DROWNER = card("Floodpits Drowner", "{1}{U}", "Creature — Merfolk", (
    "Flash\nVigilance\nWhen this creature enters, tap target creature an opponent controls and put a stun counter "
    "on it.\n{1}{U}, {T}: Shuffle this creature and target creature with a stun counter on it into their owners' "
    "libraries."), 2, 1)
CURIOSITY = card("Enduring Curiosity", "{2}{U}{U}", "Enchantment Creature — Cat Glimmer", (
    "Flash\nWhenever a creature you control deals combat damage to a player, draw a card.\nWhen this creature "
    "dies, if it was a creature, return it to the battlefield under its owner's control. It's an enchantment. "
    "(It's not a creature.)"), 4, 3)
SANCTUARY = card("Soulstone Sanctuary", types="Land", text=(
    "{T}: Add {C}.\n{4}: This land becomes a 3/3 creature with vigilance and all creature types. It's still a "
    "land."))
BETRAYAL = card("Strategic Betrayal", "{1}{B}", "Sorcery", (
    "Target opponent exiles a creature they control and their graveyard."))
BRINGER = card("Bringer of the Last Gift", "{6}{B}{B}", "Creature — Vampire Demon", (
    "Flying\nWhen this creature enters, if you cast it, each player sacrifices all other creatures they control. "
    "Then each player returns all creature cards from their graveyard that weren't put there this way to the "
    "battlefield."), 6, 6)


class Round3Tests(Base):
    def test_parsing(self):
        for c in (CACHE_GRAB, SPEAKER, BOOKWORM, CRYOMANCER, OVERLORD, TERROR, DROWNER, CURIOSITY, SANCTUARY,
                  BETRAYAL, BRINGER):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])

    def test_mill_and_pick_a_permanent(self):
        self.a.library = [ISLAND, SHOCK, BEAR, SHOCK, ISLAND]
        for e in CACHE_GRAB.spell_effects:
            if self.game.check_cond(self.a, e, None, None):
                self.game.resolve(self.a, e, None)
        self.assertEqual(len(self.a.hand), 1)
        self.assertTrue(self.a.hand[0].is_permanent)
        self.assertEqual(len(self.a.graveyard), 3)
        self.assertFalse(any(x.card.token_kind == "food" for x in self.a.battlefield))

    def test_discard_to_tutor_and_cryomancer_stuns(self):
        self.a.hand = [ISLAND]
        self.a.library = [ISLAND, BEAR, ISLAND]
        self.game.resolve(self.a, SPEAKER.triggers[0].effects[0], None)
        self.assertEqual(self.a.hand, [BEAR])
        foe = self.perm(DRAGON3, self.b)
        self.a.hand, self.a.library = [], [SHOCK, SHOCK]
        for e in CRYOMANCER.triggers[0].effects:
            self.game.resolve(self.a, e, None)
        self.assertEqual((foe.tapped, foe.counters.get("stun")), (True, 1))

    def test_impending_is_not_a_creature(self):
        for _ in range(2):
            self.perm(SWAMP, self.a)
        self.a.hand = [OVERLORD]
        variant = next(v for v in self.game.spell_options(self.a) if v.name.endswith("(impending)"))
        self.game.cast(self.a, variant)
        self.game.settle()
        lord = next(x for x in self.a.battlefield if x.card.name == "Overlord of the Balemurk")
        self.assertFalse(lord.is_creature)
        lord.counters["time"] = 0
        self.assertTrue(lord.is_creature)

    def test_terror_and_drowner(self):
        self.perm(TERROR, self.a)
        self.game.enter_battlefield(self.a, DRAGON3)
        self.game.settle()
        self.assertEqual(self.b.life, 17)
        foe = self.perm(DRAGON3, self.b)
        foe.counters["stun"] = 1
        self.perm(DROWNER, self.a)
        eff = DROWNER.activated[0].effects[0]
        self.assertEqual(self.game.legal_targets(self.a, eff), [foe])

    def test_enduring_returns_as_enchantment(self):
        cat = self.perm(CURIOSITY, self.a)
        self.game.destroy(cat)
        self.game.settle()
        back = next(x for x in self.a.battlefield if x.card.name == "Enduring Curiosity")
        self.assertFalse(back.is_creature)

    def test_strategic_betrayal(self):
        self.perm(BEAR, self.b)
        self.b.graveyard = [BEAR, SHOCK]
        for e in BETRAYAL.spell_effects:
            self.game.resolve(self.a, e, None)
        self.assertEqual((self.b.creatures, self.b.graveyard, len(self.b.exile)), ([], [], 3))

    def test_last_gift(self):
        mine = self.perm(BEAR, self.a)
        self.a.graveyard = [DRAGON3]
        self.b.graveyard = [DRAGON]
        bringer = self.perm(BRINGER, self.a)
        bringer.was_cast = True
        self.game.queue_trigger(self.a, BRINGER.triggers[0].effects, bringer, "Bringer")
        self.game.settle()
        self.assertNotIn(mine, self.a.battlefield)
        self.assertEqual(sorted(x.card.name for x in self.a.creatures), ["Big Dragon", "Bringer of the Last Gift"])
        self.assertEqual([x.card.name for x in self.b.creatures], ["Test Dragon"])


KILN = card("Cosmium Kiln", "", "Artifact", (
    "When this artifact enters, create two 1/1 colorless Gnome artifact creature tokens.\nCreatures you control "
    "get +1/+1."))
BRICKS = card("Clay-Fired Bricks", "{1}{W}", "Artifact", (
    "Craft with artifact {1}{W} ({1}{W}, Exile this artifact, Exile another artifact you control or an artifact "
    "card from your graveyard: Return this card transformed under its owner's control. Craft only as a sorcery.)"))
BRICKS.back = KILN
QUIPU = card("Braided Quipu", "", "Artifact", (
    "{3}{U}, {T}: Draw a card for each artifact you control, then put this artifact into its owner's library "
    "third from the top."))
NET = card("Braided Net", "{2}{U}", "Artifact", "This artifact enters with three net counters on it.")
PLANET = card("Test Planet", types="Land — Planet", text=(
    "{T}: Add {W}.\nStation (Tap another creature you control: Put charge counters equal to its power on this "
    "Planet. Station only as a sorcery.)\nSTATION 3+\n{T}: You gain 3 life."))


class CraftStationTests(Base):
    def test_parsing(self):
        for c in (BRICKS, KILN, QUIPU, NET, PLANET):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual(NET.etb_named_counters, ("net", 3))

    def test_craft_exiles_an_artifact_and_transforms(self):
        bricks = self.perm(BRICKS, self.a)
        self.perm(PLAINS, self.a), self.perm(PLAINS, self.a)
        self.game.active_idx = 0
        self.assertFalse(self.game.can_activate(self.a, bricks, 0))     # nothing to craft with
        self.a.graveyard = [BIG_ROCK]
        self.assertTrue(self.game.activate(self.a, bricks, "ability:0"))
        self.assertEqual(self.a.exile, [BIG_ROCK])
        kiln = next(x for x in self.a.battlefield if x.card.name == "Cosmium Kiln")
        self.assertIs(kiln.front, bricks.front)
        self.assertEqual(len([x for x in self.a.creatures if x.card.is_token]), 2)

    def test_draw_per_artifact_then_tuck(self):
        quipu = self.perm(QUIPU, self.a)
        self.perm(BIG_ROCK, self.a)
        self.a.library = [ISLAND] * 5
        item = StackItem(self.a, [], [], source=quipu, kind="ability")
        for e in QUIPU.activated[0].effects:
            self.game.resolve(self.a, e, None, item)
        self.assertEqual(len(self.a.hand), 2)
        self.assertEqual(self.a.library[-3], QUIPU)

    def test_station_unlocks_abilities(self):
        planet = self.perm(PLANET, self.a)
        bear = self.perm(BEAR, self.a)
        self.game.active_idx = 0
        self.assertFalse(self.game.can_activate(self.a, planet, 0))
        self.assertTrue(self.game.station(self.a, planet, bear))
        self.assertEqual(planet.counters["charge"], 2)
        bear.tapped = False
        self.game.station(self.a, planet, bear)
        self.assertTrue(self.game.can_activate(self.a, planet, 0))

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


class TemplateTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

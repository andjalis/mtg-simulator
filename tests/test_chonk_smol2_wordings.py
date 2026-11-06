"""smol-chonk-2 batch 3, part two: mined wording clusters.

"Add {X}{X}"/"Add N {X}"/"Add N mana of any color|combination" effects, the shuffle and
library-information no-ops, the "you don't lose this mana" rider (with its recorded
simplification), "draw an additional card", and the 'Enchanted land has "{T}: Add ..."' rewrite onto the aura_mana line
batch1_templates implements.
"""
import random
import unittest

from mtgsim.cards import Effect
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card


class ManaAddWordings(unittest.TestCase):
    def parse(self, text):
        from mtgsim.cards.parse import _parse_effects
        return _parse_effects(text)

    def test_add_repeated_symbols(self):
        effects, bad = self.parse("Add {B}{B}.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].kind, "add_mana")
        self.assertEqual(effects[0].data["colors"], ["B", "B"])

    def test_add_numbered_color(self):
        effects, bad = self.parse("Add eight {C}.")
        self.assertEqual(bad, [])
        self.assertEqual((effects[0].kind, effects[0].amount, effects[0].data["colors"]),
                         ("add_mana", 8, ["C"]))

    def test_add_numbered_any_color(self):
        effects, bad = self.parse("Add two mana of any color.")
        self.assertEqual(bad, [])
        self.assertEqual((effects[0].kind, effects[0].amount, effects[0].data["choice"]),
                         ("add_mana", 2, list("WUBRG")))

    def test_add_combination(self):
        effects, bad = self.parse("Add four mana in any combination of {R} and/or {G}.")
        self.assertEqual(bad, [])
        self.assertEqual((effects[0].kind, effects[0].amount, effects[0].data["choice"]),
                         ("add_mana", 4, ["R", "G"]))

    def test_engine_adds_the_amount(self):
        a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
        game = Game(a, b, random.Random(0))
        game.resolve(a, Effect("add_mana", 8, data={"colors": ["C"]}), None)
        self.assertEqual(len(a.pool), 8)
        game.resolve(a, Effect("add_mana", data={"colors": ["B", "B"]}), None)
        self.assertEqual(sum(1 for m in a.pool if "B" in m.card.produces), 2)


class NoOpWordings(unittest.TestCase):
    def parse(self, text):
        from mtgsim.cards.parse import _parse_effects
        return _parse_effects(text)

    def test_shuffle_sentences(self):
        for text in ("You may shuffle.", "Then that player shuffles.", "That player shuffles.",
                     "They shuffle.", "Shuffle."):
            self.assertEqual(self.parse(text), ([], []), text)

    def test_library_information(self):
        for text in ("Play with the top card of your library revealed.",
                     "You may look at the top card of your library any time."):
            self.assertEqual(self.parse(text), ([], []), text)

    def test_mana_persistence_rider(self):
        effects, bad = self.parse("Until end of turn, you don't lose this mana as steps and phases end.")
        self.assertEqual((effects, bad), ([], []))
        CLEARCUTTER = card("Test Clearcutter", "{4}", "Artifact Creature — Golem",
                           "When this creature dies, add eight {C}. Until end of turn, you don't lose this "
                           "mana as steps and phases end.", 3, 6)
        self.assertEqual(CLEARCUTTER.unsupported, [])
        self.assertEqual(CLEARCUTTER.approximations,
                         ["the mana pool still empties at the end of each phase"])

    def test_draw_an_additional_card(self):
        DRAGON = card("Test Avaricious", "{2}{R}", "Creature — Dragon",
                      "Flying\nAt the beginning of your draw step, draw an additional card.", 4, 4)
        self.assertEqual(DRAGON.unsupported, [])
        self.assertEqual(DRAGON.approximations, [])
        (trig,) = DRAGON.triggers
        self.assertEqual(trig.event, "draw_step")
        self.assertEqual(trig.effects[0].kind, "draw")
        KHANS = card("Test Khans", "{2}{U}", "Enchantment",
                     "At the beginning of your draw step, draw an additional card, then discard a card.")
        self.assertEqual(KHANS.unsupported, [])
        self.assertEqual([e.kind for e in KHANS.triggers[0].effects], ["draw", "discard"])


class AuraManaWording(unittest.TestCase):
    def test_old_wording_becomes_aura_mana_line(self):
        PARADISE = card("Test Gift of Paradise", "{2}{G}", "Enchantment — Aura",
                        "Enchant land\nWhen Test Gift of Paradise enters, you gain 2 life.\n"
                        'Enchanted land has "{T}: Add two mana of any one color."')
        self.assertEqual(PARADISE.unsupported, [])
        self.assertEqual(PARADISE.advanced_rules.get("aura_mana"), 2)
        self.assertIn("extra mana from an enchanted land is the land's own colour", PARADISE.approximations)
        # a single mana stays with the exact granted_mana path, not the approximation
        GROWTH = card("Test Wild Growth", "{G}", "Enchantment — Aura",
                      'Enchant land\nEnchanted land has "{T}: Add {G}."')
        self.assertEqual(GROWTH.unsupported, [])
        self.assertEqual(GROWTH.approximations, [])
        self.assertFalse(GROWTH.advanced_rules.get("aura_mana"))




class CountedWordings(unittest.TestCase):
    """Effects whose amount is a count or a previously targeted permanent's controller."""

    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def test_controller_discard_after_destroy(self):
        STRIKE = card("Test Strike", "{4}{B}", "Sorcery",
                      "Destroy target creature. Its controller discards a card.")
        self.assertEqual(STRIKE.unsupported, [])
        self.assertEqual([e.kind for e in STRIKE.spell_effects], ["destroy", "discard"])
        SWAMP = card("Test Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
        for _ in range(5):
            self.game.enter_battlefield(self.a, SWAMP)
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.b.hand = [ISLAND] * 3
        self.a.hand = [STRIKE]
        self.assertTrue(self.game.cast(self.a, STRIKE, targets=[bear]))
        self.game.settle()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(len(self.b.hand), 2)      # its controller discarded a card

    def test_tokens_for_each_you_control(self):
        ELVEN = card("Test Elven Ambush", "{3}{G}", "Instant",
                     "Create a 1/1 green Elf Warrior creature token for each Elf you control.")
        self.assertEqual(ELVEN.unsupported, [])
        self.assertEqual(ELVEN.spell_effects[0].data["per"], {"what": "Elf", "zone": "battlefield"})
        FOREST = card("Test Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
        ELF = card("Test Elf", "{1}{G}", "Creature — Elf Warrior", "", 2, 2)
        for _ in range(5):
            self.game.enter_battlefield(self.a, FOREST)
        self.game.enter_battlefield(self.a, ELF)
        self.game.enter_battlefield(self.a, ELF)
        self.game.settle()
        self.a.hand = [ELVEN]
        self.assertTrue(self.game.cast(self.a, ELVEN))
        self.game.settle()
        self.assertEqual(sum(x.card.is_token and "Elf" in x.card.subtypes
                              for x in self.a.battlefield), 2)

    def test_add_for_each_basic_land_you_control(self):
        STRONGHOLD = card("Test Stronghold", "", "Land — Lair",
                          "{3}, {T}: Add {B} for each basic Swamp you control.")
        self.assertEqual(STRONGHOLD.unsupported, [])
        self.assertEqual(STRONGHOLD.approximations, [])
        SWAMP = card("Test Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
        from mtgsim.copies import fits
        self.assertTrue(fits(SWAMP, "basic Swamp"))
        for _ in range(3):
            self.game.enter_battlefield(self.a, SWAMP)
        self.game.settle()
        perm = self.game.enter_battlefield(self.a, STRONGHOLD)
        self.game.settle()
        self.a.pool = []
        self.assertTrue(self.game.activate_ability(self.a, perm, 0))
        self.game.settle()
        self.assertEqual(sum("B" in m.card.produces for m in self.a.pool), 3)


class ShockTappedCondition(unittest.TestCase):
    def test_three_life_variant_uses_the_shock_condition(self):
        GATE = card("Test Black Gate", "", "Land — Gate",
                    "As Test Black Gate enters, you may pay 3 life. If you don't, it enters tapped.\n"
                    "{T}: Add {B}.")
        self.assertEqual(GATE.unsupported, [])
        self.assertEqual(GATE.approximations, ["the 3 life enters-uncovered cost is paid as 2 life"])
        self.assertEqual(GATE.tapped_condition, "shock")
        GROVE = card("Test Stomping Ground", "", "Land — Mountain Forest",
                     "As Test Stomping Ground enters, you may pay 2 life. If you don't, it enters tapped.\n"
                     "{T}: Add {R} or {G}.")
        self.assertEqual((GROVE.unsupported, GROVE.approximations), ([], []))
        self.assertEqual(GROVE.tapped_condition, "shock")


if __name__ == "__main__":
    unittest.main()

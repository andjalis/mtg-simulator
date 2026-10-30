"""smol-chonk-4 batch 5: rich mill_pick descriptions and "<Subtype> planeswalker spell" cast triggers.

Airlift Chaplain ("a Plains card or a creature card with mana value 3 or less") and Fallaji
Archaeologist ("a noncreature, nonland card") wording families: the pick keeps per-alternative
type/subtype words, "non<type>" exclusions and mana-value riders. The typed cast trigger
("a Bolas planeswalker spell", Wasp of the Bitter End) reduces to the engine's spell: filter
over subtypes, since a subtype implies its card type and the filter ORs kinds.
"""
import dataclasses
import random
import unittest

from mtgsim.milling import _alt_matches, _alt_specs
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, SHOCK, SWAMP, card

CHAPLAIN = card("Test Chaplain", "{2}{W}", "Creature — Human Cleric",
                "Flying\nWhen this creature enters, mill three cards. You may put a Plains card or a "
                "creature card with mana value 3 or less from among the cards milled this way into "
                "your hand. If you don't, put a +1/+1 counter on this creature.", 1, 3)
ARCHAEOLOGIST = card("Test Archaeologist", "{1}{W}", "Creature — Human Artificer",
                     "When this creature enters, mill three cards. You may put a noncreature, "
                     "nonland card from among the cards milled this way into your hand. If you "
                     "don't, put a +1/+1 counter on this creature.", 1, 3)
BIG_DUDE = card("Test Big Dude", "{5}{G}", "Creature — Beast", "", 5, 5)            # mana value 6
WASP = card("Test Wasp", "{1}{B}", "Creature — Insect",
            "Whenever you cast a Bolas planeswalker spell, you may sacrifice this creature. "
            "If you do, destroy target creature.", 1, 1)
BOLAS = dataclasses.replace(card("Test Bolas", "{2}{U}{B}", "Legendary Planeswalker — Bolas",
                                 "[+1]: Draw a card."), loyalty=4)
KAITO = dataclasses.replace(card("Test Kaito", "{2}{U}{B}", "Legendary Planeswalker — Kaito",
                                 "[+1]: Draw a card."), loyalty=4)


class MillPickDescriptions(unittest.TestCase):
    def test_chaplain_wording_family_parses(self):
        self.assertEqual(CHAPLAIN.unsupported, [], "chaplain")
        etb = [t for t in CHAPLAIN.triggers if t.event == "etb"][0]
        self.assertEqual([e.kind for e in etb.effects], ["mill", "pay_gate", "mill_pick", "p1_counters"])
        self.assertEqual(etb.effects[-1].cond, "!paid")
        pick = etb.effects[2]
        self.assertEqual(pick.data["alts"], [(["Plains"], [], None), (["creature"], [], ("less", 3))])
        self.assertEqual(pick.data["dest"], "hand")

    def test_archaeologist_wording_family_parses(self):
        self.assertEqual(ARCHAEOLOGIST.unsupported, [], "archaeologist")
        pick = [t for t in ARCHAEOLOGIST.triggers if t.event == "etb"][0].effects[2]
        self.assertEqual(pick.data["alts"], [([], ["creature", "land"], None)])

    def test_any_card_pick(self):
        effects, bad = _parse_effects("You may put a card from among the cards milled this way "
                                      "into your hand.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[-1].kind, "mill_pick")
        self.assertEqual(effects[-1].data["alts"], [([], [], None)])
        self.assertTrue(_alt_matches(BEAR, [([], [], None)]))

    def test_alternatives_split_before_articles_not_riders(self):
        specs = _alt_specs("Plains card or a creature card with mana value 3 or less")
        self.assertEqual(specs, [(["Plains"], [], None), (["creature"], [], ("less", 3))])
        self.assertTrue(_alt_matches(card("Plains", types="Basic Land — Plains", text="({T}: Add {W}.)"), specs))
        self.assertTrue(_alt_matches(BEAR, specs))                                   # mana value 2
        self.assertFalse(_alt_matches(BIG_DUDE, specs))                              # mana value 6
        self.assertFalse(_alt_matches(SHOCK, specs))

    def test_exclusions(self):
        specs = _alt_specs("noncreature, nonland card")
        self.assertEqual(specs, [([], ["creature", "land"], None)])
        self.assertTrue(_alt_matches(SHOCK, specs))
        self.assertFalse(_alt_matches(BEAR, specs))
        self.assertFalse(_alt_matches(ISLAND, specs))

    def test_unsafe_descriptions_stay_unsupported(self):
        for text in ("You may put a legendary card from among the cards milled this way into "
                     "your hand.",
                     "You may put a card that shares a card type with it from among the cards "
                     "milled this way into your hand.",
                     "You may put a card named Shock from among the cards milled this way into "
                     "your hand."):
            effects, bad = _parse_effects(text)
            self.assertEqual((effects, len(bad)), ([], 1), text)

    def test_alt_matching_uses_cmc_riders_per_alternative(self):
        specs = _alt_specs("Spirit card or an enchantment card with mana value 4 or greater")
        self.assertEqual(specs, [(["Spirit"], [], None), (["enchantment"], [], ("greater", 4))])
        self.assertTrue(_alt_matches(card("Test Rune", "{5}{W}", "Enchantment", ""), specs))
        self.assertFalse(_alt_matches(card("Test Rune", "{1}{W}", "Enchantment", ""), specs))


class MillPickEngine(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0

    def test_chaplain_picks_matching_card_from_milled(self):
        # top of library first: an Island and a big creature don't fit "a Plains card or a
        # creature card with mana value 3 or less", the Plains does.
        self.a.library = [ISLAND] * 20 + [BIG_DUDE, ISLAND,
                                          card("Plains", types="Basic Land — Plains",
                                               text="({T}: Add {W}.)")]
        self.game.enter_battlefield(self.a, CHAPLAIN)
        self.game.settle()
        self.assertEqual([c.name for c in self.a.hand], ["Plains"])
        self.assertEqual({c.name for c in self.a.graveyard}, {"Test Big Dude", "Island"})

    def test_archaeologist_picks_noncreature_nonland(self):
        self.a.library = [ISLAND] * 20 + [BEAR, ISLAND, SHOCK]
        self.game.enter_battlefield(self.a, ARCHAEOLOGIST)
        self.game.settle()
        self.assertEqual([c.name for c in self.a.hand], ["Shock"])
        self.assertEqual({c.name for c in self.a.graveyard}, {BEAR.name, "Island"})


class BolasCastTrigger(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        self.wasp = self.game.enter_battlefield(self.a, WASP)
        self.bear = self.game.enter_battlefield(self.b, BEAR)
        self.game.settle()

    def cast_pw(self, pw):
        for _ in range(2):
            self.game.enter_battlefield(self.a, ISLAND)
            self.game.enter_battlefield(self.a, SWAMP)
        self.a.hand.append(pw)
        self.assertTrue(self.game.cast(self.a, pw, []))
        self.game.settle()

    def test_trigger_filter_is_the_subtype(self):
        self.assertEqual(WASP.unsupported, [], "wasp")
        (trig,) = WASP.triggers
        self.assertEqual((trig.event, trig.filter), ("cast_spell", "spell:Bolas"))
        self.assertEqual([e.kind for e in trig.effects], ["sac_self_payoff"])

    def test_bolas_planeswalker_cast_fires_the_trigger(self):
        self.cast_pw(BOLAS)
        self.assertNotIn(self.wasp, self.a.battlefield)          # sacrificed for the destroy
        self.assertNotIn(self.bear, self.b.creatures)           # destroyed

    def test_other_planeswalker_cast_does_not_fire(self):
        self.cast_pw(KAITO)
        self.assertIn(self.wasp, self.a.battlefield)
        self.assertIn(self.bear, self.b.creatures)


if __name__ == "__main__":
    unittest.main()

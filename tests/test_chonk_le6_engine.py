"""le-chonk-6 engine batch, part 1: Dark Confidant recording, typed discard triggers,
and "a card named <name>" search descriptors.

- effects.dig() records the mana value of the last card put into the hand on the resolving
  stack item, which the ("revealed", "mana value") x-quantity reads ("You lose life equal to
  its mana value", Dark Confidant).
- discard_card passes the discarded card as the event subject; the "opp_discard" dispatch
  filters typed listeners ("whenever an opponent discards a creature card", Waste Not) on
  it, while unfiltered listeners (Megrim) keep firing on every discard.
- card_matches understands "a card named <full name>" (exact name match, multi-word names
  included) and "a card named ~" (the resolving card's own name, substituted in resolve());
  "~" with no known source matches nothing instead of everything.
"""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import Effect, Trigger
from mtgsim.engine import Game, Permanent, Player, StackItem
from mtgsim.engine.state import card_matches

from tests.test_templates import BEAR, ISLAND, card

BIG = card("Test Giant", "{4}", "Creature — Giant", "", 4, 5)
LAND = card("Test Land", types="Land", text="{T}: Add {G}.")
HAWK = card("Test Hawk", "{1}{W}", "Creature — Bird", (
    "Flying\nWhen this creature enters, you may search your library for a card named Test Hawk, "
    "reveal it, put it into your hand, then shuffle."))
SCREAMER = card("Screaming Testhawk", "{3}{U}", "Creature — Bird", (
    "Flying\nWhen this creature enters, you may search your library for a card named ~, "
    "reveal it, put it into your hand, then shuffle."))


class Chonk6(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        for p in (self.a, self.b):
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def resolve_all(self, p, effects, item, targets=()):
        targets = list(targets) + [None] * len(effects)
        prev = None
        for eff, target in zip(effects, targets):
            self.g.resolve(p, eff, target, item, prev=prev)
            prev = target


class DigRecording(Chonk6):
    """Dark Confidant: the dig records the revealed card's mana value on the resolving item."""

    def test_dig_records_revealed_cmc_for_the_revealed_xq(self):
        self.a.library = [ISLAND] * 5 + [BIG]
        dig = Effect("dig", 1, 1)
        lose = Effect("lose_life", 1, data={"xq": ("revealed", "mana value")})
        item = StackItem(self.a, [dig, lose], [None, None], card=BIG)
        life = self.a.life
        self.resolve_all(self.a, [dig, lose], item)
        self.assertEqual(item.revealed_cmc, BIG.cmc)
        self.assertEqual(self.a.life, life - BIG.cmc)

    def test_revealed_xq_without_a_dig_stays_zero(self):
        lose = Effect("lose_life", 1, data={"xq": ("revealed", "mana value")})
        item = StackItem(self.a, [lose], [None], card=BIG)
        life = self.a.life
        self.resolve_all(self.a, [lose], item)
        self.assertEqual(self.a.life, life)

    def test_dig_outside_a_resolution_does_not_crash(self):
        self.a.library = [ISLAND] * 5 + [BIG]
        self.g.dig(self.a, 1, 1)
        self.assertEqual([c.name for c in self.a.hand], ["Test Giant"])


class TypedDiscardTriggers(Chonk6):
    def waste_not(self, desc):
        perm = self.perm(card("Test Waste Not", "{1}{B}", "Enchantment", ""), self.a)
        perm.temp_triggers.append(Trigger(event="opp_discard", effects=[Effect("gain_life", 1)], filter=desc))
        return perm

    def test_typed_discard_triggers_on_the_matching_type(self):
        self.waste_not("creature card")
        self.b.hand = [BEAR]
        life = self.a.life
        self.g.discard_card(self.b, BEAR)
        self.g.settle()
        self.assertEqual(self.a.life, life + 1)

    def test_typed_discard_skips_other_types(self):
        self.waste_not("land card")
        self.b.hand = [BEAR]
        life = self.a.life
        self.g.discard_card(self.b, BEAR)
        self.g.settle()
        self.assertEqual(self.a.life, life)

    def test_noncreature_nonland_filter(self):
        self.waste_not("noncreature, nonland card")
        spell = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 1 damage to any target.")
        self.b.hand = [BEAR, LAND, spell]
        life = self.a.life
        self.g.discard_card(self.b, BEAR)
        self.g.settle()
        self.assertEqual(self.a.life, life)
        self.g.discard_card(self.b, LAND)
        self.g.settle()
        self.assertEqual(self.a.life, life)
        self.g.discard_card(self.b, spell)
        self.g.settle()
        self.assertEqual(self.a.life, life + 1)

    def test_unfiltered_listener_fires_on_every_discard(self):
        perm = self.perm(card("Test Megrim", "{2}{B}", "Enchantment", ""), self.a)
        perm.temp_triggers.append(Trigger(event="opp_discard", effects=[Effect("gain_life", 1)], filter=""))
        self.b.hand = [BEAR, LAND]
        life = self.a.life
        self.g.discard_card(self.b, BEAR)
        self.g.discard_card(self.b, LAND)
        self.g.settle()
        self.assertEqual(self.a.life, life + 2)

    def test_discarding_your_own_card_does_not_fire_opponent_listeners(self):
        self.waste_not("creature card")
        self.a.hand = [BEAR]
        life = self.a.life
        self.g.discard_card(self.a, BEAR)
        self.g.settle()
        self.assertEqual(self.a.life, life)


class CardNamedDescriptors(unittest.TestCase):
    def test_multi_word_name_matches(self):
        self.assertTrue(card_matches(HAWK, "a card named Test Hawk"))
        self.assertFalse(card_matches(BIG, "a card named Test Hawk"))

    def test_named_tilde_semantics(self):
        self.assertTrue(card_matches(HAWK, "a card named ~", HAWK))
        self.assertFalse(card_matches(BIG, "a card named ~", HAWK))
        # without a ref it matches nothing rather than everything
        self.assertFalse(card_matches(HAWK, "a card named ~"))
        self.assertFalse(card_matches(BIG, "a card named ~"))

    def test_wildcard_and_type_descriptors_still_work(self):
        self.assertTrue(card_matches(BIG, "a card"))
        self.assertTrue(card_matches(BIG, "a creature card"))
        self.assertFalse(card_matches(BIG, "a land card"))
        self.assertTrue(card_matches(ISLAND, "a basic land card"))
        self.assertFalse(card_matches(BIG, "a creature card with mana value 2 or less"))
        self.assertTrue(card_matches(BEAR, "a creature card with mana value 2 or less"))


class NamedSearchInGame(Chonk6):
    """The literal-name ETB search (Screaming Seahawk family) end to end."""

    def trigger_effects(self, c):
        (trig,) = c.triggers
        return [e for e in trig.effects if e.kind != "pay_gate"]

    def test_literal_multi_word_name_fetches_only_that_card(self):
        self.a.library = [ISLAND] * 5 + [HAWK, BIG, ISLAND] * 2 + [HAWK]
        self.a.hand = []
        effects = self.trigger_effects(HAWK)
        item = StackItem(self.a, effects, [], card=HAWK)
        self.resolve_all(self.a, effects, item)
        self.assertEqual([c.name for c in self.a.hand], ["Test Hawk"])

    def test_named_tilde_resolves_to_the_source_card(self):
        self.a.library = [ISLAND] * 5 + [SCREAMER, BIG, HAWK, ISLAND]
        self.a.hand = []
        effects = self.trigger_effects(SCREAMER)
        perm = self.perm(SCREAMER, self.a)
        item = StackItem(self.a, effects, [], source=perm)
        self.resolve_all(self.a, effects, item)
        self.assertEqual([c.name for c in self.a.hand], ["Screaming Testhawk"])

    def test_named_tilde_spell_item_uses_the_spell_card(self):
        self.a.library = [ISLAND] * 5 + [HAWK, SCREAMER, ISLAND]
        self.a.hand = []
        effects = self.trigger_effects(SCREAMER)
        item = StackItem(self.a, effects, [], card=SCREAMER)
        self.resolve_all(self.a, effects, item)
        self.assertEqual([c.name for c in self.a.hand], ["Screaming Testhawk"])


if __name__ == "__main__":
    unittest.main()

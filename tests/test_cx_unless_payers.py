"""#330: "unless" gates with counted costs, explicit payers and per-player decisions (cx_grammar_cond)."""
import dataclasses
import unittest

from mtgsim.engine import StackItem

from tests.test_cx_grammar import Base
from tests.test_templates import BEAR, card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
TOKEN_TEXT = "When this creature enters, sacrifice it unless you sacrifice a Forest."


def effects_of(text):
    from mtgsim.cards import parse as P
    return P._parse_effects(text)


class Base330(Base):
    def trigger(self, perm, n=0):
        """Resolve perm's n-th triggered ability with perm as its source."""
        effects = list(perm.card.triggers[n].effects)
        item = StackItem(perm.controller, effects, [None] * len(effects), source=perm, name=perm.card.name)
        self.game.stack.append(item)
        self.game.resolve_top()
        return item


class EtbReferent(Base330):
    def test_it_is_the_source_on_its_own_etb_or_attack_trigger(self):
        for text in (TOKEN_TEXT, "Whenever this creature attacks, sacrifice it unless you sacrifice an Island.",
                     "When this creature enters, exile it unless you discard a creature card."):
            c = card("Test Beast", "{1}{G}", "Creature — Beast", text, 3, 4)
            self.assertEqual(c.unsupported, [], text)
            kinds = [e.kind for e in c.triggers[0].effects]
            self.assertEqual(kinds[0], "cx_unless", text)
            self.assertIn(kinds[1], ("sacrifice_self", "exile_self"), text)

    def test_another_creature_entering_keeps_it_unmatched(self):
        c = card("Test Watcher", "{1}{B}", "Creature — Horror",
                 "Whenever another creature enters, sacrifice it unless you pay 2 life.", 2, 2)
        self.assertTrue(c.unsupported)                        # "it" is the entering creature, not ~

    def test_pay_keeps_it_and_decline_sacrifices_it(self):
        c = card("Test Beast", "{1}{G}", "Creature — Beast", TOKEN_TEXT, 3, 4)
        beast = self.perm(c, self.a)
        forest = self.perm(FOREST, self.a)
        self.trigger(beast)
        self.assertIn(beast, self.a.battlefield)
        self.assertNotIn(forest, self.a.battlefield)
        self.trigger(beast)                                   # no Forest left: unpayable
        self.assertNotIn(beast, self.a.battlefield)


class CountedSacrifice(Base330):
    LARVA = "At the beginning of your upkeep, sacrifice this creature unless you sacrifice two lands."

    def test_parse(self):
        effects, bad = effects_of("Sacrifice ~ unless you sacrifice two Swamps.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].data["costs"], [{"sacrifice": {"sub": ["Swamp"]}, "other": False, "count": 2}])
        effects, _ = effects_of("Sacrifice ~ unless you sacrifice four creatures.")
        self.assertEqual(effects[0].data["costs"][0]["count"], 4)

    def test_near_misses_stay_unmatched(self):
        for text in ("Sacrifice ~ unless you sacrifice two lands and pay 2 life.",
                     "Sacrifice ~ unless you sacrifice a land and pay 2 life.",        # one cost, not two steps
                     "Sacrifice ~ unless you sacrifice any number of creatures with total power 10 or greater.",
                     "Sacrifice ~ unless you sacrifice X lands."):
            _, bad = effects_of(text)
            self.assertTrue(bad, text)

    def larva(self):
        c = card("Test Larva", "{4}{R}{R}", "Creature — Beast", self.LARVA, 7, 6)
        self.assertEqual(c.unsupported, [])
        return self.perm(c, self.a)

    def test_pays_with_all_of_them(self):
        larva = self.larva()
        lands = [self.perm(SWAMP, self.a) for _ in range(3)]
        self.trigger(larva)
        self.assertIn(larva, self.a.battlefield)
        self.assertEqual(sum(x in self.a.battlefield for x in lands), 1)      # exactly two sacrificed
        self.assertEqual(len(self.a.graveyard), 2)

    def test_no_partial_payment(self):
        larva = self.larva()
        land = self.perm(SWAMP, self.a)
        self.perm(SWAMP, self.b)                              # the opponent's land doesn't count
        self.trigger(larva)
        self.assertIn(land, self.a.battlefield)               # one land is not enough: kept
        self.assertNotIn(larva, self.a.battlefield)

    def test_ai_declines_when_the_cost_is_worth_more_than_the_source(self):
        c = card("Test Hecatomb", "{1}{B}{B}", "Enchantment",
                 "When this enchantment enters, sacrifice it unless you sacrifice two creatures.")
        self.assertEqual(c.unsupported, [])
        ench = self.perm(c, self.a)
        bears = [self.perm(BEAR, self.a) for _ in range(2)]
        self.trigger(ench)
        self.assertNotIn(ench, self.a.battlefield)            # two Bears (2 x 4) > a 3-mana enchantment
        self.assertTrue(all(b in self.a.battlefield for b in bears))


class EachPlayer(Base330):
    MAULER = "Each player loses 4 life unless they sacrifice a nontoken creature."

    def test_parse(self):
        effects, bad = effects_of(self.MAULER)
        self.assertEqual((bad, [e.kind for e in effects]), ([], ["cx_unless_each"]))
        self.assertEqual([e.kind for e in effects[0].data["effects"]], ["lose_life"])
        effects, bad = effects_of("Each player sacrifices a permanent unless they discard a card.")
        self.assertEqual((bad, effects[0].kind), ([], "cx_unless_each"))
        for text in ("Each player draws a card unless they pay {1}.",            # no per-player body: unmatched
                     "Each player loses 4 life unless you sacrifice a creature."):  # one payer for everyone
            effects, bad = effects_of(text)
            self.assertTrue(bad or effects[0].kind != "cx_unless_each", text)

    def test_each_player_decides_for_themselves(self):
        spell = self.spell(self.MAULER, "Sorcery")
        bear = self.perm(BEAR, self.b)
        token = self.perm(dataclasses.replace(BEAR, is_token=True), self.a)
        self.cast(spell)
        self.assertNotIn(bear, self.b.battlefield)            # b sacrificed a nontoken creature: no life lost
        self.assertEqual(self.b.life, 20)
        self.assertIn(token, self.a.battlefield)              # a had only a token: can't pay, loses 4
        self.assertEqual(self.a.life, 16)

    def test_sacrifice_unless_discard(self):
        spell = self.spell("Each player sacrifices a permanent unless they discard a card.", "Sorcery")
        mine, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        self.a.hand, self.b.hand = [], [BEAR]
        self.cast(spell)
        self.assertNotIn(mine, self.a.battlefield)            # empty hand: sacrificed
        self.assertIn(theirs, self.b.battlefield)             # discarded instead
        self.assertEqual((self.b.hand, self.b.graveyard), ([], [BEAR]))

    def test_target_player_pays(self):
        spell = self.spell("Target player discards their hand unless they pay 7 life.", "Sorcery")
        self.b.hand = [BEAR, BEAR]
        self.cast(spell, targets=[None, self.b])
        self.assertEqual((self.b.life, len(self.b.hand)), (13, 2))
        self.cast(spell, targets=[None, self.b])              # 13 - 7 = 6 > 2: pays again
        self.b.life = 9                                       # 9 - 7 would leave 2: declines
        self.cast(spell, targets=[None, self.b])
        self.assertEqual((self.b.life, self.b.hand), (9, []))


class OpponentPays(Base330):
    TORMENTOR = "Draw a card unless target opponent sacrifices a creature or pays 3 life."

    def test_parse(self):
        for text in (self.TORMENTOR, "Draw a card unless an opponent pays {1}."):
            effects, bad = effects_of(text)
            self.assertEqual((bad, effects[0].kind, effects[0].data["payer"]), ([], "cx_unless", "opponent"), text)
        effects, bad = effects_of("Draw a card unless an opponent was dealt damage this turn.")
        self.assertTrue(bad)                                  # neither a cost nor a known condition

    def test_opponent_pays_from_their_resources(self):
        spell = self.spell(self.TORMENTOR, "Sorcery")
        bear = self.perm(BEAR, self.b)
        mine = self.perm(BEAR, self.a)
        hand = len(self.a.hand)
        self.cast(spell)
        self.assertNotIn(bear, self.b.battlefield)            # their creature, never mine
        self.assertIn(mine, self.a.battlefield)
        self.assertEqual((len(self.a.hand), self.a.life, self.b.life), (hand, 20, 20))     # payoff suppressed
        self.cast(spell)                                      # no creature: 3 life instead
        self.assertEqual((len(self.a.hand), self.b.life), (hand, 17))
        self.b.life = 5                                       # can't afford it: the payoff happens
        self.cast(spell)
        self.assertEqual((len(self.a.hand), self.b.life), (hand + 1, 5))


class AnyPlayer(Base330):
    def test_parse_reads_whose_interest_it_is(self):
        cases = {"Sacrifice ~ unless any player pays {3}.": "controller",
                 "~ gets +1/+1 until end of turn unless any player pays {2}.": "opponents",
                 "You gain 3 life unless any player pays {1}.": "opponents"}
        for text, against in cases.items():
            effects, bad = effects_of(text)
            self.assertEqual((bad, effects[0].data["payer"], effects[0].data["against"]), ([], "any", against))
        for text in ("Destroy target creature unless any player pays {1}.",       # either side may care
                     "~ gets -1/-1 until end of turn unless any player pays {1}."):
            _, bad = effects_of(text)
            self.assertTrue(bad, text)

    def prison(self):
        c = card("Test Prison", "{U}", "Enchantment",
                 "At the beginning of your upkeep, sacrifice this enchantment unless any player pays {3}.")
        self.assertEqual(c.unsupported, [])
        return self.perm(c, self.a)

    def test_controller_pays_to_keep_it(self):
        prison = self.prison()
        lands = [self.perm(self.island_card(), self.a) for _ in range(3)]
        theirs = [self.perm(self.island_card(), self.b) for _ in range(3)]
        self.trigger(prison)
        self.assertIn(prison, self.a.battlefield)
        self.assertTrue(all(x.tapped for x in lands))
        self.assertFalse(any(x.tapped for x in theirs))       # the opponent never pays to keep it for you

    def test_nobody_pays_and_it_goes(self):
        prison = self.prison()
        for _ in range(3):
            self.perm(self.island_card(), self.b)             # only the opponent could pay: they won't
        self.trigger(prison)
        self.assertNotIn(prison, self.a.battlefield)

    def test_an_opponent_pays_to_deny_a_benefit(self):
        spell = self.spell("You gain 3 life unless any player pays {1}.", "Sorcery")
        land = self.perm(self.island_card(), self.b)
        mine = self.perm(self.island_card(), self.a)
        self.cast(spell)
        self.assertEqual((self.a.life, land.tapped, mine.tapped), (20, True, False))
        self.cast(spell)                                      # their land is tapped now: the payoff happens
        self.assertEqual(self.a.life, 23)

    @staticmethod
    def island_card():
        from tests.test_templates import ISLAND
        return ISLAND


class PayerWordsWithoutACost(unittest.TestCase):
    def test_a_condition_after_payer_words_is_still_a_condition(self):
        effects, bad = effects_of("You lose 4 life unless you attacked this turn.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].cond, 'lib:["not","attacked_turn"]')

    def test_a_delayed_trigger_is_not_gated_now(self):
        _, bad = effects_of("At the beginning of the next end step, exile those tokens unless you have the "
                            "city's blessing.")
        self.assertTrue(bad)


if __name__ == "__main__":
    unittest.main()

"""#330: "unless" gates with counted costs, explicit payers and per-player decisions (cx_grammar_cond)."""
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


if __name__ == "__main__":
    unittest.main()

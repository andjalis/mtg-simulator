"""mega-batch4 (5): the live graveyard/exile/token clusters from the census ranking.

"Create X <desc> tokens" (no ", where X is" clause) is sized by the X paid: the SUBS
rewrites it to a one-token sentence and marks it data x (the token kind reads item.x) —
March of the Multitudes, Empty the Pits, Firecat Blitz. "You may exile a <desc> card from
your graveyard. If you do, <X>." is the exile twin of MAYSACSELF: a pay_exile_gy gate
(Aphemia, Masked Vandal).
"""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem
from tests.test_batch1 import Batch1
from tests.test_templates import BEAR, card

MARCH = card("Test March", "{X}{W}{W}", "Instant",
             "Create X 1/1 white Soldier creature tokens with lifelink.")
APHEMIA = card("Test Aphemia", "{1}{B}", "Creature — Harpy",
               "At the beginning of your end step, you may exile an enchantment card "
               "from your graveyard. If you do, create a 2/2 black Zombie creature token.", 2, 1)
VANDAL = card("Test Vandal", "{1}{G}", "Creature — Shapeshifter",
              "When Test Vandal enters, you may exile a creature card from your "
              "graveyard. If you do, exile target artifact or enchantment an opponent "
              "controls.", 1, 3)


class XTokenParse(unittest.TestCase):
    def test_plain_x_tokens(self):
        for text in ("create X 1/1 white Soldier creature tokens with lifelink",
                     "create X tapped 2/2 black Zombie creature tokens",
                     "create X 1/1 red Elemental Cat creature tokens with haste"):
            effects, bad = _parse_effects(text)
            self.assertFalse(bad, text)
            (e,) = effects
            self.assertEqual((e.kind, e.amount, e.data.get("x")), ("token", 1, True), text)

    def test_where_variants_unchanged(self):
        effects, bad = _parse_effects(
            "create X 2/2 black Zombie creature tokens, where X is the sacrificed "
            "creature's power.")
        self.assertFalse(bad, bad)
        self.assertEqual(effects[0].data.get("xq"), ("sac", "power"))
        self.assertNotIn("x", effects[0].data or {"x": None} if "x" not in effects[0].data else effects[0].data)

    def test_template(self):
        self.assertEqual(MARCH.unsupported, [])


class XTokenBehavior(Batch1):
    def test_x_tokens_read_the_paid_x(self):
        effects, bad = _parse_effects(
            "create X 1/1 white Soldier creature tokens with lifelink.")
        self.assertFalse(bad, bad)
        item = StackItem(self.a, effects, [None])
        item.x = 4
        self.g.resolve(self.a, effects[0], None, item)
        self.assertEqual(len(self.a.battlefield), 4)
        self.assertTrue(all(x.card.is_creature for x in self.a.battlefield))


class ExileGyGateParse(unittest.TestCase):
    def test_templates(self):
        self.assertEqual(APHEMIA.unsupported, [])
        self.assertEqual(VANDAL.unsupported, [])

    def test_gate_and_paid_payoff(self):
        effects, bad = _parse_effects(
            "you may exile an enchantment card from your graveyard. if you do, "
            "create a 2/2 black Zombie creature token.")
        self.assertFalse(bad, bad)
        self.assertEqual([(e.kind, e.filter, e.cond) for e in effects],
                         [("pay_exile_gy", "enchantment", ""), ("token", "", "paid")])


class ExileGyGateBehavior(Batch1):
    def resolve_gate(self, gy):
        effects, bad = _parse_effects(
            "you may exile a creature card from your graveyard. if you do, "
            "create a 2/2 black Zombie creature token.")
        self.assertFalse(bad, bad)
        self.a.graveyard = gy
        item = StackItem(self.a, effects, [None, None])
        self.g.stack.append(item)
        self.g.resolve_top()
        return item

    def test_pays_the_worst_matching_card(self):
        item = self.resolve_gate([BEAR, APHEMIA])
        self.assertTrue(item.gate_paid)
        self.assertEqual([c.name for c in self.a.graveyard], ["Test Aphemia"])
        self.assertEqual(len(self.a.battlefield), 1)      # the payoff token

    def test_no_match_no_payoff(self):
        from tests.test_templates import ISLAND
        n = len(self.a.battlefield)
        item = self.resolve_gate([ISLAND])                # not a creature card
        self.assertFalse(item.gate_paid)
        self.assertEqual([c.name for c in self.a.graveyard], ["Island"])
        self.assertEqual(len(self.a.battlefield), n)

    def test_empty_graveyard_no_payoff(self):
        item = self.resolve_gate([])
        self.assertFalse(item.gate_paid)
        self.assertEqual(len(self.a.battlefield), 0)


class ClusterDatabase(unittest.TestCase):

    def test_cards(self):
        try:
            from mtgsim.carddb import CardDB
            from mtgsim.coverage import FULL, card_coverage
            db = CardDB()
        except Exception:
            self.skipTest("card database not built")
        if db._all is None:
            self.skipTest("card database not built")
        for name in ("March of the Multitudes", "Empty the Pits", "Aphemia, the Cacophony",
                     "Masked Vandal", "Ghoulcaller Gisa"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()

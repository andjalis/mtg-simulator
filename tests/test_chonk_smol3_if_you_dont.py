"""smol-chonk-3 batch 4, mined cluster: "If you don't, <effect>" after a "you may" gate.

The "you may ..." sentences ahead of it parse into a pay_gate the engine always takes
(Game.pay_gate_cost), so the fallback effect carries cond "!paid" — consistent with that model,
it never fires, and the Ostrich-Horse / Ainok Wayfarer wording family parses fully.
"""
import unittest

from mtgsim.cards.parse import _parse_effects
from tests.test_templates import card

OSTRICH = card("Ostrich-Horse", "{1}{W}", "Creature — Beast",
               "When this creature enters, mill three cards. You may put a land card from among "
               "them into your hand. If you don't, put a +1/+1 counter on this creature.", 2, 3)


class IfYouDont(unittest.TestCase):
    def test_rider_attaches_not_paid(self):
        effects, bad = _parse_effects("mill three cards. You may put a land card from among them "
                                      "into your hand. If you don't, put a +1/+1 counter on ~.")
        self.assertEqual(bad, [])
        self.assertEqual([e.kind for e in effects], ["mill", "pay_gate", "mill_pick", "p1_counters"])
        self.assertEqual(effects[-1].cond, "!paid")
        self.assertEqual(effects[-1].target, "self")

    def test_rider_stays_unmatched_without_a_gate(self):
        effects, bad = _parse_effects("Draw a card. If you don't, put a +1/+1 counter on ~.")
        self.assertEqual([e.kind for e in effects], ["draw"])
        self.assertEqual(len(bad), 1)

    def test_wording_family_parses(self):
        self.assertEqual(OSTRICH.unsupported, [])
        etb = [t for t in OSTRICH.triggers if t.event == "etb"][0]
        self.assertEqual([e.kind for e in etb.effects],
                         ["mill", "pay_gate", "mill_pick", "p1_counters"])


if __name__ == "__main__":
    unittest.main()

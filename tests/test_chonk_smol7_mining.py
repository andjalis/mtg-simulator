"""smol-chonk-7 batch 8, priority 6 mining: hybrid "you may pay {U/B}" gates.

The pay-gate sentence took only plain symbols; hybrid ones now parse too
(parse_mana_cost simplifies {U/B} to its first coloured half). Kels, Fight Fixer's
"Whenever you sacrifice a creature, you may pay {U/B}. If you do, draw a card."
promotes fully; Shu Yun, the Silent Tempest and Killian's Confidence ride the same fix.
"""
import unittest

from mtgsim.cards.parse import _parse_effects
from tests.test_templates import card

KELS = card("Kels, Fight Fixer", "{1}{U}{B}", "Legendary Creature — Zombie Wizard",
            "Menace\nWhenever you sacrifice a creature, you may pay {U/B}. If you do, "
            "draw a card.", 3, 3)


class HybridPayGate(unittest.TestCase):
    def test_hybrid_pay_gate(self):
        effects, bad = _parse_effects("You may pay {U/B}.")
        self.assertEqual(bad, [])
        [e] = effects
        self.assertEqual(e.kind, "pay_gate")
        self.assertEqual(e.data["cost"], {"generic": 0, "U": 1})   # first coloured half, per parse_mana_cost

    def test_if_you_do_rides_the_gate(self):
        effects, bad = _parse_effects("You may pay {U/B}. If you do, draw a card.")
        self.assertEqual(bad, [])
        self.assertEqual([e.kind for e in effects], ["pay_gate", "draw"])
        self.assertEqual(effects[-1].cond, "paid")

    def test_plain_pay_gate_still_works(self):
        effects, bad = _parse_effects("You may pay {3}.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].data["cost"], {"generic": 3})

    def test_kels_parses_fully(self):
        self.assertEqual(KELS.unsupported, [])
        [t] = [x for x in KELS.triggers if x.event == "sacrifice"]
        self.assertEqual([e.kind for e in t.effects], ["pay_gate", "draw"])
        self.assertEqual(t.effects[-1].cond, "paid")


if __name__ == "__main__":
    unittest.main()

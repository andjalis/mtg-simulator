"""mega-batch4 (5): energy pay gates — "you may pay {E}{E}. If you do, ..." riders.

Trigger-rider energy gates (Conduit Goblin, Glint-Sleeve Siphoner) become a
``pay_energy`` gate effect (check and deduct p.counters["energy"], set item.gate_paid)
followed by the payoff effects with cond "paid" — the pay_gate pattern, without touching
costs.py. Activated-ability energy costs ("Pay {E}{E}:") already worked; the word-number
variants ("Pay eight {E}:") and the free-payment mis-parse of "sacrifice ~ unless you pay
{E}{E}" are cross-area needs (see the batch report).
"""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem
from tests.test_batch1 import Batch1
from tests.test_templates import card

GOBLIN = card("Test Conduit", "{R}{W}", "Creature — Goblin",
              "When Test Conduit enters, you get {E}{E}.\nAt the beginning of combat on "
              "your turn, you may pay {E}. If you do, another target creature you control "
              "gets +1/+0 and gains haste until end of turn.", 2, 2)
SIPHONER = card("Test Siphoner", "{1}{B}", "Creature — Human Rogue",
                "Whenever Test Siphoner enters or attacks, you get {E}.\nAt the beginning "
                "of your upkeep, you may pay {E}{E}. If you do, you draw a card and you "
                "lose 1 life.", 2, 1)


class EnergyGateParse(unittest.TestCase):
    def test_templates(self):
        self.assertEqual(GOBLIN.unsupported, [])
        self.assertEqual(SIPHONER.unsupported, [])

    def test_gate_and_paid_payoff(self):
        effects, bad = _parse_effects(
            "you may pay {E}{E}. If you do, you draw a card and you lose 1 life.")
        self.assertFalse(bad, bad)
        self.assertEqual([(e.kind, e.amount, e.cond) for e in effects],
                         [("pay_energy", 2, ""), ("draw", 1, "paid"),
                          ("lose_life", 1, "paid")])

    def test_when_you_do_variant(self):
        effects, bad = _parse_effects(
            "you may pay {E}. When you do, draw a card.")
        self.assertFalse(bad, bad)
        self.assertEqual([(e.kind, e.cond) for e in effects],
                         [("pay_energy", ""), ("draw", "paid")])


class EnergyGateBehavior(Batch1):
    def run_gate(self, energy):
        effects, bad = _parse_effects(
            "you may pay {E}{E}. If you do, you draw a card and you lose 1 life.")
        self.assertFalse(bad, bad)
        self.a.counters["energy"] = energy
        item = StackItem(self.a, effects, [None, None, None], kind="trigger")
        self.g.stack.append(item)
        self.g.resolve_top()
        return item

    def test_pays_and_runs_the_payoff(self):
        item = self.run_gate(3)
        self.assertTrue(item.gate_paid)
        self.assertEqual(self.a.counters["energy"], 1)
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual(self.a.life, 19)

    def test_no_energy_no_payoff(self):
        item = self.run_gate(1)
        self.assertFalse(item.gate_paid)
        self.assertEqual(self.a.counters["energy"], 1)
        self.assertEqual(self.a.hand, [])
        self.assertEqual(self.a.life, 20)


class EnergyGateDatabase(unittest.TestCase):

    def test_cards(self):
        try:
            from mtgsim.carddb import CardDB
            from mtgsim.coverage import FULL, card_coverage
            db = CardDB()
        except Exception:
            self.skipTest("card database not built")
        if db._all is None:
            self.skipTest("card database not built")
        for name in ("Conduit Goblin", "Glint-Sleeve Siphoner"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()

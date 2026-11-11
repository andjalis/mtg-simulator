"""'If ~ was kicked, B instead.' replaces the effect it stands in for; the kicked spell never runs both (#321)."""
import unittest

from tests.test_templates import card


def kicked(text, kind="Sorcery"):
    c = card("Zork", "{1}{R}", kind, "Kicker {2}\n" + text)
    alt = next(a for a in c.alt_costs if a.kind == "kicker")
    return c, [(e.kind, e.amount, e.target) for e in alt.effects]


class KickerInstead(unittest.TestCase):
    def test_pump_is_replaced_and_keyword_follows(self):
        c, eff = kicked("Target creature gets +2/+2 until end of turn. If ~ was kicked, that creature gets +4/+4 "
                        "and gains trample until end of turn instead.")
        self.assertEqual(c.unsupported, [])
        self.assertEqual(eff, [("pump", 4, "creature"), ("grant", 0, "prev")])
        self.assertEqual([(e.kind, e.amount) for e in c.spell_effects], [("pump", 2)])

    def test_damage_swapped_with_extra_effect(self):
        c, eff = kicked("~ deals 2 damage to target creature. If ~ was kicked, ~ deals 5 damage to that creature "
                        "and you gain 2 life instead.")
        self.assertEqual(c.unsupported, [])
        self.assertEqual(eff, [("damage", 5, "creature"), ("gain_life", 2, "none")])

    def test_draw_and_leading_instead(self):
        c, eff = kicked("Draw a card. If ~ was kicked, draw three cards instead.")
        self.assertEqual(eff, [("draw", 3, "none")])
        c, eff = kicked("Destroy target creature. If ~ was kicked, instead destroy target creature or planeswalker.")
        self.assertEqual([k for k, *_ in eff], ["destroy"])
        self.assertEqual(c.unsupported, [])

    def test_counter_unless_pay_becomes_hard_counter(self):
        c, eff = kicked("Counter target spell unless its controller pays {2}. If ~ was kicked, instead counter "
                        "target spell.", "Instant")
        self.assertEqual(eff, [("counter", 0, "spell")])

    def test_different_kind_replaces_the_only_effect(self):
        c, eff = kicked("Exile target creature. If ~ was kicked, return target creature card from your graveyard "
                        "to your hand instead.")
        self.assertEqual([k for k, *_ in eff], ["gy_move"])

    def test_ambiguous_replacement_stays_unmatched(self):
        c = card("Zork", "{1}{R}", "Sorcery", "Kicker {2}\nDraw a card. Target creature gets +1/+1 until end of turn. "
                 "If ~ was kicked, destroy target land instead.")
        self.assertTrue(c.unsupported)
        alt = next(a for a in c.alt_costs if a.kind == "kicker")
        self.assertEqual([e.kind for e in alt.effects], ["draw", "pump"])


if __name__ == "__main__":
    unittest.main()

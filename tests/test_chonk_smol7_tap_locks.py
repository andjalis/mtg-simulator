"""smol-chonk-7 batch 8, priority 2: tap-lock rider recording (parser side).

"... doesn't untap during its controller's untap step for as long as ~ remains tapped /
you control ~ / ~ remains on the battlefield" (Amber Prison, Dungeon Geists, Time of Ice):
the rider attaches to the preceding tap effect as data["lock"] = "tapped" / "controlled" /
"battlefield" plus the honest freeze subset (one skipped untap step). The engine half
that records the frozen_by/locked_by/net_locked_by link the AI's choose_stay_tapped
reads is still pending — the approximation note says so.
"""
import unittest

from mtgsim.cards.parse import _parse_effects
from tests.test_templates import card

AMBER = card("Amber Prison", "{4}", "Artifact",
             "You may choose not to untap this artifact during your untap step.\n"
             "{4}, {T}: Tap target artifact, creature, or land. That permanent doesn't untap "
             "during its controller's untap step for as long as this artifact remains tapped.")
GEISTS = card("Dungeon Geists", "{2}{U}{U}", "Creature — Spirit",
              "Flying\nWhen this creature enters, tap target creature an opponent controls. "
              "That creature doesn't untap during its controller's untap step for as long "
              "as you control this creature.", 3, 3)
KRAKEN = card("Shipbreaker Kraken", "{4}{U}{U}", "Creature — Kraken",
              "When this creature becomes monstrous, tap up to four target creatures. Those "
              "creatures don't untap during their controllers' untap steps for as long as you "
              "control this creature.", 6, 6)
TIME_OF_ICE = card("Time of Ice", "{2}{U}", "Enchantment — Saga",
                   "I, II — Tap target creature an opponent controls. It doesn't untap during "
                   "its controller's untap step for as long as you control this Saga.\n"
                   "III — Return all tapped creatures to their owners' hands.")


class TapLockRider(unittest.TestCase):
    def test_rider_attaches_to_activated_tap(self):
        effects, bad = _parse_effects("Tap target artifact, creature, or land. That permanent "
                                      "doesn't untap during its controller's untap step for as "
                                      "long as ~ remains tapped.")
        self.assertEqual(bad, [])
        [e] = effects
        self.assertEqual(e.kind, "tap")
        self.assertEqual(e.data["lock"], "tapped")
        self.assertTrue(e.data["freeze"])

    def test_control_duration_rider(self):
        effects, bad = _parse_effects("Tap target creature an opponent controls. That creature "
                                      "doesn't untap during its controller's untap step for as "
                                      "long as you control ~.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].data["lock"], "controlled")

    def test_battlefield_duration_rider(self):
        effects, bad = _parse_effects("Tap target creature. That creature doesn't untap during "
                                      "its controller's untap step for as long as ~ remains on "
                                      "the battlefield.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].data["lock"], "battlefield")

    def test_plural_riders(self):
        effects, bad = _parse_effects("Tap up to four target creatures. Those creatures don't "
                                      "untap during their controllers' untap steps for as long "
                                      "as you control ~.")
        self.assertEqual(bad, [])
        [e] = effects
        self.assertEqual((e.kind, e.amount, e.data["lock"]), ("tap", 4, "controlled"))

    def test_group_tap_carries_the_lock_inside(self):
        effects, bad = _parse_effects("Tap all other artifacts. They don't untap during their "
                                      "controllers' untap steps for as long as ~ remains tapped.")
        self.assertEqual(bad, [])
        [e] = effects
        self.assertEqual(e.kind, "permanent_group")
        self.assertEqual(e.data["effect"].data["lock"], "tapped")

    def test_rider_without_a_tap_stays_unmatched(self):
        effects, bad = _parse_effects("Draw a card. That creature doesn't untap during its "
                                      "controller's untap step for as long as ~ remains tapped.")
        self.assertEqual([e.kind for e in effects], ["draw"])
        self.assertEqual(len(bad), 1)

    def test_real_cards_carry_the_lock(self):
        for c, where in ((AMBER, "activated"), (GEISTS, "trigger"), (KRAKEN, "trigger")):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
                pools = c.activated if where == "activated" else c.triggers
                locks = [e.data.get("lock") for pool in pools for e in pool.effects
                         if e.data.get("lock")]
                if locks:
                    self.assertEqual(locks, ["tapped" if c is AMBER else "controlled"])

    def test_saga_chapters_carry_the_lock(self):
        self.assertEqual(TIME_OF_ICE.unsupported, [])
        self.assertEqual([e.data.get("lock") for ch in TIME_OF_ICE.chapters[:2] for e in ch],
                         ["controlled", "controlled"])

    def test_approximation_note(self):
        self.assertTrue(any("single skipped untap step" in a for a in AMBER.approximations))
        self.assertTrue(any("single skipped untap step" in a for a in GEISTS.approximations))


if __name__ == "__main__":
    unittest.main()

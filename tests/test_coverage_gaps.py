import unittest

from scripts.coverage_gaps import greedy_plan, keyword_group, normalize_line


class NormalizeLineTests(unittest.TestCase):
    def test_normalizes_names_numbers_mana_colours_and_reminders(self):
        self.assertEqual(
            normalize_line("When Test Dragon enters, add {R}{G} (They become tapped) for two red mana.",
                           "Test Dragon"),
            "When ~ enters, add {M} for N COLOR mana")

    def test_replaces_face_prefix_and_face_names(self):
        self.assertEqual(normalize_line("Back Face: Return Front Face to your hand.",
                                        "Front Face // Back Face"),
                         "Return ~ to your hand")

    def test_keyword_group_uses_heading(self):
        self.assertEqual(keyword_group("Cumulative upkeep {M}"), "Cumulative upkeep")
        self.assertEqual(keyword_group("Forestwalk"), "Forestwalk")
        self.assertIsNone(keyword_group("Exile target creature"))
        self.assertIsNone(keyword_group("When ~ enters the battlefield, draw a card"))


class GreedyPlanTests(unittest.TestCase):
    def test_greedy_plan_counts_only_newly_completed_cards(self):
        plan = greedy_plan({
            "A": {"alpha"},
            "B": {"alpha", "beta"},
            "C": {"beta"},
            "D": {"alpha", "gamma"},
            "E": {"gamma"},
        }, top=3)
        self.assertEqual([step["pattern"] for step in plan], ["alpha", "beta", "gamma"])
        self.assertEqual([step["unlocked"] for step in plan], [1, 2, 2])
        self.assertEqual([step["cumulative"] for step in plan], [1, 3, 5])

    def test_ties_are_stable_and_top_is_respected(self):
        plan = greedy_plan({"A": {"z"}, "B": {"a"}}, top=1)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["pattern"], "a")
        self.assertEqual(plan[0]["cards"], ["B"])


if __name__ == "__main__":
    unittest.main()

"""Quantity-based "Add mana" sentences (mtgsim.cx_grammar_addmana, #332): parser side."""
import unittest

from tests.test_templates import card


def spell(text, types="Instant", cost="{R}"):
    c = card("Test Spell", cost, types, text)
    assert c.unsupported == [], (text, c.unsupported)
    return c


class Parsing(unittest.TestCase):
    def test_positive_sentences(self):
        cases = {
            "Add {R} for each Goblin on the battlefield.":
                ("add_mana", {"colors": ["R"], "xq": ("cxq", "perms", {"selector": {"subtypes": ["goblin"],
                                                                                      "types_any": ["permanent"]}})}),
            "add {B} for each charge counter on ~.": ("add_mana", {"colors": ["B"], "xq": ("counters", "charge")}),
            "Add {B} for each black creature card in your graveyard.":
                ("add_mana", {"colors": ["B"], "xq": ("cxq", "cards", "your_gy", {"colors": ["B"], "types": ["creature"]})}),
            "Add one mana of any color for each charge counter removed this way.":
                ("add_mana", {"colors": [], "choice": ["W", "U", "B", "R", "G"], "xq": ("this_way", "removed", "charge")}),
            "Add {B} or {G} for each permanent destroyed this way.":
                ("add_mana", {"colors": [], "choice": ["B", "G"], "xq": ("this_way", "destroyed", "permanent")}),
            "Add {R} for each card in your hand.":
                ("add_mana", {"colors": ["R"], "xq": ("cxq", "cards", "your_hand", {})}),
        }
        for text, (kind, data) in cases.items():
            c = spell(text)
            self.assertEqual(len(c.spell_effects), 1, text)
            e = c.spell_effects[0]
            self.assertEqual(e.kind, kind, text)
            self.assertEqual(e.data, data, text)

    def test_activated_ability_sentence(self):
        c = card("Test Crypt", types="Land — Swamp", text="{T}: Add {B}.\n{2}, {T}: Add {B} for each black creature "
                                                          "card in your graveyard.")
        self.assertEqual(c.unsupported, [])
        act = c.activated[0]
        self.assertEqual(act.cost, {"generic": 2})
        self.assertEqual(act.extra_costs, {"tap": True})
        self.assertEqual([e.kind for e in act.effects], ["add_mana"])
        self.assertEqual(act.effects[0].data["xq"], ("cxq", "cards", "your_gy", {"colors": ["B"], "types": ["creature"]}))

    def test_refusals_stay_visible(self):
        """Quantities with no fixed referent (or not this family's verbs) must not match."""
        for text in ("Add {R} for each card in target opponent's hand.",
                     "Add {C} for each {S} spent to cast this spell.",
                     "Add {R} for each card revealed this way.",
                     "Add {R} for each card discarded this way.",
                     "Add {R} for each card named Rite of Flame in each graveyard.",
                     "Add {R} for each 1 life your opponents have lost this turn.",
                     "Add {R} for each creature that died this way."):
            c = card("Test Spell", "{R}", "Instant", text)
            self.assertEqual(len(c.unsupported), 1, text)      # stays unmatched and visible
            self.assertIn("for each", c.unsupported[0])


if __name__ == "__main__":
    unittest.main()

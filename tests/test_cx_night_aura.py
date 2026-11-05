"""You control enchanted permanent; goaded Auras."""
import unittest

from tests.test_templates import card

CONFISCATE = card("Test Confiscate", "{4}{U}{U}", "Enchantment — Aura", "Enchant permanent\nYou control enchanted permanent.")
IMPETUS = card("Test Impetus", "{1}{R}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1 and is goaded.")
GHOUL = card("Test Ghoul", "{1}{B}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1, has deathtouch, and is goaded.")
PLAIN = card("Test Plain", "{1}{R}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1 and attacks each combat if able.")


class AuraLines(unittest.TestCase):
    def test_control_enchanted_permanent(self):
        self.assertEqual(CONFISCATE.unsupported, [])
        self.assertTrue(CONFISCATE.advanced_rules.get("aura_control"))

    def test_goaded_reads_as_attacks_each_combat(self):
        self.assertEqual(IMPETUS.unsupported, [])
        self.assertEqual(IMPETUS.equip_keywords, PLAIN.equip_keywords)
        self.assertEqual(GHOUL.unsupported, [])
        self.assertIn("must_attack_now", repr(GHOUL.advanced_rules))
        self.assertIn("deathtouch", repr(GHOUL.advanced_rules))


if __name__ == "__main__":
    unittest.main()

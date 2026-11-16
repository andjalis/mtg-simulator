"""#743: a Station "N+ | ..." tier on a card's last line is closed like any other: its triggers and activations wait
for N charge counters, and a static it adds (which the gate can't cover) is an approximation, not full."""
import unittest

from tests.test_cx_grammar import DB_FILE


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Parse(unittest.TestCase):
    def test_last_line_static_is_an_approximation(self):
        for name, n in (("Class-4 Tactical Cube", 7), ("Land Station", 10), ("The Seriema", 7)):
            c = db(name)
            self.assertIn(f"tier {n}+ effect applies without needing {n} charge counters", c.approximations, name)

    def test_last_line_trigger_is_gated(self):
        for name, n in (("Sledge-Class Seedship", 7), ("Entropic Battlecruiser", 8), ("Starship Enterprise", 16)):
            gates = [t.data.get("trigger_gate") for t in db(name).triggers]
            self.assertIn(f"charge>={n}", gates, name)

    def test_tier_trigger_with_an_ability_word(self):
        c = db("U.S.S. Prometheus, Prototype")
        self.assertEqual(c.unsupported, [])
        self.assertEqual([t.data.get("trigger_gate") for t in c.triggers], ["charge>=8"])

    def test_gated_trigger_tier_is_not_an_approximation(self):
        for name in ("D-7 Battle Cruiser", "Synthesizer Labship"):
            self.assertFalse([a for a in db(name).approximations if a.startswith("tier ")], name)


if __name__ == "__main__":
    unittest.main()

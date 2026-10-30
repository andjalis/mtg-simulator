"""mega-batch6 (3): "put into a graveyard from anywhere".

The Blightsteel Colossus replacement ("If ~ would be put into a graveyard from anywhere,
reveal ~ and shuffle it into its owner's library instead") and the Eldrazi trigger
("When ~ is put into a graveyard from anywhere, its owner shuffles their graveyard into
their library") join the Lorwyn-incarnation wording of the TRIGGERS table: the engine has
no put-into-graveyard-from-anywhere event, so all three are approximated as dies
triggers — the card is taken out of its owner's graveyard (or the whole graveyard is
shuffled away) when it dies. Discards and mills don't fire them yet; see the batch
report for the zone-arrival hooks that would make that real.
"""
import unittest

from tests.test_batch1 import Batch1
from tests.test_templates import card

BLIGHTSTEEL = card("Test Colossus", "{12}", "Artifact Creature — Golem",
                   "If Test Colossus would be put into a graveyard from anywhere, reveal "
                   "Test Colossus and shuffle it into its owner's library instead.", 11, 11)
EMRAKUL = card("Test Emrakul", "{15}", "Creature — Eldrazi",
               "When Test Emrakul is put into a graveyard from anywhere, its owner "
               "shuffles their graveyard into their library.", 15, 15)


class PutAnywherewhereParse(unittest.TestCase):
    def test_replacement_becomes_a_dies_shuffle(self):
        self.assertEqual(BLIGHTSTEEL.unsupported, [])
        (trig,) = [t for t in BLIGHTSTEEL.triggers if t.event == "dies"]
        self.assertEqual([(e.kind, e.target) for e in trig.effects], [("shuffle_away", "self")])

    def test_eldrazi_trigger_shuffles_the_graveyard(self):
        self.assertNotIn("When Test Emrakul is put into a graveyard from anywhere, its owner "
                         "shuffles their graveyard into their library.", EMRAKUL.unsupported)
        (trig,) = [t for t in EMRAKUL.triggers if t.event == "dies"]
        self.assertEqual(trig.effects[0].kind, "shuffle_gy")


class PutAnywherewhereBehavior(Batch1):
    def test_colossus_dies_to_the_library_not_the_graveyard(self):
        colossus = self.put(BLIGHTSTEEL)
        self.g.dies(colossus)
        self.g.flush_triggers()
        while self.g.stack:
            self.g.resolve_top()
            self.g.settle()
        self.assertEqual(self.a.graveyard, [])
        self.assertIn(colossus.card.name, [c.name for c in self.a.library])

    def test_emrakul_death_empties_the_graveyard_into_the_library(self):
        self.a.graveyard.append(BLIGHTSTEEL)
        emrakul = self.put(EMRAKUL)
        self.g.dies(emrakul)
        self.g.flush_triggers()
        while self.g.stack:
            self.g.resolve_top()
            self.g.settle()
        self.assertEqual(self.a.graveyard, [])     # the trigger shuffles the whole
        self.assertIn("Test Colossus", [c.name for c in self.a.library])   # graveyard, Emrakul included
        self.assertIn("Test Emrakul", [c.name for c in self.a.library])


if __name__ == "__main__":
    unittest.main()

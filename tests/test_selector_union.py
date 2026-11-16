"""#506: a shared modifier on a type union in permanent selectors.

"nontoken artifact or creature" = nontoken (artifact or creature); a leading adjective distributes to the bare
alternatives after it; a bare subtype takes the head type of "Elf or Soldier creature"; anything else is read as
written as an "alts" list (each alternative ANDed, alternatives ORed)."""
import dataclasses
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.permanent_templates import matches, selector

from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import BEAR, ISLAND, card

VEHICLE = card("Test Wagon", "{2}", "Artifact — Vehicle", "Crew 1", 3, 3)
ELF = card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)
SOLDIER = card("Test Soldier", "{W}", "Creature — Soldier", "", 1, 1)
ELF_TRIBAL = card("Test Elf Kindred", "{G}", "Kindred Enchantment — Elf", "")
WOLF = card("Test Wolf", "{G}", "Creature — Wolf", "", 2, 2)


class Reading(unittest.TestCase):
    def test_leading_adjectives_distribute_to_bare_alternatives(self):
        self.assertEqual(selector("tapped creature or Vehicle"), {"alts": [("tapped", "creature"), ("tapped", "vehicle")]})
        self.assertEqual(selector("attacking Wolf or Werewolf"),
                         {"traits": ["attacking"], "subtypes_any": ["wolf", "werewolf"], "types_any": ["permanent"]})
        self.assertEqual(selector("attacking Cleric, Rogue, Warrior, or Wizard")["subtypes_any"],
                         ["cleric", "rogue", "warrior", "wizard"])

    def test_bare_subtype_takes_the_last_head_type(self):
        self.assertEqual(selector("Elf or Soldier creature"), {"subtypes_any": ["elf", "soldier"], "types_all": ["creature"]})
        # a land subtype doesn't take a creature head, and "enchantment creature" is an intersection, not a head
        self.assertEqual(selector("Forest or green creature"), {"alts": [("forest",), ("green", "creature")]})
        self.assertEqual(selector("Saga or enchantment creature"), {"alts": [("saga",), ("enchantment", "creature")]})

    def test_modifier_after_the_noun_or_on_a_later_alternative_does_not_distribute(self):
        self.assertEqual(selector("creature token or artifact"), {"alts": [("creature", "token"), ("artifact",)]})
        self.assertEqual(selector("artifact, enchantment, or tapped creature"),
                         {"alts": [("artifact",), ("enchantment",), ("tapped", "creature")]})
        self.assertEqual(selector("Elf creature or artifact"), {"alts": [("elf", "creature"), ("artifact",)]})

    def test_refusals(self):
        for text in ("artifact or nontoken", "nontoken or creature", "creature, artifact", "artifact or flying creature",
                     "nontoken artifacts and creatures", "artifact or creature token with flying power"):
            with self.subTest(text=text):
                self.assertIsNone(selector(text, plural=text.endswith("s")))


class Matching(Base):
    def spec_fits(self, text, perm):
        return matches(self.game, perm, selector(text), self.a)

    def test_distributed_tapped_applies_to_the_vehicle_too(self):
        wagon, bear = self.perm(VEHICLE, self.b), self.perm(BEAR, self.b)
        self.assertFalse(self.spec_fits("tapped creature or Vehicle", wagon))
        self.assertFalse(self.spec_fits("tapped creature or Vehicle", bear))
        wagon.tapped = bear.tapped = True
        self.assertTrue(self.spec_fits("tapped creature or Vehicle", wagon))
        self.assertTrue(self.spec_fits("tapped creature or Vehicle", bear))

    def test_subtype_union_with_head_type(self):
        elf, soldier = self.perm(ELF, self.a), self.perm(SOLDIER, self.a)
        kindred, wolf = self.perm(ELF_TRIBAL, self.a), self.perm(WOLF, self.a)
        fits = [p for p in (elf, soldier, kindred, wolf) if self.spec_fits("Elf or Soldier creature", p)]
        self.assertEqual(fits, [elf, soldier])

    def test_attacking_subtype_union(self):
        wolf, elf = self.perm(WOLF, self.a), self.perm(ELF, self.a)
        self.assertFalse(self.spec_fits("attacking Wolf or Werewolf", wolf))
        self.game.attackers = [wolf, elf]
        self.assertTrue(self.spec_fits("attacking Wolf or Werewolf", wolf))
        self.assertFalse(self.spec_fits("attacking Wolf or Werewolf", elf))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB()

    def test_newly_read_lines(self):
        from mtgsim.coverage import card_coverage
        for name in ("The Mighty Thor, Jane Foster", "Stall Out", "Fire Nation Engineer", "Gas Guzzler",
                     "Kari Zev's Expertise", "Puppet Crafting", "Tractor Beam", "Where We're Going...",
                     "The Measure of a Man"):
            with self.subTest(name=name):
                self.assertEqual(card_coverage(self.db.get(name)).status, "full")

    def test_union_lines_that_were_already_read_keep_reading(self):
        effects, bad = _parse_effects("Prevent the next 1 damage that would be dealt to target Cleric or Wizard "
                                      "creature this turn.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].data["selector"], {"subtypes_any": ["cleric", "wizard"], "types_all": ["creature"]})

    def test_stall_out_taps_and_stuns_an_opposing_vehicle(self):
        stall = self.db.get("Stall Out")
        wagon = self.perm(VEHICLE, self.b)
        land = self.perm(ISLAND, self.b)
        with self.game.targeting(stall):
            legal = self.game.legal_targets(self.a, stall.spell_effects[0])
        self.assertIn(wagon, legal)
        self.assertNotIn(land, legal)
        self.cast(stall, [wagon, None])
        self.assertTrue(wagon.tapped)
        self.assertEqual(wagon.counters.get("stun"), 3)

    def test_heuristic_ai_aims_stall_out_at_the_opponent(self):
        from tests.test_templates import MOUNTAIN
        stall = self.db.get("Stall Out")
        self.perm(BEAR, self.a)
        wagon = self.perm(VEHICLE, self.b)
        for _ in range(3):
            self.perm(MOUNTAIN, self.a)
        self.game.step = "main1"
        plan = self.a.ai.plan_spell(self.game, self.a, stall, precombat=True)
        self.assertIsNotNone(plan)
        self.assertIs(plan[1][0], wagon)

    def test_mighty_thor_blink_reads_the_distributed_union(self):
        thor = self.db.get("The Mighty Thor, Jane Foster")
        blink = next(e for t in thor.triggers for e in t.effects if e.kind == "blink")
        self.assertEqual(blink.data["selector"], {"traits": ["nontoken"], "types_any": ["artifact", "creature"]})
        token = self.perm(dataclasses.replace(VEHICLE, is_token=True), self.b)
        wagon, bear = self.perm(VEHICLE, self.b), self.perm(BEAR, self.b)
        with self.game.targeting(thor):
            legal = self.game.legal_targets(self.a, blink)
        self.assertIn(wagon, legal)
        self.assertIn(bear, legal)
        self.assertNotIn(token, legal)


if __name__ == "__main__":
    unittest.main()

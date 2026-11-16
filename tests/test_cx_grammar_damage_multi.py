"""Multi-recipient damage (#320): "it deals ... and ... to you" in a self ETB trigger, "target creature and N damage
to its controller", "each of up to six targets" and "N to any target, M to another target, and K to a third target"."""
import unittest

from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import StackItem

from tests.test_cx_grammar import BEAR, DB_FILE, FLIER, ISLAND, Base, card


class Parsing(unittest.TestCase):
    def test_its_controller_after_a_target_creature(self):
        effs = parse_sentence("~ deals 1 damage to target creature and 1 damage to its controller.")
        self.assertEqual([(e.kind, e.data.get("who")) for e in effs], [("damage", None), ("cx_damage", "controller")])

    def test_three_distinct_targets(self):
        effs = parse_sentence("~ deals 1 damage to any target, 2 damage to another target, and 3 damage to a third "
                              "target.")
        self.assertEqual([(e.kind, e.amount, e.target) for e in effs],
                         [("damage", 1, "any"), ("damage", 2, "any"), ("damage", 3, "any")])
        self.assertTrue(all(e.data.get("distinct") for e in effs))

    def test_up_to_six_targets(self):
        effs = parse_sentence("~ deals 6 damage to each of up to six targets.")
        self.assertEqual(len(effs), 6)
        self.assertTrue(all(e.data.get("distinct") and e.data.get("optional_target") for e in effs))

    def test_near_misses_stay_rejected(self):
        for s in ("~ deals 1 damage to target creature and 1 damage to its owner.",
                  "~ deals 1 damage to any target and 1 damage to its controller.",
                  "Enchanted creature deals 1 damage to target creature and 1 damage to its controller.",
                  "It deals 1 damage to target creature and 1 damage to its controller.",
                  "~ deals 1 damage to any target, 2 damage to another target, and X damage to a third target.",
                  "~ deals 1 damage to any target, 2 damage to another target, and 3 damage to a third target "
                  "until end of turn.",
                  "~ deals 6 damage to each of up to eleven targets."):
            self.assertIsNone(parse_sentence(s), s)

    def test_it_deals_only_rewritten_for_self_triggers(self):
        """"Whenever a creature enters, it deals ..." names the entering creature, not ~: still unsupported."""
        c = card("Test Rig", "{3}", "Artifact",
                 "Whenever another creature enters, it deals 1 damage to any target and 1 damage to you.")
        self.assertNotEqual(c.unsupported, [])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Char-Dog", "Forge Devil", "Daredevil's Billy Club", "Spicy Oatmeal Pizza", "Neonate's Rush",
                     "Cone of Flame", "Chandra, the Firebrand", "Rakdos Firewheeler", "Burning Sun's Avatar",
                     "Flametongue Kavu", "Dagger Caster", "Invasion of Ulgrotha // Grandmother Ravi Sengir"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


class Resolving(Base):
    def test_its_controller_is_the_target_creatures_controller(self):
        bear = self.perm(BEAR, self.b)
        c = self.spell("~ deals 2 damage to target creature and 1 damage to its controller.")
        self.cast(c, [bear, None])
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual((self.a.life, self.b.life), (20, 19))

    def test_three_targets_get_their_own_amounts(self):
        bear, flier = self.perm(BEAR, self.b), self.perm(FLIER, self.b)
        c = self.spell("~ deals 1 damage to any target, 2 damage to another target, and 3 damage to a third target.")
        self.cast(c, [flier, bear, self.b])
        self.assertNotIn(bear, self.b.battlefield)
        self.assertNotIn(flier, self.b.battlefield)
        self.assertEqual(self.b.life, 17)

    def test_self_etb_trigger_damages_target_and_you(self):
        dog = card("Test Dog", "{3}{R}", "Creature — Dog",
                   "When this creature enters, it deals 4 damage to any target and 2 damage to you.", 4, 4)
        self.assertEqual(dog.unsupported, [])
        src = self.perm(dog, self.a)
        trig = dog.triggers[0]
        self.game.stack.append(StackItem(self.a, list(trig.effects), [self.b, None], source=src, kind="trigger",
                                         name=dog.name))
        self.game.resolve_top()
        self.assertEqual((self.a.life, self.b.life), (18, 16))


    def test_any_other_target_in_a_self_etb_excludes_the_source(self):
        siege = card("Test Siege", "{4}{B}", "Creature — Horror",
                     "When this creature enters, it deals 3 damage to any other target and you gain 3 life.", 3, 3)
        self.assertEqual(siege.unsupported, [])
        src, bear = self.perm(siege, self.a), self.perm(BEAR, self.b)
        eff = siege.triggers[0].effects[0]
        with self.game.targeting(src):
            legal = self.game.legal_targets(self.a, eff)
        self.assertNotIn(src, legal)
        self.assertIn(bear, legal)


class DefaultAI(Base):
    def main_phase(self, c):
        self.perm(ISLAND, self.a)
        self.a.hand = [c]
        self.game.step = "main2"
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(c, self.a.hand, "the AI didn't cast it")

    def test_cone_of_flame_aims_at_the_opponent(self):
        mine = self.perm(BEAR, self.a)
        bear, flier = self.perm(BEAR, self.b), self.perm(FLIER, self.b)
        self.main_phase(card("Test Cone", "{U}", "Sorcery", "~ deals 1 damage to any target, 2 damage to another "
                             "target, and 3 damage to a third target."))
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(bear, self.b.battlefield)
        self.assertNotIn(flier, self.b.battlefield)
        self.assertEqual(self.a.life, 20)

    def test_neonates_rush_hits_their_creature_and_them(self):
        mine, theirs = self.perm(FLIER, self.a), self.perm(FLIER, self.b)
        self.main_phase(card("Test Rush", "{U}", "Instant",
                             "~ deals 1 damage to target creature and 1 damage to its controller."))
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)
        self.assertEqual((self.a.life, self.b.life), (20, 19))


if __name__ == "__main__":
    unittest.main()

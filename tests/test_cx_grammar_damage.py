"""Grammar damage verbs (mtgsim.cx_grammar_damage): "<source> deals N damage to <recipient>"."""
import unittest

from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import Permanent, StackItem

from tests.test_cx_grammar import BEAR, DB_FILE, FLIER, Base, card


class Parsing(unittest.TestCase):
    def kinds(self, s):
        effs = parse_sentence(s)
        return None if effs is None else [e.kind for e in effs]

    def test_recipients(self):
        self.assertEqual(self.kinds("~ deals 1 damage to target creature you control."), ["damage"])
        self.assertEqual(self.kinds("~ deals 2 damage to any target and 1 damage to any other target."),
                         ["damage", "damage"])
        self.assertEqual(self.kinds("~ deals 3 damage to target creature and 3 damage to that creature's controller."),
                         ["damage", "cx_damage"])
        self.assertEqual(self.kinds("It deals 1 damage to each creature without flying."), ["cx_group"])
        self.assertEqual(self.kinds("~ deals 2 damage to it."), ["damage"])

    def test_targets_and_sides(self):
        effs = parse_sentence("~ deals 2 damage to any target and 1 damage to any other target.")
        self.assertEqual([e.target for e in effs], ["any", "any"])
        self.assertTrue(all(e.data.get("distinct") for e in effs))
        self.assertFalse(any(e.data.get("other") for e in effs))
        self.assertEqual(parse_sentence("~ deals 1 damage to target creature you control.")[0].target, "permanent")

    def test_rejections(self):
        for s in ("~ deals 4 damage divided as you choose among any number of targets.",
                  "~ deals that much damage to you.",
                  "~ deals damage equal to its power to target creature.",
                  "~ deals 2 damage to each of two targets.",
                  "~ deals 2 damage to you unless you pay {1}.",
                  "It deals 2 damage to target creature with flying.",           # "it" as another source, targeted
                  "~ deals X damage to each creature.",                          # X inside a group
                  "~ deals 2 damage to target creature and 1 damage to any other target.",
                  "~ deals 2 damage to any target until end of turn.",
                  "Target creature deals 2 damage to any target."):              # bite: a later round
            self.assertIsNone(parse_sentence(s), s)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Arc Trail", "Chandra's Outrage", "First Volley", "Rile", "Spiteful Bully",
                     "Bloodfire Dwarf", "Shard Phoenix", "Subterranean Shambler", "Caltrops", "Aether Flash"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


class Resolving(Base):
    def test_two_targets_distinct(self):
        bear, opp = self.perm(BEAR, self.b), self.b
        c = self.spell("~ deals 2 damage to any target and 1 damage to any other target.", "Sorcery")
        self.cast(c, [bear, opp])
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(opp.life, 19)

    def test_controller_of_the_target_takes_damage(self):
        bear = self.perm(BEAR, self.b)
        c = self.spell("~ deals 3 damage to target creature and 2 damage to that creature's controller.")
        self.cast(c, [bear, None])
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual((self.a.life, self.b.life), (20, 18))

    def test_group_spares_fliers(self):
        bear, flier, mine = self.perm(BEAR, self.b), self.perm(FLIER, self.b), self.perm(BEAR, self.a)
        self.cast(self.spell("~ deals 2 damage to each creature without flying."))
        self.assertNotIn(bear, self.b.battlefield)
        self.assertNotIn(mine, self.a.battlefield)
        self.assertIn(flier, self.b.battlefield)

    def test_it_in_a_trigger_is_the_triggering_permanent(self):
        """"~ deals 1 damage to it" hits the attacker; "it deals" from that attacker comes from it."""
        caltrops = card("Test Caltrops", "{3}", "Artifact", "Whenever a creature attacks, ~ deals 1 damage to it.")
        self.assertEqual(caltrops.unsupported, [])
        src = self.perm(caltrops, self.a)
        attacker = self.perm(card("Test Elf", "{G}", "Creature — Elf", "", 1, 1), self.b)
        trig = caltrops.triggers[0]
        self.game.stack.append(StackItem(self.a, list(trig.effects), [None] * len(trig.effects), source=src,
                                         kind="trigger", context=attacker, name="Caltrops"))
        self.game.resolve_top()
        self.assertNotIn(attacker, self.b.battlefield)

    def test_player_recipient_is_real_damage(self):
        """Damage to "that creature's controller" is damage (prevention applies), not life loss."""
        bear = self.perm(BEAR, self.b)
        self.b.prevent_next = 2
        c = self.spell("~ deals 1 damage to target creature and 2 damage to that creature's controller.")
        self.cast(c, [bear, None])
        self.assertEqual(self.b.life, 20)
        self.assertIsInstance(bear, Permanent)


if __name__ == "__main__":
    unittest.main()

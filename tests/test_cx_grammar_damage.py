"""Grammar damage verbs (mtgsim.cx_grammar_damage): "<source> deals N damage to <recipient>"."""
import unittest

from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import Permanent, StackItem

from tests.test_cx_grammar import BEAR, DB_FILE, FLIER, GOBLIN, ISLAND, Base, card


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
        self.assertEqual(self.kinds("~ deals 3 damage to that land's controller."), ["cx_damage"])
        self.assertEqual(self.kinds("~ deals 1 damage to each creature and each player."), ["cx_group", "cx_damage"])
        self.assertEqual([(e.kind, e.target) for e in parse_sentence(
            "~ deals 2 damage to any target and 2 damage to itself.")], [("damage", "any"), ("damage", "self")])

    def test_targets_and_sides(self):
        effs = parse_sentence("~ deals 2 damage to any target and 1 damage to any other target.")
        self.assertEqual([e.target for e in effs], ["any", "any"])
        self.assertTrue(all(e.data.get("distinct") for e in effs))
        self.assertFalse(any(e.data.get("other") for e in effs))
        self.assertEqual(parse_sentence("~ deals 1 damage to target creature you control.")[0].target, "permanent")

    def test_rejections(self):
        for s in ("~ deals 4 damage divided as you choose among any number of targets.",
                  "~ deals that much damage to you.",
                  "~ deals 2 damage to each of two targets.",
                  "~ deals 2 damage to you unless you pay {1}.",
                  "It deals 2 damage to target creature with flying.",           # "it" as another source, targeted
                  "~ deals X damage to each creature.",                          # X inside a group
                  "~ deals 2 damage to target creature and 1 damage to any other target.",
                  "~ deals 2 damage to any target until end of turn.",
                  "Enchanted creature deals 1 damage to its controller.",       # "its" is the source here
                  "It deals 2 damage to each other creature.",                  # "other" than ~, not than it
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

    def test_grammar_group_resolves(self):
        """A group only the grammar reads (cx_group around cx_damage), resolved through the stack: Seismic Wave."""
        goblin, bear, mine = self.perm(GOBLIN, self.b), self.perm(BEAR, self.b), self.perm(GOBLIN, self.a)
        c = self.spell("~ deals 2 damage to any target and 1 damage to each nonartifact creature target opponent "
                       "controls.")
        self.assertEqual([e.kind for e in c.spell_effects], ["damage", "cx_group"])
        from mtgsim.engine.state import TARGETED
        self.cast(c, [self.b if e.target in TARGETED else None for e in c.spell_effects])   # "target opponent": b
        self.assertNotIn(goblin, self.b.battlefield)        # 1/1: dies
        self.assertEqual(bear.damage, 1)
        self.assertIn(mine, self.a.battlefield)
        self.assertEqual(self.b.life, 18)

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

    def test_each_creature_and_each_player(self):
        bear, mine = self.perm(BEAR, self.b), self.perm(BEAR, self.a)
        self.cast(self.spell("~ deals 2 damage to each creature and each player.", "Sorcery"))
        self.assertNotIn(bear, self.b.battlefield)
        self.assertNotIn(mine, self.a.battlefield)
        self.assertEqual((self.a.life, self.b.life), (18, 18))

    def test_player_recipient_is_real_damage(self):
        """Damage to "that creature's controller" is damage (prevention applies), not life loss."""
        bear = self.perm(BEAR, self.b)
        self.b.prevent_next = 2
        c = self.spell("~ deals 1 damage to target creature and 2 damage to that creature's controller.")
        self.cast(c, [bear, None])
        self.assertEqual(self.b.life, 20)
        self.assertIsInstance(bear, Permanent)


class DefaultAI(Base):
    """The default AI casts the new shapes and aims them at the opponent."""
    def main_phase(self, text, types="Sorcery"):
        spell = card("Test Spell", "{U}", types, text)
        self.assertEqual(spell.unsupported, [], text)
        self.perm(ISLAND, self.a)
        self.a.hand = [spell]
        self.game.step = "main2"            # after combat: the AI holds face burn before its attack
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand, "the AI didn't cast it")
        return spell

    def test_damage_to_each_opponent(self):
        self.main_phase("~ deals 2 damage to each opponent.")
        self.assertEqual((self.a.life, self.b.life), (20, 18))

    def test_creature_and_its_controller(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        self.main_phase("~ deals 2 damage to target creature and 2 damage to that creature's controller.")
        self.assertNotIn(theirs, self.b.battlefield)
        self.assertIn(mine, self.a.battlefield)
        self.assertEqual((self.a.life, self.b.life), (20, 18))

    def test_group_sweep_at_their_side(self):
        theirs = [self.perm(BEAR, self.b) for _ in range(3)]
        flier = self.perm(FLIER, self.a)
        self.main_phase("~ deals 2 damage to each creature without flying.")
        self.assertFalse(any(x in self.b.battlefield for x in theirs))
        self.assertIn(flier, self.a.battlefield)

    def test_two_distinct_targets(self):
        """Arc Trail on a 2/2 and a 1/1: one each (the default AI holds 1 damage to the face as too little)."""
        bear, flier = self.perm(BEAR, self.b), self.perm(FLIER, self.b)
        self.main_phase("~ deals 2 damage to any target and 1 damage to any other target.")
        self.assertNotIn(bear, self.b.battlefield)
        self.assertNotIn(flier, self.b.battlefield)


if __name__ == "__main__":
    unittest.main()

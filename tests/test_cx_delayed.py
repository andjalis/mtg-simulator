"""Delayed end-step actions (cx_delayed) and the suspect riders (cx_suspect)."""
import random
import unittest

from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

PYRIC = card("Test Salamander", "{1}{R}", "Creature — Salamander",
             "{R}: ~ gets +1/+0 until end of turn. Sacrifice ~ at the beginning of the next end step.", 1, 1)
CANNON = card("Test Cannon", "{4}", "Artifact",
              "{T}: Target creature you control gets +1/+0 and gains flying until end of turn. "
              "Destroy that creature at the beginning of the next end step.")
SNEAK = card("Test Sneak", "{1}{R}{R}", "Enchantment",
             "{R}: You may put a creature card from your hand onto the battlefield. That creature gains haste. "
             "Sacrifice the creature at the beginning of the next end step.")
STAFF = card("Test Staff", "{1}", "Artifact",
             "{2}, Sacrifice ~: Exile target creature. Return the exiled card to the battlefield under its owner's "
             "control at the beginning of the next end step.")
MASK = card("Test Mask", "{3}", "Artifact",
            "{3}, {T}: Target creature you control gets +2/+2 until end of turn. Return it to its owner's hand at the "
            "beginning of the next end step.")
IDEAS = card("Test Ideas", "{U}", "Sorcery", "Draw three cards. Discard three cards at the beginning of the next end step.")
OFFENDER = card("Test Offender", "{2}{B}", "Creature — Goblin",
                "{2}{B}: If ~ is suspected, put a +1/+1 counter on it. Otherwise, suspect it.", 2, 2)
LAMMASU = card("Test Lammasu", "{4}{W}", "Creature — Lammasu",
               "When ~ enters, all suspected creatures are no longer suspected.", 3, 3)


class Base(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def run_item(self, effects, targets=(), source=None):
        targets = list(targets) + [None] * (len(effects) - len(targets))
        self.g.stack.append(StackItem(self.a, list(effects), targets, source=source, name="test"))
        self.g.resolve_top()

    def end_step(self):
        self.g.begin_end_step(self.a)
        self.g.settle()


class Delayed(Base):
    def test_parse(self):
        for c in (PYRIC, CANNON, SNEAK, STAFF, MASK, IDEAS, OFFENDER, LAMMASU):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertIn("cx_delay", [e.kind for e in PYRIC.activated[0].effects])
        self.assertIn("cx_fresh_grant", [e.kind for e in SNEAK.activated[0].effects])

    def test_sacrifice_self(self):
        lizard = self.g.enter_battlefield(self.a, PYRIC)
        self.run_item(PYRIC.activated[0].effects, source=lizard)
        self.assertIn(lizard, self.a.battlefield)
        self.end_step()
        self.assertNotIn(lizard, self.a.battlefield)

    def test_destroy_target(self):
        cannon = self.g.enter_battlefield(self.a, CANNON)
        bear = self.g.enter_battlefield(self.a, BEAR)
        self.run_item(CANNON.activated[0].effects, [bear], source=cannon)
        self.assertTrue(bear.has("flying"))
        self.end_step()
        self.assertNotIn(bear, self.a.battlefield)

    def test_put_from_hand_gains_haste_then_sacrificed(self):
        sneak = self.g.enter_battlefield(self.a, SNEAK)
        self.a.hand.append(BEAR)
        self.run_item(SNEAK.activated[0].effects, source=sneak)
        bear = next(x for x in self.a.battlefield if x.card.name == BEAR.name)
        self.assertTrue(bear.has("haste"))
        self.end_step()
        self.assertNotIn(bear, self.a.battlefield)
        self.assertIn(sneak, self.a.battlefield)

    def test_exile_and_return(self):
        staff = self.g.enter_battlefield(self.a, STAFF)
        bear = self.g.enter_battlefield(self.b, BEAR)
        self.run_item(STAFF.activated[0].effects, [bear], source=staff)
        self.assertEqual([x for x in self.b.battlefield if x.card.name == BEAR.name], [])
        self.end_step()
        back = [x for x in self.b.battlefield if x.card.name == BEAR.name]
        self.assertEqual(len(back), 1)
        self.assertNotIn(back[0].front, self.b.exile)

    def test_return_to_hand(self):
        mask = self.g.enter_battlefield(self.a, MASK)
        bear = self.g.enter_battlefield(self.a, BEAR)
        self.run_item(MASK.activated[0].effects, [bear], source=mask)
        self.end_step()
        self.assertNotIn(bear, self.a.battlefield)
        self.assertIn(BEAR.name, [c.name for c in self.a.hand])

    def test_whole_sentence_delayed(self):
        self.run_item(IDEAS.spell_effects)
        self.assertEqual(len(self.a.hand), 3)
        self.end_step()
        self.assertEqual(len(self.a.hand), 0)

    def test_nothing_left_to_act_on(self):
        lizard = self.g.enter_battlefield(self.a, PYRIC)
        self.run_item(PYRIC.activated[0].effects, source=lizard)
        self.g.leave_battlefield(lizard, "hand")
        self.end_step()
        self.assertIn(PYRIC.name, [c.name for c in self.a.hand])


class Suspect(Base):
    def test_if_suspected_otherwise(self):
        goblin = self.g.enter_battlefield(self.a, OFFENDER)
        effects = OFFENDER.activated[0].effects
        self.run_item(effects, source=goblin)
        self.assertTrue(goblin.has("suspected"))
        self.assertEqual(goblin.counters.get("+1/+1", 0), 0)
        self.run_item(effects, source=goblin)
        self.assertEqual(goblin.counters.get("+1/+1", 0), 1)

    def test_no_longer_suspected(self):
        goblin = self.g.enter_battlefield(self.a, OFFENDER)
        self.run_item(OFFENDER.activated[0].effects, source=goblin)
        self.assertTrue(goblin.has("suspected"))
        self.g.enter_battlefield(self.a, LAMMASU)
        self.g.settle()
        self.assertFalse(goblin.has("suspected"))
        self.assertFalse(goblin.has("cant_block_now"))


if __name__ == "__main__":
    unittest.main()

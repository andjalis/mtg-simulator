"""#554: "another / other target ..." after an earlier target of the same spell or ability can't take the object
the earlier target took (rule 115.3), not only "not the source" (Withdraw). "target ... other than ~" still names
only the source."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card

WITHDRAW = card("Test Withdraw", "{U}{U}", "Instant", "Return target creature to its owner's hand. Then return "
                "another target creature to its owner's hand unless its controller pays {1}.")
WINGS = card("Test Wings", "{U}", "Instant", "Target creature gets +1/+1 until end of turn. Another target creature "
             "gains flying until end of turn.")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


class AnotherTarget(unittest.TestCase):
    def setUp(self):
        self.g, self.a, self.b = game()
        self.x = self.g.enter_battlefield(self.b, card("Ogre", "{3}", "Creature — Ogre", "", 3, 3))
        self.y = self.g.enter_battlefield(self.b, card("Elf", "{1}", "Creature — Elf", "", 1, 1))

    def test_same_object_twice_refused(self):
        for spell in (WITHDRAW, WINGS):
            self.assertEqual(spell.unsupported, [])
            effs = spell.spell_effects
            twice = [self.x if e.target != "none" else None for e in effs]
            self.assertFalse(self.g.valid_action_targets(self.a, effs, twice, spell), spell.name)
            seq = iter([self.x, self.y])
            two = [next(seq) if e.target != "none" else None for e in effs]
            self.assertTrue(self.g.valid_action_targets(self.a, effs, two, spell), spell.name)

    def test_second_targets_exclude_the_first_while_choosing(self):
        effs = WITHDRAW.spell_effects
        targets = self.g.auto_targets(self.a, effs, WITHDRAW)
        chosen = [t for t in targets if t is not None]
        self.assertEqual(len(chosen), 2)
        self.assertIsNot(chosen[0], chosen[1])

    def test_withdraw_resolves_on_two_creatures(self):
        for _ in range(2):
            self.g.enter_battlefield(self.a, ISLAND)
        self.a.hand = [WITHDRAW]
        effs = WITHDRAW.spell_effects
        self.assertFalse(self.g.cast(self.a, WITHDRAW, [self.x if e.target != "none" else None for e in effs]))
        seq = iter([self.x, self.y])
        self.assertTrue(self.g.cast(self.a, WITHDRAW, [next(seq) if e.target != "none" else None for e in effs]))
        self.g.settle()
        self.assertNotIn(self.x, self.b.battlefield)

    def test_other_than_source_keeps_earlier_targets_legal(self):
        effects, bad = _parse_effects("Target creature other than ~ gains flying until end of turn.")
        self.assertEqual(bad, [])
        eff = effects[0]
        self.assertTrue(eff.data.get("other_than_source"))
        src = self.g.enter_battlefield(self.a, card("Src", "{1}", "Creature — Bird", "", 1, 1))
        first = _parse_effects("Target creature gets +1/+1 until end of turn.")[0][0]
        item = StackItem(self.a, [first, eff], [self.x, None], source=src, kind="ability")
        with self.g.targeting(item):
            legal = self.g.legal_targets(self.a, eff)
        self.assertNotIn(src, legal)
        self.assertIn(self.x, legal)

    def test_no_earlier_target_only_the_source(self):
        effects, _ = _parse_effects("Return another target creature to its owner's hand.")
        src = self.g.enter_battlefield(self.a, card("Src", "{1}", "Creature — Bird", "", 1, 1))
        with self.g.targeting(StackItem(self.a, effects, [None], source=src, kind="trigger")):
            legal = self.g.legal_targets(self.a, effects[0])
        self.assertEqual(set(legal), {self.x, self.y})

    @unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
    def test_withdraw_card(self):
        from mtgsim.carddb import CardDB
        c = CardDB(offline=True).get("Withdraw")
        self.assertEqual(c.unsupported, [])
        effs = c.spell_effects
        twice = [self.x if e.target != "none" else None for e in effs]
        self.assertFalse(self.g.valid_action_targets(self.a, effs, twice, c))


if __name__ == "__main__":
    unittest.main()

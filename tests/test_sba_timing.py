"""#682: state-based actions aren't checked between the effects of one resolving spell or ability (CR 704.3)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def resolve(self, c, x=0, targets=None):
        effs = list(c.spell_effects)
        item = StackItem(self.a, effs, targets or [None] * len(effs), card=c, name=c.name)
        item.x = x
        self.game.stack.append(item)
        self.game.resolve_top()

    def tokens(self, p):
        return [x for x in p.battlefield if x.card.is_token]


class ZeroZeroTokens(Base):
    def test_token_then_counters_on_it(self):
        self.resolve(card("Test Fractal", "{X}{G}{U}", "Sorcery", "Create a 0/0 green and blue Fractal creature "
                          "token. Put three +1/+1 counters on it."))
        tokens = self.tokens(self.a)
        self.assertEqual([t.counters.get("+1/+1") for t in tokens], [3])

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_wild_hypothesis(self):
        from mtgsim.carddb import CardDB
        self.resolve(CardDB().get("Wild Hypothesis"), x=3)
        tokens = self.tokens(self.a)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].counters.get("+1/+1"), 3)

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_body_of_research(self):
        from mtgsim.carddb import CardDB
        self.resolve(CardDB().get("Body of Research"))
        tokens = self.tokens(self.a)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].counters.get("+1/+1"), len(self.a.library))

    def test_intrude_shape_counted_counters_on_the_token(self):
        """Intrude on the Mind's shape: "Create a 0/0 ... token with flying, then put a +1/+1 counter on it for each
        <counted thing>"."""
        self.a.hand = [ISLAND, ISLAND]
        self.resolve(card("Test Intrude", "{2}{U}", "Sorcery", "Create a 0/0 colorless Thopter artifact creature "
                          "token with flying, then put a +1/+1 counter on it for each card in your hand."))
        tokens = self.tokens(self.a)
        self.assertEqual([t.counters.get("+1/+1") for t in tokens], [2])

    def test_it_after_a_token_is_only_the_next_effect(self):
        """"Destroy target creature. Its controller creates a 1/1 token.": the token doesn't become a later "it"."""
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.resolve(card("Test Swap", "{1}", "Instant", "Destroy target creature. Its controller creates a 1/1 "
                          "white Soldier creature token."), targets=[bear, None])
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(len(self.tokens(self.b)), 1)

    def test_a_zero_token_without_counters_still_dies_after_resolution(self):
        self.resolve(card("Test Zero", "{1}", "Sorcery", "Create a 0/0 green Fractal creature token."))
        self.assertEqual(self.tokens(self.a), [])

    def test_lethal_damage_is_checked_once_the_spell_is_done(self):
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.resolve(card("Test Shock", "{R}", "Instant", "Test Shock deals 2 damage to target creature."), targets=[bear])
        self.assertNotIn(bear, self.b.battlefield)

    def test_damage_then_pump_in_one_spell_saves_it(self):
        """Damage and a toughness boost from one resolution: SBAs see the creature only after both."""
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.resolve(card("Test Odd", "{R}", "Instant", "Test Odd deals 2 damage to target creature. It gets +0/+2 "
                          "until end of turn."), targets=[bear, None])
        self.assertIn(bear, self.a.battlefield)


if __name__ == "__main__":
    unittest.main()

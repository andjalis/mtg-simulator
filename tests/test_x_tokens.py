"""X Mutagen tokens, artifact-token ability discount, Empower X."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, card
from tests.test_empower_discover import Base

OOZE = card("Test Ooze", "{X}{G}{G}", "Legendary Creature — Ooze",
            "When ~ enters, create X Mutagen tokens.\n"
            "Activated abilities of artifact tokens you control cost {1} less to activate.", 1, 1)
ENFORCER = card("Test Enforcer", "{1}{U}", "Creature — Robot",
                "When ~ enters, empower Jace X, where X is the number of creatures you control.", 2, 2)


class XTokens(Base):
    def test_templates(self):
        for c in (OOZE, ENFORCER):
            self.assertEqual(c.unsupported, [], c.name)

    def test_x_mutagen_tokens_and_discount(self):
        self.a.hand.append(OOZE)
        perm = self.game.enter_battlefield(self.a, OOZE, x=3)
        self.game.settle()
        self.assertEqual(sum(x.card.name == "Mutagen" for x in self.a.battlefield), 3)
        tok = next(x for x in self.a.battlefield if x.card.is_token and x.card.is_artifact)
        act = tok.card.activated[0]
        self.assertEqual(self.game.ability_cost(self.a, tok, act).get("generic", 0), 0)
        self.a.battlefield.remove(perm)
        self.assertEqual(self.game.ability_cost(self.a, tok, act).get("generic", 0), 1)

    def test_empower_counts_creatures(self):
        self.perm(BEAR)
        self.game.enter_battlefield(self.a, ENFORCER)
        self.game.settle()
        jace = next(x for x in self.a.battlefield if "Jace" in x.card.subtypes)
        self.assertEqual(jace.loyalty, 2)


SHOCK = card("Test Scorch", "{1}{R}", "Sorcery",
             "~ deals 3 damage to target creature. If that creature would die this turn, exile it instead.")


class ExileInstead(Base):
    def test_template(self):
        self.assertEqual(SHOCK.unsupported, [])

    def test_damaged_creature_is_exiled(self):
        from tests.test_templates import MOUNTAIN
        for _ in range(2):
            self.perm(MOUNTAIN)
        bear = self.perm(BEAR, self.b)
        self.a.hand.append(SHOCK)
        self.assertTrue(self.game.cast(self.a, SHOCK, [bear, bear]))
        self.game.settle()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(self.b.graveyard, [])
        self.assertIn(BEAR, self.b.exile)


if __name__ == "__main__":
    unittest.main()

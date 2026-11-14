"""'Target creature an opponent controls / you don't control gets -N/-N until end of turn' keeps the restriction
(Invasion of Innistrad could target your own creature)."""
import random
import unittest

from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import card


class DebuffOpponentFilter(unittest.TestCase):
    def test_restriction_kept(self):
        a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
        g = Game(a, b, random.Random(0), log=True)
        mine = g.enter_battlefield(a, card("Mine", "{1}", "Creature — Human", "", 2, 2))
        foe = g.enter_battlefield(b, card("Foe", "{1}", "Creature — Ogre", "", 2, 2))
        for text in ("Target creature an opponent controls gets -13/-13 until end of turn.",
                     "Target creature you don't control gets -2/-2 until end of turn."):
            effects, bad = _parse_effects(text)
            self.assertEqual(bad, [])
            legal = g.legal_targets(a, effects[0])
            self.assertEqual(legal, [foe], text)
        effects, _ = _parse_effects("Target creature gets -2/-2 until end of turn.")
        self.assertEqual(set(g.legal_targets(a, effects[0])), {mine, foe})


if __name__ == "__main__":
    unittest.main()

"""#417: "return target creature to its owner's hand" targets creatures only (it was read as any nonland permanent)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import ISLAND, card

UNSUMMON = card("Test Unsummon", "{U}", "Instant", "Return target creature to its owner's hand.")
THEIRS = card("Test Jilt", "{U}", "Sorcery", "Return target creature an opponent controls to its owner's hand.")
UP_TO = card("Test Maybe", "{U}", "Sorcery", "Return up to one target creature to its owner's hand.")
NONLAND = card("Test Helix", "{U}", "Instant", "Return target nonland permanent to its owner's hand.")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    for _ in range(2):
        g.enter_battlefield(a, ISLAND).sick = False
    rock = g.enter_battlefield(b, card("Rock", "{2}", "Artifact", "{T}: Add {C}."))
    ogre = g.enter_battlefield(b, card("Ogre", "{3}", "Creature — Ogre", "", 3, 3))
    mine = g.enter_battlefield(a, card("Mine", "{1}", "Creature — Human", "", 1, 1))
    g.settle()
    return g, a, b, rock, ogre, mine


class CreatureBounce(unittest.TestCase):
    def test_creature_wordings_target_creatures_only(self):
        g, a, b, rock, ogre, mine = game()
        for spell in (UNSUMMON, UP_TO):
            legal = g.legal_targets(a, spell.spell_effects[0])
            self.assertNotIn(rock, legal, spell.name)
            self.assertIn(ogre, legal)
            self.assertIn(mine, legal)
        legal = g.legal_targets(a, THEIRS.spell_effects[0])
        self.assertEqual(legal, [ogre])

    def test_nonland_permanent_still_hits_artifacts(self):
        g, a, b, rock, ogre, mine = game()
        self.assertIn(rock, g.legal_targets(a, NONLAND.spell_effects[0]))

    def test_ai_bounces_their_creature(self):
        g, a, b, rock, ogre, mine = game()
        a.hand.append(THEIRS)
        g.main_phase(a)
        g.settle()
        self.assertNotIn(ogre, b.battlefield)
        self.assertIn(rock, b.battlefield)


if __name__ == "__main__":
    unittest.main()

"""cx_replace.py: conditional entry counters, "would die, exile it instead", draw replacements, two-player
"choose an opponent", and copy events for "cast or copy" triggers (cx_events)."""
import random
import unittest

from mtgsim import copies
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, SHOCK, card

MORBID = card("Test Morbid", "{2}{G}", "Creature — Wolf",
              "Morbid — ~ enters with two +1/+1 counters on it if a creature died this turn.", 2, 2)
WARDEN = card("Test Warden", "{2}{W}", "Enchantment", "If a creature an opponent controls would die, exile it instead.")
PHOENIX = card("Test Shade", "{1}{B}", "Creature — Shade", "If ~ would die, exile it instead.", 2, 2)
SAGE = card("Test Sage", "{3}{U}", "Enchantment", "If you would draw a card except the first one you draw in each of "
                                                  "your draw steps, draw two cards instead.")
VISE = card("Test Vise", "{1}", "Artifact", "As ~ enters, choose an opponent.\nAt the beginning of the chosen player's "
                                            "upkeep, ~ deals 1 damage to that player.")
EMERITUS = card("Test Emeritus", "{2}{U}{U}", "Creature — Human Wizard",
                "Whenever you cast or copy an instant or sorcery spell, you gain 1 life.", 2, 2)


class Replace(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        self.game.settle()
        return perm

    def test_parse(self):
        for c in (MORBID, WARDEN, PHOENIX, SAGE, VISE, EMERITUS):
            self.assertEqual(c.unsupported, [], c.name)

    def test_morbid_counters(self):
        self.assertEqual(self.put(self.a, MORBID).counters.get("+1/+1", 0), 0)
        self.game.dies(self.put(self.b, BEAR))
        self.assertEqual(self.put(self.a, MORBID).counters.get("+1/+1", 0), 2)

    def test_exile_instead_of_dying(self):
        self.put(self.a, WARDEN)
        theirs, mine = self.put(self.b, BEAR), self.put(self.a, BEAR)
        self.game.destroy(theirs)
        self.game.destroy(mine)
        self.game.settle()
        self.assertEqual((len(self.b.graveyard), len(self.b.exile)), (0, 1))
        self.assertEqual(len(self.a.graveyard), 1)
        shade = self.put(self.a, PHOENIX)
        self.game.destroy(shade)
        self.assertEqual(len(self.a.exile), 1)

    def test_draw_two_instead(self):
        self.put(self.a, SAGE)
        self.game.draw(self.a)
        self.assertEqual(len(self.a.hand), 2)

    def test_chosen_player_is_the_opponent(self):
        self.put(self.a, VISE)
        self.game.fire(self.b, "upkeep")
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (20, 19))

    def test_cast_or_copy(self):
        self.put(self.a, EMERITUS)
        self.game.enter_battlefield(self.a, MOUNTAIN).tapped = False
        self.a.hand = [SHOCK]
        self.assertTrue(self.game.cast(self.a, SHOCK, [self.b]))
        self.game.settle()
        self.assertEqual(self.a.life, 21)
        spell = StackItem(self.a, list(SHOCK.spell_effects), [self.b], card=SHOCK)
        self.game.stack.append(spell)
        copies.copy_spell(self.game, self.a, spell)
        self.game.settle()
        self.assertEqual(self.a.life, 22)


if __name__ == "__main__":
    unittest.main()

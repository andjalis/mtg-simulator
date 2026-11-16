"""#634 DICE: the roll-advantage replacement, four-sided dice, and "Choose target creature, then roll a d20" with a
result table (one test per band)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


class Parse(unittest.TestCase):
    def test_four_sided_die(self):
        effects, bad = _parse_effects("Roll a four-sided die. If the result is 1, return ~ from your graveyard to the "
                                      "battlefield.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].data["sides"], 4)

    def test_advantage_static(self):
        for name in ("Barbarian Class", "Pixie Guide", "Wyll, Blade of Frontiers"):
            self.assertEqual(db(name).advanced_rules.get("dice_advantage"), 1, name)
            self.assertTrue(db(name).fully_supported, name)

    def test_refusals(self):
        # the roller chooses which result to ignore (not always the lowest): left unread
        self.assertFalse(db("Krark's Other Thumb").fully_supported)
        # a plain "Choose target creature." belongs to other templates, not to a die roll
        effects, _ = _parse_effects("Choose target creature. Mill four cards.")
        self.assertFalse(any(e.kind == "die_roll" for e in effects))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Game_(unittest.TestCase):
    def new(self, seed):
        a = Player("a", [], HeuristicAI())
        b = Player("b", [], HeuristicAI())
        game = Game(a, b, random.Random(seed), log=True)
        game.turn, game.step = 3, "main1"
        a.library = b.library = [ISLAND] * 20
        return game, a, b

    def pit_trap(self, seed):
        game, a, b = self.new(seed)
        trap = game.enter_battlefield(a, db("Spiked Pit Trap"))
        wurm = game.enter_battlefield(b, db("Craw Wurm"))
        mine = game.enter_battlefield(a, BEAR)
        for _ in range(5):
            game.enter_battlefield(a, ISLAND)
        self.assertTrue(game.activate_ability(a, trap, 0))
        game.settle()
        roll = int(next(e for e in game.events if "rolls 1 d20" in e).split("[")[1].rstrip("]"))
        treasures = [x for x in a.battlefield if "Treasure" in x.card.subtypes]
        self.assertNotIn(wurm, b.battlefield)        # 5 damage to their Wurm, the AI's choice
        self.assertEqual(mine.damage, 0)
        return roll, len(treasures)

    def test_spiked_pit_trap_low_band(self):
        outcomes = [self.pit_trap(seed) for seed in range(30)]
        low = [t for r, t in outcomes if r <= 9]
        self.assertTrue(low)
        self.assertEqual(set(low), {0})              # 1—9: damage only

    def test_spiked_pit_trap_high_band(self):
        outcomes = [self.pit_trap(seed) for seed in range(30)]
        high = [t for r, t in outcomes if r >= 10]
        self.assertTrue(high)
        self.assertEqual(set(high), {1})             # 10—20: damage and a Treasure

    def test_advantage_rolls_extra_dice_and_drops_the_lowest(self):
        game, a, b = self.new(3)
        game.enter_battlefield(a, db("Pixie Guide"))
        game.enter_battlefield(a, db("Wyll, Blade of Frontiers"))
        from mtgsim.dice_more import faces
        kept = faces(game, a, 20, 1)
        line = next(e for e in game.events if "ignores the lowest 2" in e)
        rolled = [int(x) for x in line.split("[")[1].split("]")[0].split(", ")]
        self.assertEqual(len(rolled), 3)
        self.assertEqual(kept, [max(rolled)])
        again, a2, _ = self.new(3)
        again.enter_battlefield(a2, db("Pixie Guide"))
        again.enter_battlefield(a2, db("Wyll, Blade of Frontiers"))
        self.assertEqual(faces(again, a2, 20, 1), kept)      # seeded: the same rolls again


if __name__ == "__main__":
    unittest.main()

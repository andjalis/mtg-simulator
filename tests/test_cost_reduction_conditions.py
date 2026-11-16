"""#341 slice: self cost reductions whose conditions were missing from cx_condlib: night, an opponent's spells /
draws this turn, no <kind> cards in hand, cards total in all graveyards, a creature attacking you, total
toughness, half the starting life, "a Human creature and a non-Human creature", two creatures sharing a type."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cx_condlib import parse
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE


def total(cost):
    return sum(v for k, v in cost.items() if k != "X")


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class ReductionConditions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [self.db.get("Island")] * 5

    def cost(self, name):
        return total(self.g.cost_of(self.a, self.db.get(name)))

    def put(self, name, who=None):
        return self.g.enter_battlefield(who or self.a, self.db.get(name))

    def test_parse(self):
        for name in ("Moonrager's Slash", "Ertai's Scorn", "Even the Score", "Forceful Cultivator", "Avatar of Woe",
                     "Red Alert!", "Orysa, Tide Choreographer", "Game Over", "Of One Mind", "Synchronized Eviction"):
            self.assertEqual(self.db.get(name).unsupported, [], name)
        for text in ("you control a Human creature and a non-Elf creature", "there are no cards in your library",
                     "an opponent cast two spells this turn"):
            self.assertEqual(parse(text), "", text)

    def test_night(self):
        base = self.cost("Moonrager's Slash")
        self.g.day_night = "night"
        self.assertEqual(self.cost("Moonrager's Slash"), base - 2)

    def test_opponent_spells_and_draws(self):
        base_scorn, base_score = self.cost("Ertai's Scorn"), self.cost("Even the Score")
        self.g.spells_cast = {"turn": self.g.turn, "b": 2}
        self.assertEqual(self.cost("Ertai's Scorn"), base_scorn - 1)
        self.b.drawn_turn = (self.g.turn, 3)
        self.assertEqual(self.cost("Even the Score"), base_score)
        self.b.drawn_turn = (self.g.turn, 4)
        self.assertEqual(self.cost("Even the Score"), base_score - 3)
        self.b.drawn_turn = (self.g.turn - 1, 9)                       # last turn's draws don't count
        self.assertEqual(self.cost("Even the Score"), base_score)

    def test_no_lands_in_hand(self):
        self.a.hand = [self.db.get("Forest")]
        base = self.cost("Forceful Cultivator")
        self.a.hand = [self.db.get("Grizzly Bears")]
        self.assertEqual(self.cost("Forceful Cultivator"), base - 2)

    def test_all_graveyards(self):
        base = self.cost("Avatar of Woe")
        self.a.graveyard = [self.db.get("Grizzly Bears")] * 5
        self.b.graveyard = [self.db.get("Grizzly Bears")] * 4 + [self.db.get("Island")] * 3
        self.assertEqual(self.cost("Avatar of Woe"), base)                 # 9 creature cards
        self.b.graveyard.append(self.db.get("Hill Giant"))
        self.assertEqual(self.cost("Avatar of Woe"), base - 6)

    def test_attacking_you(self):
        base = self.cost("Red Alert!")
        attacker = self.put("Grizzly Bears", self.b)
        self.g.attackers = [attacker]
        self.assertEqual(self.cost("Red Alert!"), base - 2)
        mine = self.put("Grizzly Bears")
        self.g.attackers = [mine]
        self.assertEqual(self.cost("Red Alert!"), base)                    # my own attacker isn't attacking me

    def test_total_toughness(self):
        base = self.cost("Orysa, Tide Choreographer")
        for _ in range(3):
            self.put("Hill Giant")                                         # 3 toughness each: 9
        self.assertEqual(self.cost("Orysa, Tide Choreographer"), base)
        self.put("Llanowar Elves")
        self.assertEqual(self.cost("Orysa, Tide Choreographer"), base - 3)

    def test_half_life(self):
        base = self.cost("Game Over")
        self.b.life = 11
        self.assertEqual(self.cost("Game Over"), base)
        self.b.life = 10
        self.assertEqual(self.cost("Game Over"), base - 2)

    def test_human_and_non_human(self):
        base = self.cost("Of One Mind")
        self.put("Grizzly Bears")
        self.assertEqual(self.cost("Of One Mind"), base)
        self.put("Elite Vanguard")                                         # Human Soldier
        self.assertEqual(self.cost("Of One Mind"), base - 2)

    def test_share_a_type(self):
        base = self.cost("Synchronized Eviction")
        self.put("Grizzly Bears")
        self.put("Llanowar Elves")
        self.assertEqual(self.cost("Synchronized Eviction"), base)          # Bear and Elf Druid
        self.put("Elvish Mystic")
        self.assertEqual(self.cost("Synchronized Eviction"), base - 2)      # two Elves


if __name__ == "__main__":
    unittest.main()

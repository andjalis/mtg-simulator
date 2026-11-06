"""Cost modifiers over a spell filter, a scope, a condition and an amount (mtgsim/cx_static_cost.py)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
PLAINS = card("Plains", types="Basic Land — Plains", text="({T}: Add {W}.)")
ZOMBIE = card("Test Zombie", "{3}{B}", "Creature — Zombie", "", 3, 3)
KNIGHT = card("Test Knight", "{1}{W}", "Creature — Human Knight", "", 2, 2)
CLERIC = card("Test Cleric", "{1}{B}", "Creature — Human Cleric", "", 2, 2)
RELIC = card("Test Relic", "{3}", "Artifact", "")
DRAKE = card("Test Drake", "{2}{U}", "Creature — Drake", "Flying", 2, 2)
WALL = card("Test Wall", "{2}{U}", "Creature — Wall", "Defender", 0, 4)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class CostModifiers(unittest.TestCase):
    db = None

    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [BEAR] * 20, HeuristicAI())
        self.b = Player("b", [BEAR] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=False)
        for p in (self.a, self.b):
            p.library = list(p.deck)
        self.game.turn, self.game.step, self.game.active_idx = 3, "main1", 0

    def get(self, name):
        c = self.db.get(name)
        self.assertEqual(c.unsupported, [], name)
        return c

    def put(self, name, who=None):
        return self.game.enter_battlefield(who or self.a, self.get(name))

    def cost(self, c, who=None):
        return self.game.cost_of(who or self.a, c)

    def test_parse(self):
        for name in ("Bontu's Monument", "Sunscape Familiar", "Alabaster Leech", "Conduit of Ruin", "Avatar of Hope",
                     "Emet-Selch of the Third Seat", "Geyser Drake", "Edgewalker", "Primeval Protector",
                     "Frogtosser Banneret", "Aura of Silence", "Warden of Evos Isle", "Centaur Omenreader",
                     "Siren Reaver", "Stoic Rebuttal", "Arcane Melee"):
            self.get(name)

    def test_color_and_type_filter(self):
        self.put("Bontu's Monument")
        self.assertEqual(self.cost(ZOMBIE), {"generic": 2, "B": 1})
        self.assertEqual(self.cost(CLERIC), {"generic": 0, "B": 1})
        self.assertEqual(self.cost(BEAR), {"generic": 1, "G": 1})        # green: no reduction
        self.assertEqual(self.cost(ZOMBIE, self.b), {"generic": 3, "B": 1})   # only spells you cast

    def test_alternatives(self):
        self.put("Frogtosser Banneret")          # Goblin spells and Rogue spells
        rogue = card("Test Rogue", "{2}{B}", "Creature — Human Rogue", "", 2, 2)
        self.assertEqual(self.cost(rogue)["generic"], 1)
        self.assertEqual(self.cost(ZOMBIE)["generic"], 3)

    def test_colored_increase(self):
        self.put("Alabaster Leech")
        self.assertEqual(self.cost(KNIGHT), {"generic": 1, "W": 2})
        self.assertEqual(self.cost(ZOMBIE), {"generic": 3, "B": 1})

    def test_colored_reduction_only(self):
        self.put("Edgewalker")                   # Cleric spells cost {W}{B} less, colored mana only
        self.assertEqual(self.cost(CLERIC), {"generic": 1})

    def test_opponents_scope(self):
        self.put("Aura of Silence")
        self.assertEqual(self.cost(RELIC, self.b)["generic"], 5)
        self.assertEqual(self.cost(RELIC)["generic"], 3)

    def test_keyword_filter(self):
        self.put("Warden of Evos Isle")
        self.assertEqual(self.cost(DRAKE)["generic"], 1)
        self.assertEqual(self.cost(WALL)["generic"], 2)

    def test_first_spell_each_turn(self):
        self.put("Conduit of Ruin")
        self.assertEqual(self.cost(ZOMBIE)["generic"], 1)
        self.assertEqual(self.cost(RELIC)["generic"], 3)            # creature spells only
        self.cast_on_stack(CLERIC, SWAMP, 2)
        self.assertEqual(self.cost(ZOMBIE)["generic"], 3)

    def test_turn_scope(self):
        self.put("Geyser Drake")
        self.assertEqual(self.cost(ZOMBIE)["generic"], 3)
        self.game.active_idx = 1
        self.assertEqual(self.cost(ZOMBIE)["generic"], 2)

    def test_static_condition(self):
        omen = self.put("Centaur Omenreader")
        self.assertEqual(self.cost(ZOMBIE)["generic"], 3)
        omen.tapped = True
        self.assertEqual(self.cost(ZOMBIE)["generic"], 1)

    def test_zone_scope(self):
        emet = self.get("Emet-Selch of the Third Seat")
        self.game.enter_battlefield(self.a, emet)
        self.assertEqual(self.cost(ZOMBIE)["generic"], 3)      # cast from hand

    def test_self_condition(self):
        hope = self.get("Avatar of Hope")
        self.assertEqual(self.cost(hope)["generic"], 6)
        self.a.life = 3
        self.assertEqual(self.cost(hope)["generic"], 0)

    def test_self_per_count(self):
        prot = self.get("Primeval Protector")
        base = prot.mana_cost["generic"]
        for _ in range(3):
            self.game.enter_battlefield(self.b, BEAR)
        self.game.enter_battlefield(self.a, BEAR)
        self.assertEqual(self.cost(prot)["generic"], base - 3)

    def cast_on_stack(self, spell, land, lands):
        for _ in range(lands):
            self.game.enter_battlefield(self.a, land)
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell))
        while self.game.stack:
            self.game.resolve_top()

    def test_cast_with_discount(self):
        self.put("Bontu's Monument")
        self.cast_on_stack(ZOMBIE, SWAMP, 3)       # {3}{B} paid with three Swamps
        self.assertTrue(any(x.card.name == ZOMBIE.name for x in self.a.battlefield))
        self.assertTrue(all(x.tapped for x in self.a.battlefield if x.card.name == "Swamp"))


if __name__ == "__main__":
    unittest.main()

"""#329 slice: "Whenever <creature> deals combat damage to a player, create that many <tokens>": engine.combat sets
Game.event_amount (the damage that creature dealt) when it fires combat_damage_player, so the trigger's "that many"
is the damage dealt."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


class Parse(unittest.TestCase):
    def test_that_many_needs_an_event_amount(self):
        hive = card("Hive", "{1}", "Creature — Insect", "Whenever this creature deals combat damage to a player, create "
                    "that many 1/1 green Insect creature tokens.", 3, 3)
        self.assertEqual(hive.unsupported, [])
        self.assertTrue(hive.triggers[0].effects[0].data.get("that_much"))
        # a discard batch carries no count: refused
        chariot = card("Chariot", "{1}", "Artifact", "Whenever you discard one or more cards, create that many tapped "
                       "2/2 black Zombie creature tokens.")
        self.assertNotEqual(chariot.unsupported, [])
        self.assertEqual(_parse_effects("Create that many Treasure tokens.")[1], ["Create that many Treasure tokens."])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Games(unittest.TestCase):
    def test_living_hive_makes_one_token_per_damage(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        a, b = Player("a", [], Scripted()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [db.get("Island")] * 10
        hive = g.enter_battlefield(a, db.get("Living Hive"))       # 6/6 trample
        hive.sick = False
        g.settle()
        a.ai.attack = [hive]
        g.combat(a, b)
        g.settle()
        self.assertEqual(b.life, 14)
        self.assertEqual(sum(1 for x in a.battlefield if x.card.is_token and "Insect" in x.card.name), 6)


if __name__ == "__main__":
    unittest.main()

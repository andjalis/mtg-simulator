import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.decklist import parse_decklist
from mtgsim.engine import Game, Permanent, Player, find_payment
from mtgsim.ai import HeuristicAI

DB = CardDB(offline=True)


def perm(name, owner, sick=False):
    p = Permanent(DB.get(name), owner)
    p.sick = sick
    owner.battlefield.append(p)
    return p


class DecklistTests(unittest.TestCase):
    def test_formats(self):
        text = "Deck\n4 Lightning Bolt (M10) 146\n2x Shock\n// comment\n20 Mountain\n\nSideboard\n3 Murder\n"
        self.assertEqual(parse_decklist(text), {"Lightning Bolt": 4, "Shock": 2, "Mountain": 20})

    def test_pasted_table(self):
        text = ("1. UB Control (1v1), 60 cards\nCreatures (2)\n\nQty\tCard Name\tColor\n"
                "1\tTolarian Terror (new)\tBlue\n2\tJwari Disruption // Jwari Ruins\tBlue\n"
                "Sideboard (3)\n3\tDuress\tBlack\tControl\n")
        self.assertEqual(parse_decklist(text), {"Tolarian Terror": 1, "Jwari Disruption": 2})


class CardParsingTests(unittest.TestCase):
    def test_burn_and_keywords(self):
        bolt = DB.get("Lightning Bolt")
        self.assertEqual((bolt.spell_effects[0].kind, bolt.spell_effects[0].amount), ("damage", 3))
        self.assertTrue(bolt.fully_supported)
        self.assertEqual(DB.get("Vampire Nighthawk").keywords, {"flying", "deathtouch", "lifelink"})
        highlands = DB.get("Rugged Highlands")
        self.assertTrue(highlands.enters_tapped)
        self.assertEqual(highlands.produces, {"R", "G"})
        self.assertTrue(DB.get("Goblin Guide").fully_supported)
        self.assertFalse(DB.get("Old-Growth Troll").fully_supported)


class ManaTests(unittest.TestCase):
    def test_payment_saves_dual_land(self):
        me = Player("me", [], HeuristicAI())
        forest, dual = perm("Forest", me), perm("Rugged Highlands", me)
        pay = find_payment([forest, dual], DB.get("Kalonian Tusker").mana_cost)
        self.assertEqual(set(pay), {forest, dual})
        self.assertIsNone(find_payment([forest], DB.get("Kalonian Tusker").mana_cost))
        self.assertIsNone(find_payment([forest, dual], DB.get("Murder").mana_cost))


class CombatTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))

    def test_trample_over_chump(self):
        maw = perm("Colossal Dreadmaw", self.a)
        elf = perm("Llanowar Elves", self.b)
        self.game.combat_damage(self.a, self.b, [maw], {maw: [elf]}, lambda c: True)
        self.assertEqual(self.b.life, 15)
        self.assertNotIn(elf, self.b.battlefield)

    def test_deathtouch_lifelink(self):
        hawk = perm("Vampire Nighthawk", self.a)
        maw = perm("Colossal Dreadmaw", self.b)
        self.game.combat_damage(self.a, self.b, [hawk], {hawk: [maw]}, lambda c: True)
        self.assertNotIn(maw, self.b.battlefield)
        self.assertEqual(self.a.life, 22)

    def test_full_game_finishes(self):
        deck = [DB.get("Mountain")] * 24 + [DB.get("Raging Goblin")] * 36
        winner = Game(Player("x", deck, HeuristicAI()), Player("y", deck, HeuristicAI()),
                      random.Random(1)).play()
        self.assertIsNotNone(winner)


if __name__ == "__main__":
    unittest.main()

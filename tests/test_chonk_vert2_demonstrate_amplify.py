"""Demonstrate and amplify: templates and engine behavior (chonk/vert batch 2)."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import card

import json
import sqlite3

DB = sqlite3.connect("mtgsim/data/cards.sqlite3")
RAW = {k: json.loads(d) for k, d in DB.execute("select key, data from cards")}


def real(name):
    from mtgsim import cards
    return cards.card_from_scryfall(RAW[name.lower()])


TECHNIQUE = card("Test Technique", "{2}{W}", "Sorcery", "Demonstrate\nYou gain 2 life.")
BRUTE = card("Test Brute", "{6}{B}", "Creature — Zombie", "Amplify 1\nTrample", 3, 3)
OTHER_ZOMBIE = card("Test Ghoul", "{1}{B}", "Creature — Zombie", "", 1, 1)
DRAGON = real("Kilnmouth Dragon")


class ParseWordings(unittest.TestCase):
    def test_demonstrate_cast_trigger(self):
        self.assertEqual([(t.event, [e.kind for e in t.effects]) for t in TECHNIQUE.cast_self_triggers],
                         [("cast_self", ["demonstrate"])])
        self.assertEqual(TECHNIQUE.unsupported, [])

    def test_amplify_etb_trigger(self):
        self.assertEqual([(t.event, t.effects[0].kind, t.effects[0].amount) for t in BRUTE.triggers],
                         [("etb", "amplify", 1)])
        self.assertEqual(BRUTE.unsupported, [])

    def test_real_cards(self):
        for name in ("Incarnation Technique", "Excavation Technique", "Creative Technique",
                     "Zombie Brute", "Aven Warhawk", "Ghastly Remains", "Embalmed Brawler",
                     "Glowering Rogon"):
            c = real(name)
            word = "Demonstrate" if "Demonstrate" in (RAW[name.lower()]["oracle_text"] or "") else "Amplify"
            self.assertNotIn(word, c.unsupported, (name, c.unsupported))


class DemonstrateEngine(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(3), log=True)
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [card("Test Plains", types="Basic Land — Plains", text="({T}: Add {W}.)")] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None
        for _ in range(7):
            self.g.enter_battlefield(self.a, card("Test Plains", types="Basic Land — Plains",
                                                  text="({T}: Add {W}.)"))
        self.g.settle()

    def test_demonstrate_copies_for_both_players(self):
        self.a.hand = [TECHNIQUE]
        self.assertTrue(self.g.cast(self.a, TECHNIQUE))
        self.g.settle()
        # two copies resolved: one for each player
        copies = [l for l in self.g.events if "copies Test Technique" in l]
        self.assertEqual(len(copies), 2)
        self.assertEqual(self.a.life, 24)          # own cast + own copy
        self.assertEqual(self.b.life, 22)         # the opponent's copy
        self.assertEqual([e.kind for e in TECHNIQUE.cast_self_triggers[0].effects], ["demonstrate"])


class AmplifyEngine(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(3))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [card("Test Plains", types="Basic Land — Plains", text="({T}: Add {W}.)")] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def test_amplify_counts_sharing_hand_cards(self):
        self.a.hand = [OTHER_ZOMBIE, OTHER_ZOMBIE, card("Test Bear", "{1}{G}", "Creature — Bear", "", 2, 2)]
        brute = self.g.enter_battlefield(self.a, BRUTE)
        self.g.settle()
        self.assertEqual(brute.p1, 2)          # 2 zombies in hand -> 2 counters
        self.assertEqual((brute.power, brute.toughness), (5, 5))

    def test_amplify_three_times_a_dragon(self):
        self.a.hand = [DRAGON, DRAGON]
        dragon = self.g.enter_battlefield(self.a, DRAGON)
        self.g.settle()
        self.assertEqual(dragon.p1, 6)          # amplify 3, two Dragons revealed
        self.assertEqual((dragon.power, dragon.toughness), (11, 11))


if __name__ == "__main__":
    unittest.main()

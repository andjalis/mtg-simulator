"""Round 13: exile the top card and play it later, "until ~ leaves" exile with restrictions."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, card

PEEK = card("Test Peek", "{1}{R}", "Sorcery", "Exile the top card of your library. You may play that card this turn.")
LONG = card("Test Long Peek", "{2}{R}", "Sorcery", "Exile the top two cards of your library. Until the end of your next "
            "turn, you may play them.")
JAILER = card("Test Jailer", "{2}{W}", "Creature — Human Soldier", "When ~ enters, exile up to one other target non-Assassin "
              "creature until ~ leaves the battlefield.", 2, 2)
WARDEN = card("Test Warden", "{3}{W}", "Creature — Human", "When ~ enters, exile up to one target artifact, creature, or "
              "enchantment an opponent controls with mana value 3 or greater until ~ leaves the battlefield.", 3, 3)
MOUNTAIN = card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")
PLAINS = card("Plains", types="Basic Land — Plains", text="({T}: Add {W}.)")
BIG = card("Big Thing", "{3}", "Creature — Golem", "", 3, 3)
ASSASSIN = card("Test Assassin", "{1}", "Creature — Assassin", "", 1, 1)


class Round13(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, who=None):
        p = Permanent(c, who or self.a)
        p.sick = False
        p.controller.battlefield.append(p)
        return p

    def cast(self, spell, lands):
        for l in lands:
            self.perm(l)
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, []))
        self.game.settle()

    def test_templates(self):
        for c in (PEEK, LONG, JAILER, WARDEN):
            self.assertEqual(c.unsupported, [], c.name)

    def test_exiled_card_is_castable_this_turn_only(self):
        self.a.library = [ISLAND] * 5 + [BIG]
        self.cast(PEEK, [MOUNTAIN, MOUNTAIN])
        self.assertIn(BIG, self.a.exile)
        self.assertTrue(any(self.game._origin(c)[0] is BIG for c in self.game.spell_options(self.a)))
        self.game.turn = 2
        self.assertFalse(any(self.game._origin(c)[0] is BIG for c in self.game.spell_options(self.a)))

    def test_next_turn_window_and_land_drop(self):
        self.a.library = [ISLAND] * 5 + [PLAINS, BIG]
        self.cast(LONG, [MOUNTAIN] * 3)
        self.game.turn = 3          # our next turn
        self.assertEqual(set(map(id, self.game.impulse_cards(self.a))), {id(PLAINS), id(BIG)})
        self.game.play_land(self.a, PLAINS)
        self.assertNotIn(PLAINS, self.a.exile)
        self.assertEqual(self.a.lands_played, 1)
        self.game.turn = 4
        self.assertEqual(self.game.impulse_cards(self.a), [])

    def test_jailer_returns_creature_when_it_leaves(self):
        victim = self.perm(BIG, self.b)
        self.cast(JAILER, [PLAINS] * 3)
        self.assertNotIn(victim, self.b.battlefield)
        jail = next(x for x in self.a.battlefield if x.card is JAILER)
        self.game.leave_battlefield(jail, "graveyard")
        self.game.settle()
        self.assertTrue(any(x.card is BIG for x in self.b.battlefield))

    def test_assassin_is_not_a_legal_target(self):
        self.perm(ASSASSIN, self.b)
        self.cast(JAILER, [PLAINS] * 3)
        self.assertTrue(any(x.card is ASSASSIN for x in self.b.battlefield))

    def test_warden_needs_mana_value_three(self):
        small = self.perm(BEAR, self.b)
        self.cast(WARDEN, [PLAINS] * 4)
        self.assertIn(small, self.b.battlefield)

    def test_behold_or_pay(self):
        c = card("Test Beholder", "{1}{R}", "Creature — Goblin", "As an additional cost to cast ~, behold a Goblin or pay {2}.", 2, 2)
        self.assertEqual(c.unsupported, [])
        self.assertEqual(self.game.cost_of(self.a, c).get("generic"), 3)
        gob = card("Test Goblin", "{1}", "Creature — Goblin", "", 1, 1)
        self.perm(gob)
        self.assertEqual(self.game.cost_of(self.a, c).get("generic"), 1)


if __name__ == "__main__":
    unittest.main()

"""Valiant, Opus, Repartee and Eerie triggers."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

HERO = card("Test Hero", "{1}{R}", "Creature — Mouse", "Valiant — Whenever ~ becomes the target of a spell or ability you "
            "control for the first time each turn, put a +1/+1 counter on it.", 1, 1)
SKYWHALE = card("Test Whale", "{3}{R}", "Creature — Whale", "Opus — Whenever you cast an instant or sorcery spell, ~ gets +3/+0 "
                "until end of turn. If five or more mana was spent to cast that spell, put three +1/+1 counters on ~ instead.", 2, 2)
POET = card("Test Poet", "{1}{B}", "Creature — Bard", "Repartee — Whenever you cast an instant or sorcery spell that targets a "
            "creature, each opponent loses 1 life and you gain 1 life.", 1, 1)
TRACKER = card("Test Tracker", "{2}{U}", "Creature — Detective", "Eerie — Whenever an enchantment you control enters and "
               "whenever you fully unlock a Room, draw a card.", 2, 2)
GROWTH = card("Giant Growth", "{R}", "Instant", "Target creature gets +3/+3 until end of turn.")
BIGSPELL = card("Big Burn", "{4}{R}", "Sorcery", "~ deals 1 damage to any target.")
SHOCK = card("Shock", "{R}", "Instant", "Shock deals 2 damage to any target.")
ENCH = card("Pacifism-ish", "{W}", "Enchantment", "")


class AbilityWords(unittest.TestCase):
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

    def lands(self, n):
        for _ in range(n):
            self.perm(MOUNTAIN)

    def test_templates(self):
        for c in (HERO, SKYWHALE, POET, TRACKER):
            self.assertEqual(c.unsupported, [], c.name)

    def test_valiant_only_first_time_each_turn(self):
        hero = self.perm(HERO)
        self.lands(2)
        for _ in range(2):
            self.a.hand.append(GROWTH)
            self.assertTrue(self.game.cast(self.a, GROWTH, [hero]))
            self.game.settle()
        self.assertEqual(hero.p1, 1)

    def test_opus_small_then_big(self):
        whale = self.perm(SKYWHALE)
        self.lands(1)
        self.a.hand.append(SHOCK)
        self.game.cast(self.a, SHOCK, [self.b])
        self.game.settle()
        self.assertEqual((whale.pump_p, whale.p1), (3, 0))
        whale.pump_p = 0
        self.lands(5)
        self.a.hand.append(BIGSPELL)
        self.game.cast(self.a, BIGSPELL, [self.b])
        self.game.settle()
        self.assertEqual((whale.pump_p, whale.p1), (0, 3))

    def test_repartee_needs_a_creature_target(self):
        self.perm(POET)
        bear = self.perm(BEAR, self.b)
        self.lands(2)
        self.a.hand += [SHOCK, SHOCK]
        self.game.cast(self.a, SHOCK, [self.b])
        self.game.settle()
        self.assertEqual(self.b.life, 18)
        self.game.cast(self.a, SHOCK, [bear])
        self.game.settle()
        self.assertEqual((self.b.life, self.a.life), (17, 21))

    def test_eerie_draws_when_an_enchantment_enters(self):
        self.perm(TRACKER)
        before = len(self.a.hand)
        self.game.enter_battlefield(self.a, ENCH)
        self.game.settle()
        self.assertEqual(len(self.a.hand), before + 1)


if __name__ == "__main__":
    unittest.main()

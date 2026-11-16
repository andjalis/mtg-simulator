"""#568: coin flips with one result per player or per creature, and uncalled heads/tails coins (chance_each.py)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_coinflip_remainder import Coins
from tests.test_templates import BEAR, ISLAND, card

DEMON = card("Test Demon", "{2}{B}", "Creature — Demon", "", 3, 3)


class CoinFlipEach(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    @classmethod
    def tearDownClass(cls):
        if cls.db._all is not None:
            cls.db._all.close()

    def real(self, name):
        if self.db._all is None:
            self.skipTest("card database not built")
        return self.db.get(name)

    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick = p.tapped = False
        owner.battlefield.append(p)
        return p

    def test_real_cards_are_full(self):
        for name in ("Goblin Assassin", "Mana Clash", "Rakdos, the Showstopper", "Two-Headed Giant",
                     "Mutalith Vortex Beast", "Fiery Gambit", "Squee's Revenge"):
            with self.subTest(card=name):
                self.assertEqual(self.real(name).unsupported, [])

    def test_near_misses_refused(self):
        for text in ("Each player flips a coin. Each player whose coin comes up tails discards their hand.",
                     "Flip a coin for each creature that isn't a Demon. Exile each creature whose coin comes up tails.",
                     "Flip two coins. If both coins come up heads, draw a card. If both coins come up heads, "
                     "draw a card."):
            with self.subTest(text=text):
                effects, bad = _parse_effects(text)
                self.assertTrue(bad, effects)
                self.assertNotIn("FLIPEACH", " ".join(bad))

    def test_goblin_assassin_tails_player_sacrifices(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        assassin = self.real("Goblin Assassin")
        self.g.rng = Coins(True, False)            # active player (a) heads, b tails
        self.g.enter_battlefield(self.a, assassin)
        self.g.settle()
        self.assertNotIn(theirs, self.b.battlefield)
        self.assertIn(mine, self.a.battlefield)

    def resolve_spell(self, c, targets=None):
        effects = list(c.spell_effects)
        item = StackItem(self.a, effects, targets or [None] * len(effects), card=c)
        self.g.stack.append(item)
        self.g.resolve_top()

    def test_mana_clash_repeats_until_both_heads(self):
        self.g.rng = Coins(False, True, True, False, True, True)
        self.resolve_spell(self.real("Mana Clash"))
        self.assertEqual((self.a.life, self.b.life), (19, 19))
        self.assertEqual(self.g.rng.calls, 6)

    def test_rakdos_destroys_tails_non_demons(self):
        mine = self.perm(BEAR, self.a)
        theirs, demon = self.perm(BEAR, self.b), self.perm(DEMON, self.b)
        self.g.rng = Coins(False, True)            # two coins: one per non-Demon creature (Rakdos is a Demon)
        self.g.enter_battlefield(self.a, self.real("Rakdos, the Showstopper"))
        self.g.settle()
        self.assertEqual(self.g.rng.calls, 2)
        self.assertNotIn(mine, self.a.battlefield)
        self.assertIn(theirs, self.b.battlefield)
        self.assertIn(demon, self.b.battlefield)

    def giant_attacks(self, *wins):
        giant = self.perm(self.real("Two-Headed Giant"), self.a)
        watcher = card("Watcher", types="Enchantment", text="Whenever you win a coin flip, draw a card.")
        self.perm(watcher, self.a)
        self.g.step = "declare_attackers"
        self.g.attackers = [giant]
        self.g.rng = Coins(*wins)
        self.g.fire(self.a, "attacks", giant)
        self.g.settle()
        return giant

    def test_two_headed_giant_both_heads(self):
        giant = self.giant_attacks(True, True)
        self.assertTrue(giant.has("double strike"))
        self.assertFalse(giant.has("menace"))
        self.assertEqual(len(self.a.hand), 0)      # nobody called these coins: no flip was won

    def test_two_headed_giant_both_tails(self):
        giant = self.giant_attacks(False, False)
        self.assertTrue(giant.has("menace"))
        self.assertFalse(giant.has("double strike"))

    def test_two_headed_giant_mixed(self):
        giant = self.giant_attacks(True, False)
        self.assertFalse(giant.has("menace") or giant.has("double strike"))

    # flip loops with a choice
    def test_fiery_gambit_stops_after_one_win(self):
        target = self.perm(BEAR, self.b)
        gambit = self.real("Fiery Gambit")
        self.g.rng = Coins(True, True, True)
        self.resolve_spell(gambit, targets=[None, target, self.b, None, None])
        self.assertEqual(self.g.rng.calls, 1)      # one tier taken, no gamble for the next
        self.assertNotIn(target, self.b.battlefield)
        self.assertEqual(self.b.life, 20)

    def test_fiery_gambit_goes_for_lethal(self):
        target = self.perm(BEAR, self.b)
        self.b.life = 6
        self.g.rng = Coins(True, True)
        self.resolve_spell(self.real("Fiery Gambit"), targets=[None, target, self.b, None, None])
        self.assertEqual(self.g.rng.calls, 2)
        self.assertLessEqual(self.b.life, 0)

    def test_fiery_gambit_a_loss_means_no_effect(self):
        target = self.perm(BEAR, self.b)
        self.b.life = 6
        self.g.rng = Coins(True, False)
        self.resolve_spell(self.real("Fiery Gambit"), targets=[None, target, self.b, None, None])
        self.assertIn(target, self.b.battlefield)
        self.assertEqual(self.b.life, 6)

    def test_squees_revenge_all_won(self):
        self.g.rng = Coins(True, True)
        self.resolve_spell(self.real("Squee's Revenge"))
        self.assertEqual((self.g.rng.calls, len(self.a.hand)), (2, 4))

    def test_squees_revenge_a_loss_draws_nothing(self):
        self.g.rng = Coins(True, False)
        self.resolve_spell(self.real("Squee's Revenge"))
        self.assertEqual(len(self.a.hand), 0)

    def test_mutalith_lost_flip_damages_the_opponent(self):
        self.g.rng = Coins(False)
        self.g.enter_battlefield(self.a, self.real("Mutalith Vortex Beast"))
        self.g.settle()
        self.assertEqual((self.b.life, len(self.a.hand)), (17, 0))

    def test_mutalith_won_flip_draws(self):
        self.g.rng = Coins(True)
        self.g.enter_battlefield(self.a, self.real("Mutalith Vortex Beast"))
        self.g.settle()
        self.assertEqual((self.b.life, len(self.a.hand)), (20, 1))


if __name__ == "__main__":
    unittest.main()

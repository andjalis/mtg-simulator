"""#322 tail: coin-flip riders that needed effects. The delayed "flip a coin at end of combat" with its riders in one
delayed group (Fickle Efreet), "an opponent / one of your opponents gains control of ~" (two players: the one
opponent), "remove ~ from combat and tap it" (Mijae Djinn), and Krark's "return that spell to its owner's hand" /
"copy that spell, and you may choose new targets for the copy" on the spell its cast trigger fired on."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Permanent, Player
from tests.test_coinflip_remainder import Coins
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")


class CoinFlipEffects(unittest.TestCase):
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
        for name in ("Fickle Efreet", "Mijae Djinn", "Goblin Festival", "Krark, the Thumbless", "Wishclaw Talisman",
                     "Rainbow Vale"):
            with self.subTest(card=name):
                self.assertEqual(self.real(name).unsupported, [])

    def test_near_misses_refused(self):
        for text in ("Remove ~ from combat and it can't block this turn.",
                     # "turn ~ face down" is supported since #635 (Skittish Valesk): another rider stands in
                     "Flip a coin at end of combat. If you lose the flip, ~ phases out and can't phase in until your "
                     "next turn."):
            with self.subTest(text=text):
                effects, bad = _parse_effects(text)
                self.assertTrue(bad, effects)
        self.assertTrue(self.real("Ydwen Efreet").unsupported)      # "become unblocked" is not modelled

    # Fickle Efreet: the flip waits for end of combat
    def attack_with_efreet(self, *wins):
        efreet = self.perm(self.real("Fickle Efreet"), self.a)
        self.g.step = "declare_attackers"
        self.g.attackers = [efreet]
        self.g.rng = Coins(*wins)
        self.g.fire(self.a, "attacks", efreet)
        self.g.settle()
        self.assertEqual(self.g.rng.calls, 0)       # nothing flipped yet
        self.g.end_combat(self.a)
        self.g.settle()
        return efreet

    def test_fickle_efreet_lost_flip_gives_it_away(self):
        efreet = self.attack_with_efreet(False)
        self.assertIn(efreet, self.b.battlefield)
        self.assertIs(efreet.controller, self.b)

    def test_fickle_efreet_won_flip_keeps_it(self):
        efreet = self.attack_with_efreet(True)
        self.assertIn(efreet, self.a.battlefield)

    # Mijae Djinn
    def test_mijae_lost_flip_removes_and_taps(self):
        djinn = self.perm(self.real("Mijae Djinn"), self.a)
        self.g.step = "declare_attackers"
        self.g.attackers = [djinn]
        self.g.rng = Coins(False)
        self.g.fire(self.a, "attacks", djinn)
        self.g.settle()
        self.assertNotIn(djinn, self.g.attackers)
        self.assertTrue(djinn.tapped)

    def test_mijae_won_flip_keeps_attacking(self):
        djinn = self.perm(self.real("Mijae Djinn"), self.a)
        self.g.step = "declare_attackers"
        self.g.attackers = [djinn]
        self.g.rng = Coins(True)
        self.g.fire(self.a, "attacks", djinn)
        self.g.settle()
        self.assertIn(djinn, self.g.attackers)

    # Goblin Festival: "choose one of your opponents. That player gains control of ~"
    def test_goblin_festival_lost_flip_gives_it_away(self):
        festival = self.perm(self.real("Goblin Festival"), self.a)
        ability = festival.card.activated[0]
        from mtgsim.engine import StackItem
        item = StackItem(self.a, list(ability.effects), [self.b] + [None] * (len(ability.effects) - 1),
                         source=festival, kind="ability")
        self.g.rng = Coins(False)
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertEqual(self.b.life, 19)
        self.assertIn(festival, self.b.battlefield)

    # the two-player "an opponent gains control of ~" on other cards
    def test_wishclaw_talisman_goes_to_the_opponent(self):
        talisman = self.perm(self.real("Wishclaw Talisman"), self.a)
        talisman.counters["wish"] = 3
        ability = talisman.card.activated[0]
        from mtgsim.engine import StackItem
        item = StackItem(self.a, list(ability.effects), [None] * len(ability.effects), source=talisman, kind="ability")
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertIn(talisman, self.b.battlefield)
        self.assertEqual(len(self.a.hand), 1)        # the tutored card

    def test_rainbow_vale_changes_control_at_end_step(self):
        vale = self.perm(self.real("Rainbow Vale"), self.a)
        ability = vale.card.activated[0]
        from mtgsim.engine import StackItem
        item = StackItem(self.a, list(ability.effects), [None] * len(ability.effects), source=vale, kind="ability")
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertIn(vale, self.a.battlefield)      # not yet
        self.g.begin_end_step(self.a)
        self.g.settle()
        self.assertIn(vale, self.b.battlefield)

    # Krark: the cast spell, not a target
    def cast_bolt_with_krark(self, *wins):
        self.perm(self.real("Krark, the Thumbless"), self.a)
        self.perm(MOUNTAIN, self.a)
        self.a.hand = [BOLT]
        self.g.rng = Coins(*wins)
        self.assertTrue(self.g.cast(self.a, BOLT, [self.b]))
        self.g.settle()

    def test_krark_lost_flip_returns_the_spell(self):
        self.cast_bolt_with_krark(False)
        self.assertEqual(self.b.life, 20)
        self.assertIn(BOLT, self.a.hand)

    def test_krark_won_flip_copies_the_spell(self):
        self.cast_bolt_with_krark(True)
        self.assertEqual(self.b.life, 14)           # the copy and the original
        self.assertIn(BOLT.name, [c.name for c in self.a.graveyard])


if __name__ == "__main__":
    unittest.main()

"""#322: coin-flip riders the single-sentence templates miss. "Flip a coin." followed by its win and lose
riders in either order, a rider of several sentences, "When you win/lose the flip", and a flip made by
"that player" ("If they lose the flip"). Each rider runs on the flip's own result (conds flip_won /
flip_lost), so a declined "If you do, flip a coin" runs neither."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_coinflip_remainder import Coins
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")


class CoinFlipRiders(unittest.TestCase):
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
            for _ in range(4):
                self.perm(MOUNTAIN, p)

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick = p.tapped = False
        owner.battlefield.append(p)
        return p

    def resolve(self, text, *wins):
        effects, bad = _parse_effects(text)
        self.assertFalse(bad, bad)
        item = StackItem(self.a, effects, [None] * len(effects))
        self.g.rng = Coins(*wins)
        self.g.stack.append(item)
        self.g.resolve_top()
        return item

    # parser: real cards
    def test_real_cards_are_full(self):
        for name in ("Breeches, the Blastmaker", "Planar Chaos"):
            with self.subTest(card=name):
                self.assertEqual(self.real(name).unsupported, [])

    def test_breeches_riders_read_the_flip_not_the_sacrifice(self):
        trig = self.real("Breeches, the Blastmaker").triggers[0]
        kinds = [(e.kind, e.cond) for e in trig.effects]
        self.assertEqual(kinds[0][0], "pay_gate")
        self.assertEqual(kinds[1], ("flip_coin", "paid"))
        self.assertIn(("copy_spell", "flip_won"), kinds)
        self.assertIn(("damage", "flip_lost"), kinds)

    def test_planar_chaos_flipper_is_the_caster(self):
        trig = [t for t in self.real("Planar Chaos").triggers if t.event == "any_cast"][0]
        self.assertEqual([(e.kind, e.target, e.cond) for e in trig.effects],
                         [("flip_coin", "that_player", ""), ("counter", "spell", "flip_lost")])

    # parser: near misses stay unmatched
    def test_near_misses_refused(self):
        for text in (
            # the same side twice
            "Flip a coin. If you win the flip, draw a card. If you win the flip, draw a card.",
            # "they" without another player flipping
            "Flip a coin. If they lose the flip, you lose 1 life. If you win the flip, draw a card.",
            # an unsupported rider sentence keeps the whole line unmatched
            # ("turn ~ face down" is supported since #635, so a still-unsupported rider stands in)
            "Flip a coin. If you lose the flip, you lose 1 life. If you win the flip, ~ phases out and can't phase in "
            "until your next turn.",
        ):
            with self.subTest(text=text):
                effects, bad = _parse_effects(text)
                self.assertTrue(bad, effects)
                self.assertNotIn("FLIPSEQ", " ".join(bad))

    def test_unsupported_real_riders_keep_oracle_wording(self):
        for name in ("Ydwen Efreet",):          # Skittish Valesk is full since #635 ("turn ~ face down")
            with self.subTest(card=name):
                c = self.real(name)
                self.assertTrue(c.unsupported)
                self.assertNotIn("FLIPSEQ", str(c.unsupported))

    def test_skittish_valesk_turns_face_down_on_a_lost_flip(self):
        c = self.real("Skittish Valesk")
        self.assertTrue(c.fully_supported)
        effects = c.triggers[0].effects
        self.assertEqual([e.kind for e in effects], ["flip_coin", "turn_face_down"])

    # resolution
    def test_lose_then_win_order(self):
        text = "Flip a coin. If you lose the flip, you lose 2 life. If you win the flip, draw a card."
        self.resolve(text, True)
        self.assertEqual((len(self.a.hand), self.a.life), (1, 20))
        self.resolve(text, False)
        self.assertEqual((len(self.a.hand), self.a.life), (1, 18))

    def test_multi_sentence_rider(self):
        text = ("Flip a coin. If you win the flip, draw a card. You gain 3 life. "
                "If you lose the flip, you lose 2 life.")
        self.resolve(text, True)
        self.assertEqual((len(self.a.hand), self.a.life), (1, 23))
        self.resolve(text, False)
        self.assertEqual((len(self.a.hand), self.a.life), (1, 21))

    def test_gate_inside_a_rider_keeps_the_flip_result(self):
        text = ("Flip a coin. If you lose the flip, you lose 1 life. If you win the flip, you may pay 2 life. "
                "If you do, draw two cards.")
        effects, bad = _parse_effects(text)
        self.assertFalse(bad, bad)
        self.assertTrue(any(e.kind == "pay_gate" for e in effects))
        self.resolve(text, True)                   # the AI pays: draw two, and the lose rider stays off
        self.assertEqual((len(self.a.hand), self.a.life), (2, 18))

    def test_declined_gate_runs_neither_rider(self):
        text = ("You may sacrifice an artifact. If you do, flip a coin. When you win the flip, draw a card. "
                "You gain 1 life. When you lose the flip, you lose 3 life.")
        effects, bad = _parse_effects(text)
        self.assertFalse(bad, bad)
        item = StackItem(self.a, effects, [None] * len(effects))
        self.g.rng = Coins(False)
        self.g.stack.append(item)
        self.g.resolve_top()           # no artifact to sacrifice: the flip never happens
        self.assertEqual((len(self.a.hand), self.a.life, self.g.rng.calls), (0, 20, 0))

    def test_planar_chaos_counters_on_casters_lost_flip(self):
        chaos = self.real("Planar Chaos")
        self.perm(chaos, self.a)
        self.b.hand = [BOLT]
        self.g.rng = Coins(False)
        self.g.cast(self.b, BOLT, [self.a])
        self.g.settle()
        self.assertEqual(self.a.life, 20)          # countered
        self.assertIn(BOLT.name, [c.name for c in self.b.graveyard])

    def test_planar_chaos_spell_resolves_on_casters_won_flip(self):
        chaos = self.real("Planar Chaos")
        self.perm(chaos, self.a)
        watcher = card("Watcher", types="Enchantment", text="Whenever you win a coin flip, draw a card.")
        self.perm(watcher, self.b)
        self.b.hand = [BOLT]
        self.g.rng = Coins(True)
        self.g.cast(self.b, BOLT, [self.a])
        self.g.settle()
        self.assertEqual(self.a.life, 17)          # the caster won the flip: the bolt resolves
        self.assertEqual(len(self.b.hand), 1)      # and it was the caster's win (their watcher drew)


if __name__ == "__main__":
    unittest.main()

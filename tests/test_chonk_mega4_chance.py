"""mega-batch4 (5): clash and coin flips — the general shapes.

"Clash with an opponent. If you win, <X>." becomes a ``clash`` gate effect (reveal each
library's top card, the bigger mana value wins) followed by the payoff with cond "paid"
(the pay_gate pattern); "Flip a coin. If you win / lose the flip, <X>." is the same with
a fair coin. The kinds fire you_clash / you_win_clash so "Whenever you clash [and win]"
is a normal trigger. Die rolls (per-face amounts) are a foundation need, not covered.
"""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem
from tests.test_batch1 import Batch1
from tests.test_templates import card

BIG = card("Test Expensive", "{7}{U}", "Sorcery", "", cmc=8)
CHEAP = card("Test Cheap", "{U}", "Instant", "", cmc=1)
LASH_OUT = card("Test Lash Out", "{1}{R}", "Instant",
                "Test Lash Out deals 3 damage to target creature. Clash with an opponent. "
                "If you win, Test Lash Out deals 3 damage to that creature's controller.")
MANA_CRYPT = card("Test Crypt", "{0}", "Artifact",
                  "At the beginning of your upkeep, flip a coin. If you lose the flip, "
                  "this artifact deals 3 damage to you.\n{T}: Add {C}{C}.")


class ChanceParse(unittest.TestCase):
    def parse(self, text):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        return effects

    def test_clash_with_win_rider(self):
        effects = self.parse("clash with an opponent. if you win, draw a card")
        self.assertEqual([(e.kind, e.cond) for e in effects],
                         [("clash", ""), ("draw", "paid")])

    def test_clash_defending_player_and_won(self):
        effects = self.parse("clash with defending player. if you won, draw a card")
        self.assertEqual([(e.kind, e.cond) for e in effects],
                         [("clash", ""), ("draw", "paid")])

    def test_bare_clash(self):
        effects = self.parse("clash with an opponent")
        self.assertEqual([e.kind for e in effects], ["clash"])

    def test_flip_win_and_lose(self):
        effects = self.parse("flip a coin. if you win the flip, draw a card")
        self.assertEqual([(e.kind, e.cond) for e in effects],
                         [("flip_coin", ""), ("draw", "paid")])
        effects = self.parse("flip a coin. if you lose the flip, you lose 3 life")
        self.assertEqual([(e.kind, e.cond, e.data.get("on_lose")) for e in effects],
                         [("flip_coin", "", True), ("lose_life", "paid", None)])
        self.assertEqual(effects[1].amount, 3)

    def test_templates(self):
        self.assertEqual(LASH_OUT.unsupported, [])
        self.assertEqual(MANA_CRYPT.unsupported, [])


class ClashBehavior(Batch1):
    def resolve_clash(self, mine, theirs):
        effects, bad = _parse_effects("clash with an opponent. if you win, you gain 1 life")
        self.assertFalse(bad, bad)
        self.a.library = [mine] if mine else []
        self.b.library = [theirs] if theirs else []
        item = StackItem(self.a, effects, [None, None])
        self.g.stack.append(item)
        self.g.resolve_top()
        return item

    def test_bigger_card_wins(self):
        item = self.resolve_clash(BIG, CHEAP)
        self.assertTrue(item.gate_paid)
        self.assertEqual(self.a.life, 21)               # the rider ran

    def test_smaller_or_empty_library_loses(self):
        self.assertFalse(self.resolve_clash(CHEAP, BIG).gate_paid)
        self.assertFalse(self.resolve_clash(None, CHEAP).gate_paid)
        self.assertEqual(self.a.life, 20)               # no rider ran
        self.assertTrue(self.resolve_clash(BIG, None).gate_paid)

    def test_revealed_cards_stay_on_top(self):
        self.resolve_clash(BIG, CHEAP)
        self.assertEqual(self.a.library, [BIG])
        self.assertEqual(self.b.library, [CHEAP])

    def test_clash_triggers_fire(self):
        watcher = card("Test Marvo", "{3}{U}{B}", "Creature — Octopus Rogue",
                        "Whenever you win a clash, draw a card.", 1, 8)
        perm = self.g.enter_battlefield(self.a, watcher)
        effects, bad = _parse_effects("clash with an opponent")
        self.assertFalse(bad, bad)
        self.a.library, self.b.library = [BIG], [CHEAP]
        self.g.resolve(self.a, effects[0], None, StackItem(self.a, effects, [None]))
        self.g.flush_triggers()
        while self.g.stack:
            self.g.resolve_top()
            self.g.settle()
        self.assertEqual(len(self.a.hand), 1)          # the you_win_clash trigger drew
        self.assertEqual(perm.card.name, watcher.name)


class FlipBehavior(Batch1):
    def flip_effects(self, side="win"):
        text = {"win": "flip a coin. if you win the flip, you gain 1 life",
                "lose": "flip a coin. if you lose the flip, you gain 1 life"}[side]
        effects, bad = _parse_effects(text)
        self.assertFalse(bad, bad)
        return effects

    def flips(self, side="win", n=100):
        won = 0
        effects = self.flip_effects(side)
        for _ in range(n):
            item = StackItem(self.a, effects, [None, None])
            self.g.resolve(self.a, effects[0], None, item)
            if item.gate_paid:
                won += 1
        return won

    def test_coin_is_fair(self):
        won = self.flips()
        self.assertTrue(30 <= won <= 70, won)

    def test_lose_side_rides_the_other_gate(self):
        won = self.flips("lose")
        self.assertTrue(30 <= won <= 70, won)

    def test_paid_rider_runs_through_the_stack(self):
        effects = self.flip_effects()
        item = StackItem(self.a, effects, [None, None])
        self.g.stack.append(item)
        self.g.resolve_top()
        life = self.a.life
        self.assertIn(life, (20, 21))                  # exactly one of flip and payoff


class ChanceDatabase(unittest.TestCase):

    def test_cards(self):
        try:
            from mtgsim.carddb import CardDB
            from mtgsim.coverage import FULL, card_coverage
            db = CardDB()
        except Exception:
            self.skipTest("card database not built")
        if db._all is None:
            self.skipTest("card database not built")
        for name in ("Lash Out", "Release the Ants", "Oaken Brawler", "Mana Crypt",
                     "Tavern Swindler", "The Gold Saucer", "Stitch in Time"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()

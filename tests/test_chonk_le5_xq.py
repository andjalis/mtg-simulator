"""le-chonk-5 engine batch: new "where X is ..." quantities and the tap gate.

CostsMixin.x_quantity learns four specs (the cards-side _xq strips are queued for the
parser batch; these tests drive the evaluator and the gate directly):

- ("sac_plus", n, stat) — "mana value equal to 1 plus the sacrificed artifact's mana value"
  (Oswald Fiddlebender, Enigmatic Incarnation, Broadside Bombardiers), reading the same
  gate/spell/ability stats as ("sac", stat)
- ("arith", a, op, b) — "3 minus the number of cards in their hand" (Rackling) and
  "the number of cards in their hand minus 4" (Iron Maiden); each side is a number or
  another quantity, and "their ..." evaluates for the trigger's context player
- ("tap", stat) — "that creature's mana value" after the ("tap", "creature") gate
  (Energy Tap) taps an untapped creature and records its stats
- ("revealed", "mana value") — "You lose life equal to its mana value" (Dark Confidant);
  the recording line in effects.dig is queued for the foundation queue (it needs
  self.resolving_item there), so this spec reads item.revealed_cmc.
"""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import Effect
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, card

ENGINE5 = card("Test Engine", "{5}", "Artifact Creature — Golem", "", 5, 5)


class XQuantityTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def item(self, p=None, source=None, context=None):
        return StackItem(p or self.a, [], [], source=source, context=context)

    # ------------------------------------------------------------- sac_plus
    def test_sac_plus_reads_gate_stats(self):
        item = self.item()
        item.gate_sac_stats = (2, 2, 5)
        self.assertEqual(self.game.x_quantity(self.a, ("sac_plus", 1, "mana value"), item, None), 6)
        self.assertEqual(self.game.x_quantity(self.a, ("sac_plus", 2, "power"), item, None), 4)

    def test_sac_plus_reads_last_sacrificed(self):
        src = self.perm(BEAR, self.a)
        src.last_sacrificed = (2, 2, 2)
        item = self.item(source=src)
        self.assertEqual(self.game.x_quantity(self.a, ("sac_plus", 1, "mana value"), item, None), 3)

    def test_sac_plus_without_a_sacrifice_is_just_n(self):
        self.assertEqual(self.game.x_quantity(self.a, ("sac_plus", 1, "mana value"), self.item(), None), 1)

    # --------------------------------------------------------------- arith
    def test_arith_n_minus_their_hand(self):
        # Rackling: "3 minus the number of cards in their hand", on the opponent's upkeep
        self.b.hand = [BEAR] * 2
        item = self.item(context=self.b)
        self.assertEqual(self.game.x_quantity(self.a, ("arith", 3, "-", ("hand",)), item, None), 1)

    def test_arith_floor_is_zero(self):
        self.b.hand = [BEAR] * 5
        item = self.item(context=self.b)
        self.assertEqual(self.game.x_quantity(self.a, ("arith", 3, "-", ("hand",)), item, None), 0)

    def test_arith_count_minus_n(self):
        # Iron Maiden: "the number of cards in their hand minus 4"
        self.b.hand = [BEAR] * 6
        item = self.item(context=self.b)
        self.assertEqual(self.game.x_quantity(self.a, ("arith", ("hand",), "-", 4), item, None), 2)

    def test_arith_without_a_context_player_uses_the_resolving_player(self):
        self.a.hand = [BEAR] * 1
        self.assertEqual(self.game.x_quantity(self.a, ("arith", 3, "-", ("hand",)), self.item(), None), 2)

    # ----------------------------------------------------------------- tap gate
    def test_tap_gate_taps_and_records(self):
        bear = self.perm(BEAR, self.a)
        item = self.item()
        self.assertTrue(self.game.pay_gate_cost(self.a, ("tap", "creature"), item))
        self.assertTrue(bear.tapped)
        self.assertEqual(item.gate_tap_stats, (2, 2, 2))
        self.assertEqual(self.game.x_quantity(self.a, ("tap", "mana value"), item, None), 2)

    def test_tap_gate_picks_the_highest_mana_value(self):
        engine = self.perm(ENGINE5, self.a)
        bear = self.perm(BEAR, self.a)
        item = self.item()
        self.assertTrue(self.game.pay_gate_cost(self.a, ("tap", "creature"), item))
        self.assertTrue(engine.tapped)
        self.assertFalse(bear.tapped)
        self.assertEqual(item.gate_tap_stats[2], 5)

    def test_tap_gate_needs_an_untapped_creature(self):
        bear = self.perm(BEAR, self.a)
        bear.tapped = True
        self.assertFalse(self.game.pay_gate_cost(self.a, ("tap", "creature"), self.item()))

    def test_tap_xq_without_a_gate_is_zero(self):
        self.assertEqual(self.game.x_quantity(self.a, ("tap", "mana value"), self.item(), None), 0)

    def test_energy_tap_gate_then_add_mana_resolves(self):
        # the whole Energy Tap shape: pay_gate, then add_mana with the ("tap", ...) xq
        self.perm(ENGINE5, self.a)
        item = self.item(self.a)
        self.game.resolve(self.a, Effect("pay_gate", data={"gate": ("tap", "creature")}), None, item)
        self.game.resolve(self.a, Effect("add_mana", 1, data={"colors": ["C"],
                                                              "xq": ("tap", "mana value")}), None, item)
        self.assertEqual(len(self.a.pool), 5)

    # -------------------------------------------------------------- revealed
    def test_revealed_reads_the_recorded_mana_value(self):
        item = self.item()
        item.revealed_cmc = 4
        self.assertEqual(self.game.x_quantity(self.a, ("revealed", "mana value"), item, None), 4)

    def test_revealed_without_a_recording_is_zero(self):
        self.assertEqual(self.game.x_quantity(self.a, ("revealed", "mana value"), self.item(), None), 0)
        self.assertEqual(self.game.x_quantity(self.a, ("revealed", "mana value"), None, None), 0)

"""Delayed exile/destroy continuations bound to created tokens (Stormsplitter, Old Hob)."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card


SPLITTER = card("Test Splitter", "{3}{R}", "Creature — Elemental",
                "Haste\nWhenever you cast an instant or sorcery spell, create a token that's a copy of "
                "Test Splitter. Exile that token at the beginning of the next end step.", 1, 2)
HOB = card("Test Hob", "{R}{W}", "Legendary Creature — Cat",
           "At the beginning of combat on your turn, create a 2/2 red Mutant creature token. "
           "It gains haste until end of turn. Destroy it at the beginning of the next end step.", 2, 2)
CANTRIP = card("Test Cantrip", "{R}", "Instant", "Draw a card.")
DOUBLER = card("Test Doubler", "{R}", "Enchantment",
               "If one or more tokens would be created under your control, twice that many of those tokens "
               "are created instead.")
MOURNER = card("Test Mourner", "{R}", "Enchantment", "Whenever another creature you control dies, you gain 1 life.")


class DelayedTokenActionTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 30, HeuristicAI())
        self.b = Player("b", [ISLAND] * 30, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(2), log=True)
        self.game.turn = 1
        for p in (self.a, self.b):
            p.library = [ISLAND] * 30
        for _ in range(8):
            self.game.enter_battlefield(self.a, MOUNTAIN).tapped = False

    def end(self, p):
        self.game.active_idx = self.game.players.index(p)
        self.game.step = "end_step"
        self.game.fire(p, "end_step")
        self.game.settle()

    def split(self):
        """Cast an instant with Test Splitter out; return (original, token copy)."""
        src = next((x for x in self.a.battlefield if x.card.name == SPLITTER.name and not x.card.is_token), None)
        src = src or self.game.enter_battlefield(self.a, SPLITTER)
        before = set(map(id, self.a.battlefield))
        self.a.hand.append(CANTRIP)
        self.assertTrue(self.game.cast(self.a, CANTRIP))
        self.game.settle()
        new = [x for x in self.a.battlefield if id(x) not in before]
        self.assertEqual(len(new), 1)
        self.assertTrue(new[0].card.is_token)
        return src, new[0]

    def hob(self):
        """Fire Test Hob's combat trigger; return (Hob, created tokens)."""
        src = next((x for x in self.a.battlefield if x.card.name == HOB.name), None)
        src = src or self.game.enter_battlefield(self.a, HOB)
        before = set(map(id, self.a.battlefield))
        self.game.active_idx = 0
        self.game.fire(self.a, "begin_combat")
        self.game.settle()
        return src, [x for x in self.a.battlefield if id(x) not in before]

    def steal(self, perm, to):
        perm.controller.battlefield.remove(perm)
        perm.controller = to
        to.battlefield.append(perm)

    def on_battlefield(self, perm):
        return any(perm is x for p in self.game.players for x in p.battlefield)

    # Parsing

    def test_templates_are_supported(self):
        self.assertEqual(SPLITTER.unsupported, [])
        self.assertEqual(HOB.unsupported, [])
        for text in ("Create a 1/1 red Goblin creature token. Exile it at the beginning of the next end step.",
                     "Create a 1/1 red Goblin creature token. Destroy it at the beginning of the next end step.",
                     "Create two 1/1 red Goblin creature tokens. Exile them at the beginning of the next end step.",
                     "Create two 1/1 red Goblin creature tokens. Destroy those tokens at the beginning of the "
                     "next end step.",
                     "Create a 1/1 red Goblin creature token. Exile the token at the beginning of your next "
                     "end step."):
            self.assertEqual(card("Test Brief", "{R}", "Sorcery", text).unsupported, [], text)

    def test_conditional_and_unbound_continuations_stay_unsupported(self):
        for text in (
            "Exile that token at the beginning of the next end step.",
            "Destroy it at the beginning of the next end step.",
            "Create a 1/1 red Goblin creature token. Destroy it at the beginning of the next end step "
            "if it didn't attack this turn.",
            "Create a 1/1 red Goblin creature token. Exile it at the beginning of the next end step "
            "or if it would leave the battlefield.",
            "Create a 1/1 red Goblin creature token. Draw a card. Exile it at the beginning of the next end step.",
            "Create a 1/1 red Goblin creature token. If you control a Bird, destroy it at the beginning of the "
            "next end step.",
            "Destroy target creature. Exile it at the beginning of the next end step.",
        ):
            self.assertTrue(card("Test Unknown", "{R}", "Sorcery", text).unsupported, text)

    # Stormsplitter: exile that token

    def test_splitter_copy_has_haste_and_is_exiled_on_either_turn(self):
        for active in (0, 1):
            with self.subTest(active=active):
                self.setUp()
                src, token = self.split()
                self.assertTrue(token.has("haste"))
                self.end(self.game.players[active])
                self.assertFalse(self.on_battlefield(token))
                self.assertIn(src, self.a.battlefield)
                self.assertEqual(self.game.delayed, [])
                # Tokens cease to exist; nothing is left in exile or the graveyard.
                self.assertEqual([c for c in self.a.exile + self.a.graveyard if c.is_token], [])

    def test_exile_ignores_indestructible_and_dies_triggers(self):
        self.game.enter_battlefield(self.a, MOURNER)
        _, token = self.split()
        token.temp_kw.add("indestructible")
        life = self.a.life
        self.end(self.b)
        self.assertFalse(self.on_battlefield(token))
        self.assertEqual(self.a.life, life)

    def test_exile_follows_stolen_token(self):
        _, token = self.split()
        self.steal(token, self.b)
        self.end(self.b)
        self.assertFalse(self.on_battlefield(token))
        self.assertEqual(self.game.delayed, [])

    def test_each_copy_is_tracked_and_exiled_once(self):
        self.split()
        # The first copy has the same trigger, so the second spell makes two more copies.
        self.a.hand.append(CANTRIP)
        self.assertTrue(self.game.cast(self.a, CANTRIP))
        self.game.settle()
        tokens = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual(len(tokens), 3)
        self.assertEqual(len(self.game.delayed), 3)
        self.game.active_idx = 0
        self.game.fire(self.a, "end_step")
        self.game.flush_triggers()
        self.assertEqual(len(self.game.stack), 3)
        self.game.settle()
        self.assertFalse(any(self.on_battlefield(t) for t in tokens))
        self.assertEqual(self.game.delayed, [])
        self.end(self.b)
        self.assertEqual(self.game.stack, [])

    def test_exile_survives_source_departure_and_queues_once(self):
        src, token = self.split()
        self.game.destroy(src)
        self.game.fire(self.b, "end_step")
        self.game.flush_triggers()
        self.assertEqual(len(self.game.stack), 1)
        self.assertEqual(self.game.delayed, [])
        self.game.resolve_top()
        self.assertFalse(self.on_battlefield(token))
        self.end(self.a)
        self.assertEqual(self.game.stack, [])

    def test_exile_does_not_follow_a_new_object(self):
        src, token = self.split()
        self.game.leave_battlefield(token, "hand")
        new = self.game.enter_battlefield(self.a, token.card)
        self.end(self.a)
        self.assertIn(new, self.a.battlefield)
        self.assertIn(src, self.a.battlefield)

    def test_your_next_end_step_exile_follows_stolen_token_on_owners_turn(self):
        mine = card("Test My Exile", "{R}", "Sorcery",
                    "Create a 1/1 red Goblin creature token. Exile it at the beginning of your next end step.")
        self.a.hand.append(mine)
        self.assertTrue(self.game.cast(self.a, mine))
        self.game.settle()
        (token,) = [x for x in self.a.creatures if x.card.is_token]
        self.steal(token, self.b)
        self.end(self.b)    # the thief's end step is not the caster's
        self.assertIn(token, self.b.battlefield)
        self.end(self.a)
        self.assertFalse(self.on_battlefield(token))
        self.assertEqual(self.game.delayed, [])

    def test_copy_created_during_end_step_waits_for_next_end_step(self):
        self.end(self.a)
        _, token = self.split()
        self.assertTrue(self.on_battlefield(token))
        self.end(self.b)
        self.assertFalse(self.on_battlefield(token))

    # Old Hob: destroy it

    def test_hob_token_has_haste_and_is_destroyed_on_either_turn(self):
        for active in (0, 1):
            with self.subTest(active=active):
                self.setUp()
                hob, tokens = self.hob()
                self.assertEqual(len(tokens), 1)
                self.assertTrue(tokens[0].has("haste"))
                self.end(self.game.players[active])
                self.assertFalse(self.on_battlefield(tokens[0]))
                self.assertIn(hob, self.a.battlefield)
                self.assertEqual(self.game.delayed, [])

    def test_destroy_fires_dies_triggers(self):
        self.game.enter_battlefield(self.a, MOURNER)
        _, (token,) = self.hob()
        life = self.a.life
        self.end(self.a)
        self.assertFalse(self.on_battlefield(token))
        self.assertEqual(self.a.life, life + 1)

    def test_indestructible_token_survives_and_is_not_retried(self):
        _, (token,) = self.hob()
        token.perm_kw.add("indestructible")
        self.end(self.a)
        self.assertIn(token, self.a.battlefield)
        self.assertEqual(self.game.delayed, [])
        token.perm_kw.discard("indestructible")
        self.end(self.b)
        self.end(self.a)
        self.assertIn(token, self.a.battlefield)

    def test_destroy_follows_stolen_token(self):
        _, (token,) = self.hob()
        self.steal(token, self.b)
        self.end(self.b)
        self.assertFalse(self.on_battlefield(token))
        self.assertEqual(self.game.delayed, [])

    def test_destroy_survives_source_departure_and_queues_once(self):
        hob, (token,) = self.hob()
        self.game.destroy(hob)
        self.game.fire(self.b, "end_step")
        self.game.flush_triggers()
        self.assertEqual(len(self.game.stack), 1)
        self.assertEqual(self.game.delayed, [])
        self.game.resolve_top()
        self.assertFalse(self.on_battlefield(token))
        self.end(self.a)
        self.assertEqual(self.game.stack, [])

    def test_destroy_does_not_follow_a_new_object(self):
        _, (token,) = self.hob()
        self.game.leave_battlefield(token, "hand")
        new = self.game.enter_battlefield(self.a, token.card)
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.end(self.a)
        self.assertIn(new, self.a.battlefield)
        self.assertIn(bear, self.a.battlefield)

    def test_each_doubled_token_is_destroyed(self):
        self.game.enter_battlefield(self.a, DOUBLER)
        _, tokens = self.hob()
        self.assertEqual(len(tokens), 2)
        self.end(self.a)
        self.assertFalse(any(self.on_battlefield(t) for t in tokens))
        self.assertEqual(self.game.delayed, [])

    def test_two_combats_each_token_destroyed_at_its_own_end_step(self):
        _, (first,) = self.hob()
        self.end(self.a)
        _, (second,) = self.hob()
        self.assertFalse(self.on_battlefield(first))
        self.assertIn(second, self.a.battlefield)
        self.end(self.a)
        self.assertFalse(self.on_battlefield(second))

    def test_stale_token_after_trigger_queued_does_nothing(self):
        _, (token,) = self.hob()
        self.game.active_idx = 0
        self.game.fire(self.a, "end_step")
        self.game.flush_triggers()
        self.assertEqual(len(self.game.stack), 1)
        self.game.leave_battlefield(token, "hand")
        new = self.game.enter_battlefield(self.a, token.card)
        self.game.settle()
        self.assertIn(new, self.a.battlefield)
        self.assertEqual(self.game.delayed, [])

    def test_multiple_continuations_each_bind_and_run_once(self):
        both = card("Test Both", "{R}", "Sorcery",
                    "Create a 1/1 red Goblin creature token. It gains haste until end of turn. "
                    "Destroy it at the beginning of the next end step. "
                    "Exile it at the beginning of your next end step.")
        self.assertEqual(both.unsupported, [])
        self.a.hand.append(both)
        self.assertTrue(self.game.cast(self.a, both))
        self.game.settle()
        (token,) = [x for x in self.a.creatures if x.card.is_token]
        self.assertTrue(token.has("haste"))
        self.assertEqual(len(self.game.delayed), 2)
        token.temp_kw.add("indestructible")
        self.end(self.b)    # destroy fails; "your" exile waits for a's end step
        self.assertIn(token, self.a.battlefield)
        self.assertEqual(len(self.game.delayed), 1)
        self.end(self.a)
        self.assertFalse(self.on_battlefield(token))
        self.assertEqual(self.game.delayed, [])

    def test_entries_are_pruned_when_the_bound_token_leaves(self):
        for how in ("graveyard", "hand", "exile"):
            for maker in ("hob", "split"):
                with self.subTest(how=how, maker=maker):
                    self.setUp()
                    _, token = self.split() if maker == "split" else (None, self.hob()[1][0])
                    self.assertEqual(len(self.game.delayed), 1)
                    self.game.leave_battlefield(token, how)
                    self.assertEqual(self.game.delayed, [])
                    self.end(self.a)
                    self.assertEqual(self.game.stack, [])

    def test_prune_keeps_other_entries_in_order_and_one_time_semantics(self):
        _, (first,) = self.hob()
        _, (second,) = self.hob()
        _, (third,) = self.hob()
        self.assertEqual([e.context for e in self.game.delayed], [first, second, third])
        self.game.leave_battlefield(second, "graveyard")
        self.assertEqual([e.context for e in self.game.delayed], [first, third])
        self.end(self.a)
        self.assertFalse(self.on_battlefield(first) or self.on_battlefield(third))
        self.assertEqual((self.game.delayed, self.game.stack), ([], []))

    def test_prune_keeps_both_continuations_of_a_surviving_token(self):
        both = card("Test Both", "{R}", "Sorcery",
                    "Create a 1/1 red Goblin creature token. Destroy it at the beginning of the next end step. "
                    "Exile it at the beginning of your next end step.")
        self.a.hand.append(both)
        self.assertTrue(self.game.cast(self.a, both))
        self.game.settle()
        _, (other,) = self.hob()
        (token,) = [x for x in self.a.creatures if x.card.is_token and x is not other]
        self.game.leave_battlefield(other, "graveyard")
        self.assertEqual([e.context for e in self.game.delayed], [token, token])

    def test_blink_return_entries_are_not_pruned(self):
        flicker = card("Test Flicker", "{R}", "Instant",
                       "Exile target creature you control. Return it to the battlefield under its owner's "
                       "control at the beginning of the next end step.")
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.a.hand.append(flicker)
        self.assertTrue(self.game.cast(self.a, flicker, [bear]))
        self.game.settle()
        self.assertEqual(len(self.game.delayed), 1)
        self.end(self.a)
        self.assertEqual([x.card for x in self.a.creatures], [BEAR])

    def test_actual_turn_creates_and_destroys_hob_token(self):
        self.game.enter_battlefield(self.a, HOB)
        with patch.object(self.a.ai, "main_phase"), patch.object(self.a.ai, "choose_attackers", return_value=[]):
            self.game.take_turn(self.a)
        self.assertEqual([x.card.name for x in self.a.creatures], [HOB.name])
        self.assertEqual(self.game.delayed, [])


class RealCardTests(unittest.TestCase):
    def test_stormsplitter_and_old_hob(self):
        db = CardDB(offline=True)
        if db._all is None:
            self.skipTest("card DB absent")
        try:
            self.assertEqual(db.get("Stormsplitter").unsupported, [])
            hob = db.get("Old Hob, Alleycat Blues")
            self.assertEqual(hob.unsupported, [])
            self.assertTrue(any("next end step" in u for u in db.get("Nettling Imp").unsupported))
        finally:
            db._all.close()


if __name__ == "__main__":
    unittest.main()

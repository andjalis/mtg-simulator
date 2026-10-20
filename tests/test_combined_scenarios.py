"""Integration scenarios: delayed token exile/destroy, mixed Equip costs and flashback-grant targets.

Each scenario crosses at least two of the three mechanics, includes a priority response where one
fits, and checks exact objects (``is``) rather than names, because tokens and deck copies share
CardDefs.
"""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player
from tests.test_templates import BEAR, DRAGON3, ISLAND, MOUNTAIN, card

GRANT = "Target instant or sorcery card in your graveyard gains flashback until end of turn. " \
        "The flashback cost is equal to its mana cost."
REPLAY = card("Test Replay", "{R}", "Instant", GRANT)
LICH = card("Test Replay Lich", "{R}", "Creature — Zombie", "{T}: " + GRANT, 1, 1)
DOOM = card("Test Doomed Goblin", "{R}", "Sorcery",
            "Create a 1/1 red Goblin creature token. It gains haste until end of turn. "
            "Destroy it at the beginning of the next end step.")
FADE = card("Test Fading Goblin", "{R}", "Sorcery",
            "Create a 1/1 red Goblin creature token. Exile it at the beginning of the next end step.")
SPLITTER = card("Test Splitter", "{3}{R}", "Creature — Elemental",
                "Haste\nWhenever you cast an instant or sorcery spell, create a token that's a copy of "
                "Test Splitter. Exile that token at the beginning of the next end step.", 1, 2)
BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")
MIXED = card("Test Mixed Blade", "{1}", "Artifact — Equipment",
             "Equipped creature gets +1/+1.\nEquip—{1}{R}, Sacrifice a creature.")
CHOICE = card("Test Choice Blade", "{1}", "Artifact — Equipment",
              "Equipped creature gets +1/+1.\nEquip {3}\nEquip—Sacrifice a creature.")
MOURNER = card("Test Mourner", "{R}", "Enchantment", "Whenever another creature you control dies, you gain 1 life.")
BOUNCE = card("Test Bounce", "{0}", "Instant", "Return target creature to its owner's hand.")
GRAVE_EXILE = card("Test Grave Robber", "{0}", "Instant", "Exile target card from an opponent's graveyard.")


class CombinedScenarios(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 30, HeuristicAI())
        self.b = Player("b", [ISLAND] * 30, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 1, "main1", 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 30
        self.seen = []

    # ------------------------------------------------------------------ helpers
    def perm(self, c, p=None):
        p = self.a if p is None else p
        x = Permanent(c, p)
        x.sick = False
        p.battlefield.append(x)
        return x

    def lands(self, n):
        return [self.perm(MOUNTAIN) for _ in range(n)]

    def everywhere(self, perm):
        return any(perm is x for p in self.game.players for x in p.battlefield)

    def new_permanents(self, before):
        return [x for x in self.a.battlefield if id(x) not in before]

    def cast_new(self, c, targets=None):
        """Cast c (from hand or a flashback option) and return the permanents it created."""
        before = set(map(id, self.a.battlefield))
        self.assertTrue(self.game.cast(self.a, c, targets))
        self.game.settle()
        return self.new_permanents(before)

    def token_from(self, maker):
        self.lands(1)
        self.a.hand.append(maker)
        (token,) = self.cast_new(maker)
        self.assertTrue(token.card.is_token)
        return token

    def options(self, c):
        return [o for o in self.game.spell_options(self.a) if o.name.startswith(c.name + " (")]

    def end(self, p):
        self.game.active_idx = self.game.players.index(p)
        self.game.step = "end_step"
        self.game.fire(p, "end_step")
        self.game.settle()

    def respond_once(self, response, when):
        """b answers the first stack item matching ``when`` with ``response(item)``."""
        def respond(game, me):
            if game.stack and not self.seen and when(game.stack[-1]):
                self.seen.append(game.stack[-1])
                return response(game.stack[-1])
            return None
        self.b.ai.respond = respond

    def bounce(self, target):
        def answer(item):
            self.b.hand.append(BOUNCE)
            return BOUNCE, [target]
        return answer

    @staticmethod
    def is_equip(item):
        return any(e.kind == "equip" for e in item.effects)

    def test_fixtures_are_fully_supported(self):
        for c in (REPLAY, LICH, DOOM, FADE, SPLITTER, MIXED, CHOICE):
            self.assertEqual(c.unsupported, [], c.name)

    # ------------------------------------------- delayed token x mixed Equip cost
    def test_doomed_token_paid_as_mixed_equip_cost_leaves_a_no_op_delayed_trigger(self):
        self.game.enter_battlefield(self.a, MOURNER)
        token = self.token_from(DOOM)
        eq, host, bear = self.perm(MIXED), self.perm(DRAGON3), self.perm(BEAR)
        self.assertEqual(len(self.game.delayed), 1)
        self.assertIs(self.game.delayed[0].context, token)
        life = self.a.life
        mana = self.lands(2)
        self.assertTrue(self.game.equip(self.a, eq, host, sacrifice=token))
        self.assertTrue(all(x.tapped for x in mana))
        self.assertFalse(self.everywhere(token))
        self.assertEqual(self.a.life, life + 1)             # the sacrifice is a death
        self.assertIs(eq.attached_to, host)
        self.end(self.b)
        # The bound object is gone: the trigger must not pick another creature.
        for x in (eq, host, bear):
            self.assertIn(x, self.a.battlefield)
        self.assertIs(eq.attached_to, host)
        self.assertEqual((self.a.life, self.game.delayed), (life + 1, []))
        self.assertEqual([c for c in self.a.graveyard + self.a.exile if c.is_token], [])
        self.end(self.a)
        self.assertEqual(self.game.stack, [])

    def test_equipped_doomed_token_leaves_the_equipment_unattached(self):
        for maker in (DOOM, FADE):
            with self.subTest(maker=maker.name):
                self.setUp()
                token = self.token_from(maker)
                eq, bear = self.perm(CHOICE), self.perm(BEAR)
                self.lands(3)
                self.assertTrue(self.game.equip(self.a, eq, token, ability=0))
                self.assertIs(eq.attached_to, token)
                self.assertEqual((token.power, token.toughness), (2, 2))
                self.end(self.b)
                self.assertFalse(self.everywhere(token))
                self.assertIn(eq, self.a.battlefield)
                self.assertIsNone(eq.attached_to)
                self.assertIn(bear, self.a.battlefield)
                self.assertEqual(self.game.delayed, [])

    def test_sacrifice_ability_on_doomed_token_then_response_bounces_it(self):
        token = self.token_from(DOOM)
        eq, bear = self.perm(CHOICE), self.perm(BEAR)
        self.respond_once(self.bounce(token), self.is_equip)
        self.assertTrue(self.game.equip(self.a, eq, token, ability=1))
        self.assertTrue(self.seen)
        self.assertNotIn(bear, self.a.battlefield)          # cost stays paid
        self.assertIn(BEAR, self.a.graveyard)
        self.assertFalse(self.everywhere(token))
        self.assertEqual([c for c in self.a.hand if c.is_token], [])   # a bounced token ceases to exist
        self.assertIsNone(eq.attached_to)
        self.assertEqual(len(self.game.delayed), 1)
        self.end(self.a)
        self.assertEqual((self.game.delayed, self.game.stack), ([], []))
        self.assertIn(eq, self.a.battlefield)

    def test_doomed_token_cannot_pay_for_equipping_itself_twice(self):
        token = self.token_from(DOOM)
        eq = self.perm(MIXED)
        self.lands(2)
        # Sacrificing the target itself is legal; the ability then has no target.
        self.assertTrue(self.game.equip(self.a, eq, token, sacrifice=token))
        self.assertFalse(self.everywhere(token))
        self.assertIsNone(eq.attached_to)
        self.end(self.a)
        self.assertEqual(self.game.delayed, [])
        self.assertIn(eq, self.a.battlefield)

    # --------------------------------------- flashback grant x delayed token
    def test_flashback_granted_token_maker_binds_a_new_token(self):
        self.a.graveyard.append(FADE)
        first = self.token_from(FADE)            # a second copy cast from hand
        self.assertEqual(self.a.graveyard, [FADE, FADE])
        self.lands(1)
        self.a.hand.append(REPLAY)
        target = self.game.legal_targets(self.a, REPLAY.spell_effects[0])[1]
        self.assertTrue(self.game.cast(self.a, REPLAY, [target]))
        (option,) = self.options(FADE)
        self.lands(1)
        (second,) = self.cast_new(option)
        self.assertIsNot(second, first)
        self.assertEqual([d.context for d in self.game.delayed], [first, second])
        self.assertEqual((self.a.graveyard.count(FADE), self.a.exile.count(FADE)), (1, 1))
        self.end(self.b)
        self.assertFalse(self.everywhere(first) or self.everywhere(second))
        self.assertEqual(self.game.delayed, [])

    def test_grant_survives_response_on_other_copy_then_token_is_equipped(self):
        self.a.graveyard.extend([DOOM, DOOM])
        self.lands(1)
        self.a.hand.append(REPLAY)
        second = self.game.legal_targets(self.a, REPLAY.spell_effects[0])[1]

        def exile_other(item):    # the robber takes the first copy, not the targeted one
            self.b.hand.append(GRAVE_EXILE)
            return GRAVE_EXILE, [self.a.graveyard[0]]
        self.respond_once(exile_other, lambda item: item.card is REPLAY)
        self.assertTrue(self.game.cast(self.a, REPLAY, [second]))
        self.assertTrue(self.seen)
        self.assertEqual([c for c in self.a.graveyard if c is DOOM], [DOOM])
        (option,) = self.options(DOOM)
        self.lands(1)
        (token,) = self.cast_new(option)
        self.assertTrue(token.has("haste"))
        eq, bear = self.perm(MIXED), self.perm(BEAR)
        self.lands(2)
        self.assertTrue(self.game.equip(self.a, eq, token, sacrifice=bear))
        self.assertIs(eq.attached_to, token)
        self.end(self.a)
        self.assertFalse(self.everywhere(token))
        self.assertIsNone(eq.attached_to)
        self.assertEqual(([c for c in self.a.graveyard if c is not REPLAY], self.game.delayed), ([BEAR], []))

    def test_grant_source_sacrificed_for_equip_keeps_the_grant(self):
        self.a.graveyard.append(DOOM)
        lich = self.perm(LICH)
        self.respond_once(self.bounce(lich), lambda item: item.source is lich)
        self.assertTrue(self.game.activate_ability(self.a, lich, 0, [DOOM]))
        self.assertTrue(self.seen)
        self.assertIn(LICH, self.a.hand)                    # source gone; the ability still resolved
        (option,) = self.options(DOOM)
        self.lands(1)
        (token,) = self.cast_new(option)
        eq, host = self.perm(MIXED), self.perm(DRAGON3)
        self.lands(2)
        self.assertTrue(self.game.equip(self.a, eq, host, sacrifice=token))
        self.assertIs(eq.attached_to, host)
        self.assertEqual(list(self.a.exile), [DOOM])
        self.end(self.a)
        self.assertIn(host, self.a.battlefield)
        self.assertEqual(self.game.delayed, [])

    # --------------------------------------------- all three mechanics at once
    def test_flashback_bolt_splits_copy_that_pays_mixed_equip(self):
        splitter = self.perm(SPLITTER)
        self.a.graveyard.append(BOLT)
        self.lands(1)
        self.a.hand.append(REPLAY)
        (copy1,) = self.cast_new(REPLAY)                    # REPLAY is an instant: Splitter triggers
        (option,) = self.options(BOLT)
        foe = self.perm(BEAR, self.b)
        self.respond_once(self.bounce(splitter), lambda item: item.card is None and item.source is splitter)
        self.lands(1)
        # Both the original and copy1 trigger on the flashback cast.
        copy2, copy3 = self.cast_new(option, [foe])
        self.assertTrue(self.seen)                          # the copy trigger resolves after its source left
        self.assertNotIn(splitter, self.a.battlefield)
        self.assertNotIn(foe, self.b.battlefield)
        self.assertEqual(list(self.a.exile), [BOLT])
        self.assertEqual([id(d.context) for d in self.game.delayed], [id(copy1), id(copy2), id(copy3)])
        self.game.active_idx, self.game.step = 0, "main2"
        eq = self.perm(MIXED)
        self.lands(2)
        self.assertTrue(self.game.equip(self.a, eq, copy1, sacrifice=copy2))
        self.assertIs(eq.attached_to, copy1)
        self.end(self.b)
        self.assertFalse(any(self.everywhere(x) for x in (copy1, copy2, copy3)))
        self.assertIn(eq, self.a.battlefield)
        self.assertIsNone(eq.attached_to)
        self.assertEqual((self.game.delayed, self.game.stack), ([], []))

    # ---------------------------------------------------------- reproducibility
    def scripted_events(self):
        self.setUp()
        self.test_flashback_bolt_splits_copy_that_pays_mixed_equip()
        return list(self.game.events)

    def test_scripted_scenario_is_reproducible(self):
        self.assertEqual(self.scripted_events(), self.scripted_events())

    def test_bounded_ai_games_are_reproducible(self):
        deck = [MOUNTAIN] * 16 + [DOOM, FADE, REPLAY, BOLT, MIXED, CHOICE, BEAR, LICH] * 3

        def run(seed):
            a, b = Player("a", list(deck), HeuristicAI()), Player("b", list(deck), HeuristicAI())
            g = Game(a, b, random.Random(seed), max_turns=12, log=True)
            winner = g.play()
            return (winner.name if winner else None, a.life, b.life, g.turn, list(g.events))

        events = []
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                first = run(seed)
                self.assertLessEqual(first[3], 12)
                self.assertEqual(first, run(seed))
                events += first[4]
        # The seeds actually reach all three mechanics (the Equip policy no longer
        # sacrifices a body for these decks' modest equipment, so "sacrifices" is not required).
        for word in ("equip", "flashback", "delayed"):
            self.assertTrue(any(word in e for e in events), word)


if __name__ == "__main__":
    unittest.main()

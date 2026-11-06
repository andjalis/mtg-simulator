"""New trigger events (cx_trig_events) and the per-blocker 'becomes blocked by a creature' event, on real cards."""
import os
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import BEAR, Scripted

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None


@unittest.skipUnless(HAVE_DB, "card database not built")
class EventTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [BEAR] * 10

    def put(self, name, who=None):
        return self.game.enter_battlefield(who or self.a, DB.get(name))

    def test_cards_parse(self):
        for n in ("Dimir Spybug", "Chandra's Spitfire", "Master of Barbs", "Tavern Scoundrel", "Lurking Chupacabra",
                  "Wildgrowth Walker", "Vengeful Warchief", "Wax-Wane Witness"):
            self.assertEqual(DB.get(n).unsupported, [], n)

    def test_surveil(self):
        bug = self.put("Dimir Spybug")
        from mtgsim.cards import Effect
        self.game.resolve(self.a, Effect("surveil", 1), None)
        self.game.settle()
        self.assertEqual(bug.p1, 1)

    def test_noncombat_damage_to_opponent_only(self):
        spit = self.put("Chandra's Spitfire")
        base = spit.power
        self.game.deal_damage(self.a, 1, cause="x")              # damage to its own controller: no trigger
        self.game.settle()
        self.assertEqual(spit.power, base)
        self.game.deal_damage(self.b, 1, cause="x", combat=True)  # combat damage: no trigger
        self.game.settle()
        self.assertEqual(spit.power, base)
        self.game.deal_damage(self.b, 1, cause="x")
        self.game.settle()
        self.assertEqual(spit.power, base + 3)

    def test_first_life_loss_each_turn(self):
        warchief = self.put("Vengeful Warchief")
        self.game.change_life(self.a, -1, "x")
        self.game.settle()
        self.game.change_life(self.a, -1, "x")
        self.game.settle()
        self.assertEqual(warchief.p1, 1)

    def test_life_change_on_your_turn_only(self):
        wit = self.put("Wax-Wane Witness")
        base = wit.power
        self.game.change_life(self.a, 2, "x")
        self.game.settle()
        self.assertEqual(wit.power, base + 1)
        self.game.active_idx = 1
        self.game.change_life(self.a, -2, "x")
        self.game.settle()
        self.assertEqual(wit.power, base + 1)

    def test_coin_flip_win(self):
        self.put("Tavern Scoundrel")
        from mtgsim.cards import Effect
        self.game.rng = random.Random(1)
        wins = 0
        for _ in range(12):
            before = sum(1 for x in self.a.battlefield if x.card.is_token)
            self.game.resolve(self.a, Effect("flip_coin"), None, None)
            self.game.settle()
            wins += sum(1 for x in self.a.battlefield if x.card.is_token) > before
        self.assertTrue(0 < wins < 12)

    def test_explores(self):
        walker = self.put("Wildgrowth Walker")
        self.a.library = [BEAR] * 5                       # nonland on top: a +1/+1 counter for the explorer too
        from mtgsim.cards import Effect
        self.game.resolve(self.a, Effect("explore"), walker)
        self.game.settle()
        self.assertEqual(walker.p1, 2)                     # explore counter + the trigger's counter
        self.assertEqual(self.a.life, 23)

    def _combat(self, text):
        from tests.test_templates import card
        hero = card("Test Hero", "{2}", "Creature — Human", text, 1, 9)
        wall1 = card("Test Wall A", "{1}", "Creature — Wall", "", 0, 5)
        wall2 = card("Test Wall B", "{1}", "Creature — Wall", "", 0, 5)
        h = self.put("Wildgrowth Walker") if False else self.game.enter_battlefield(self.a, hero)
        h.sick = False
        w1, w2 = (self.game.enter_battlefield(self.b, c) for c in (wall1, wall2))
        self.game.settle()
        self.a.ai.attack, self.b.ai.block = [h], {h: [w1, w2]}
        life = self.a.life
        self.game.combat(self.a, self.b)
        self.game.settle()
        return self.a.life - life

    def test_blocked_by_a_creature_triggers_once_per_blocker(self):
        self.assertEqual(self._combat("Whenever ~ becomes blocked by a creature, you gain 1 life."), 2)

    def test_plain_becomes_blocked_triggers_once(self):
        self.assertEqual(self._combat("Whenever ~ becomes blocked, you gain 1 life."), 1)

    def test_blocks_or_becomes_blocked_by_a_creature(self):
        self.assertEqual(self._combat("Whenever ~ blocks or becomes blocked by a creature, you gain 1 life."), 2)

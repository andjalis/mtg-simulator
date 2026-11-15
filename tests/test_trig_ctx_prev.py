"""#507: the trigger's context is the creature the head names — the blocker for "becomes blocked by a creature"
(Grasping Giant) and the attacker for "a creature deals combat damage to you" (Hixus, Prison Warden) — so
"exile that creature until ~ leaves the battlefield" is a linked exile (oring) on target "prev".

The heads already carry the creature (combat.py fires "blocked_by" per blocker with the blocker as context;
the ev: combat-damage head's match returns the attacking creature), so the payoff phrase in linked_exile.py
is what makes these cards playable. The phrase is read only under those heads: elsewhere "that creature"
names something else (a chosen target, as in Turncoat Kunoichi) and the sentence stays ignored."""
import os
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None

WALL = card("Test Wall", "{1}{W}", "Creature — Wall", "", 0, 5)
WALL2 = card("Test Wall B", "{1}{W}", "Creature — Wall", "", 0, 5)


@unittest.skipUnless(HAVE_DB, "card database not built")
class TriggerContextPrev(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 3, "main1", 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def fight(self, attackers, blocks=None):
        self.a.ai.attack = list(attackers)
        self.b.ai.block = blocks or {}
        self.game.combat(self.a, self.b)
        self.game.settle()

    def test_grasping_giant_parses_as_oring_on_prev(self):
        trig = DB.get("Grasping Giant").triggers[0]
        self.assertEqual(trig.event, "blocked_by")
        self.assertEqual([(e.kind, e.target) for e in trig.effects], [("oring", "prev")])

    def test_hixus_parses_as_oring_on_prev_with_the_entered_gate(self):
        trig = DB.get("Hixus, Prison Warden").triggers[0]
        self.assertEqual(trig.event, "ev:combat_damage_player")
        self.assertEqual([(e.kind, e.target) for e in trig.effects], [("oring", "prev")])
        self.assertEqual(trig.effects[0].cond, 'lib:["src_entered"]')

    def test_chosen_target_wording_stays_ignored(self):
        # "choose target creature an opponent controls. Exile that creature until ~ leaves": the antecedent is
        # the chosen target, not the trigger's event object, so the phrase must not parse as "prev".
        self.assertIn("Exile that creature until ~ leaves the battlefield.", DB.get("Turncoat Kunoichi").unsupported)

    def test_blocker_is_exiled_until_the_giant_leaves(self):
        giant = self.put(self.a, DB.get("Grasping Giant"))
        wall = self.put(self.b, WALL)
        self.fight([giant], {giant: [wall]})
        self.assertNotIn(wall, self.b.battlefield)
        self.assertIn(wall.front, self.b.exile)
        self.assertEqual([c.name for c, _ in giant.exiled_cards], ["Test Wall"])
        self.game.leave_battlefield(giant, "graveyard")
        self.game.settle()
        self.assertTrue(any(x.card.name == "Test Wall" for x in self.b.battlefield))
        self.assertNotIn(wall.front, self.b.exile)

    def test_each_blocker_is_exiled(self):
        giant = self.put(self.a, DB.get("Grasping Giant"))
        w1, w2 = self.put(self.b, WALL), self.put(self.b, WALL2)
        self.fight([giant], {giant: [w1, w2]})
        self.assertNotIn(w1, self.b.battlefield)
        self.assertNotIn(w2, self.b.battlefield)
        self.assertEqual(sorted(c.name for c, _ in giant.exiled_cards), ["Test Wall", "Test Wall B"])

    def test_attacker_is_exiled_until_hixus_leaves(self):
        hixus = self.put(self.b, DB.get("Hixus, Prison Warden"))    # entered this turn (turn 3)
        bear = self.put(self.a, BEAR)
        self.fight([bear])
        self.assertNotIn(bear, self.a.battlefield)
        self.assertIn(bear.front, self.a.exile)
        self.assertEqual([c.name for c, _ in hixus.exiled_cards], ["Grizzly Bears"])
        self.game.leave_battlefield(hixus, "graveyard")
        self.game.settle()
        self.assertTrue(any(x.card.name == "Grizzly Bears" for x in self.a.battlefield))
        self.assertNotIn(bear.front, self.a.exile)

    def test_hixus_gate_closed_when_it_did_not_enter_this_turn(self):
        hixus = self.put(self.b, DB.get("Hixus, Prison Warden"))
        hixus.entered_turn = 1
        bear = self.put(self.a, BEAR)
        self.fight([bear])
        self.assertIn(bear, self.a.battlefield)
        self.assertEqual(hixus.exiled_cards, [])


if __name__ == "__main__":
    unittest.main()

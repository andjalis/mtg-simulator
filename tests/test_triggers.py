"""New trigger events: beginning of combat, second draw / second spell each turn, mana value N or greater,
"enters or dies". Card text is written out."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, SHOCK, card

DRILL = card("Drill Sergeant", "{1}{W}", "Creature — Human", (
    "At the beginning of combat on your turn, put a +1/+1 counter on ~."), 1, 1)
SECOND = card("Quick Study", "{1}{U}", "Creature — Wizard", (
    "Whenever you draw your second card each turn, put a +1/+1 counter on ~."), 1, 1)
CASTER = card("Spell Student", "{1}{R}", "Creature — Wizard", (
    "Whenever you cast your second spell each turn, put a +1/+1 counter on ~."), 1, 1)
BIGCAST = card("Big Spender", "{2}{R}", "Creature — Wizard", (
    "Whenever you cast a spell with mana value 3 or greater, put a +1/+1 counter on ~."), 1, 1)
MOUNT = card("Test Mount", "{2}{R}", "Creature — Mount", (
    "Whenever ~ attacks while saddled, put a +1/+1 counter on it.\nSaddle 1"), 2, 2)
TAPPER = card("Tap Gainer", "{1}{W}", "Creature — Human", "Whenever ~ becomes tapped, you gain 1 life.", 1, 1)
SPENDER = card("Big Spender Two", "{1}{G}", "Creature — Elf", "Whenever you expend 4, ~ gets +1/+1 until end of turn.", 1, 1)
MOURNER = card("Grim Mourner", "{1}{B}", "Creature — Vampire", (
    "Whenever a creature you control dies, put a +1/+1 counter on ~."), 1, 1)
WATCHER = card("Ench Watcher", "{1}{W}", "Creature — Spirit", (
    "Whenever an enchantment you control is put into a graveyard from the battlefield, put a +1/+1 counter on ~."), 1, 1)
RUNE = card("Test Rune", "{1}{W}", "Enchantment", "You gain 1 life.")
DESCENDER = card("Cave Delver", "{1}{B}", "Creature — Human", (
    "At the beginning of your end step, if you descended this turn, put a +1/+1 counter on ~."), 1, 1)
BOTH = card("Twice Blessed", "{2}{W}", "Creature — Angel", "When ~ enters or dies, you gain 2 life.", 2, 2)


class TriggerTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c):
        p = Permanent(c, self.a)
        p.sick = False
        self.a.battlefield.append(p)
        return p

    def test_templates_match(self):
        for c in (DRILL, SECOND, CASTER, BIGCAST, BOTH, MOUNT, TAPPER, SPENDER, MOURNER, WATCHER, DESCENDER):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])

    def test_beginning_of_combat(self):
        d = self.perm(DRILL)
        self.game.combat(self.a, self.b)
        self.assertEqual(d.counters.get("+1/+1"), 1)

    def test_second_draw_each_turn(self):
        s = self.perm(SECOND)
        self.game.draw(self.a)
        self.game.settle()
        self.assertFalse(s.counters)
        self.game.draw(self.a)
        self.game.settle()
        self.assertEqual(s.counters.get("+1/+1"), 1)
        self.game.draw(self.a)
        self.game.settle()
        self.assertEqual(s.counters.get("+1/+1"), 1)

    def test_second_spell_each_turn(self):
        s = self.perm(CASTER)
        for _ in range(3):
            self.perm(ISLAND)
        self.a.hand = [SHOCK, SHOCK]
        for _ in range(2):
            self.perm(card("Mountain", "", "Basic Land — Mountain", "{T}: Add {R}."))
        self.game.cast(self.a, SHOCK, [self.b])
        self.assertFalse(s.counters)
        self.game.cast(self.a, SHOCK, [self.b])
        self.assertEqual(s.counters.get("+1/+1"), 1)

    def test_enters_or_dies(self):
        self.game.enter_battlefield(self.a, BOTH)
        self.game.settle()
        self.assertEqual(self.a.life, 22)
        perm = [x for x in self.a.battlefield if x.card is BOTH][0]
        self.game.destroy(perm)
        self.game.settle()
        self.assertEqual(self.a.life, 24)

    def test_saddle_and_attack_trigger(self):
        self.assertEqual(MOUNT.saddle, 1)
        mount = self.perm(MOUNT)
        helper = self.perm(BEAR)
        helper.sick = True
        from mtgsim.engine import before_attacks
        self.game.fire(self.a, "attacks", mount)        # not saddled: no trigger
        self.game.settle()
        self.assertFalse(mount.counters)
        before_attacks(self.game, self.a)
        self.assertTrue(mount.saddled)
        self.assertTrue(helper.tapped)
        self.game.fire(self.a, "attacks", mount)
        self.game.settle()
        self.assertEqual(mount.counters.get("+1/+1"), 1)

    def test_becomes_tapped_when_attacking(self):
        self.perm(TAPPER)
        self.game.combat(self.a, self.b)
        self.assertEqual(self.a.life, 21)

    def test_expend_four(self):
        s = self.perm(SPENDER)
        for _ in range(4):
            self.perm(ISLAND)
        self.assertIsNotNone(self.game.pay(self.a, {"generic": 3}))
        self.game.settle()
        self.assertEqual(s.pump_p, 0)
        self.assertIsNotNone(self.game.pay(self.a, {"generic": 1}))
        self.game.settle()
        self.assertEqual(s.pump_p, 1)

    def test_ally_dies(self):
        m = self.perm(MOURNER)
        bear = self.perm(BEAR)
        self.game.destroy(bear)
        self.game.settle()
        self.assertEqual(m.counters.get("+1/+1"), 1)
        self.game.destroy(m)                           # its own death is not a trigger for itself here
        self.game.settle()

    def test_permanent_to_graveyard(self):
        w = self.perm(WATCHER)
        rune = self.perm(RUNE)
        self.game.leave_battlefield(rune, "graveyard")
        self.game.settle()
        self.assertEqual(w.counters.get("+1/+1"), 1)
        bear = self.perm(BEAR)
        self.game.destroy(bear)                          # not an enchantment
        self.game.settle()
        self.assertEqual(w.counters.get("+1/+1"), 1)

    def test_descended(self):
        d = self.perm(DESCENDER)
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertFalse(d.counters)                       # nothing went to the graveyard yet
        self.a.graveyard.append(BEAR)
        self.a.graveyard.append(SHOCK)                     # an instant doesn't count
        self.assertEqual(self.a.graveyard.descents, 1)
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertEqual(d.counters.get("+1/+1"), 1)


if __name__ == "__main__":
    unittest.main()

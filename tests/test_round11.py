"""Round 11: Power-up / Exhaust, keyword counters, Renew, Braided Net locks, main-phase triggers."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

POWER = card("Test Power", "{1}{W}", "Creature — Hero", "Power-up — {4}{W}: Put two +1/+1 counters on this creature. "
             "(Activate each power-up ability only once. Reduce the cost by its mana cost if it entered this turn.)", 2, 1)
TREK = card("Test Trek", "{2}", "Artifact", "{T}: Put a +1/+1 counter on target creature or Vehicle you control. "
            "Activate only as a sorcery.")
NET = card("Test Net", "{2}", "Artifact", "{T}, Remove a net counter from ~: Tap another target nonland permanent. Its "
           "activated abilities can't be activated for as long as it remains tapped.")
RENEW = card("Test Renew", "{3}{G}", "Creature — Beast", "Renew — {2}{G}, Exile this card from your graveyard: Put a "
             "+1/+1 counter and a trample counter on target creature. Activate only as a sorcery.", 3, 3)
RAMP = card("Test Ramp", "{2}", "Enchantment", "At the beginning of your first main phase, add {R}{R}.")
SURVIVE = card("Test Survivor", "{1}{W}", "Creature — Human", "Survival — At the beginning of your second main phase, if "
               "~ is tapped, you gain 2 life.", 2, 2)
ALONE = card("Test Alone", "{2}", "Creature — Human", "Whenever a creature you control attacks alone, it gets +1/+0 and gains "
             "deathtouch until end of turn.", 1, 1)
CRIME = card("Test Crime", "{1}{B}", "Creature — Rogue", "Whenever you commit a crime, put a +1/+1 counter on ~. "
             "This ability triggers only once each turn.", 2, 2)
SPITE = card("Test Spite", "{R}", "Instant", "~ deals 2 damage to any target.")
DISCARDER = card("Test Discarder", "{1}", "Creature — Rogue", "Whenever you discard a card, ~ gets +2/+0 until end of turn.",
                 1, 1)
GATE = card("Test Gate", "{2}", "Creature — Human", "When ~ enters, you may sacrifice another creature. If you do, draw "
            "a card.", 2, 2)
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
PLAINS = card("Plains", types="Basic Land — Plains", text="({T}: Add {W}.)")


class Round11(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, who=None):
        p = Permanent(c, who or self.a)
        p.sick = False
        p.controller.battlefield.append(p)
        return p

    def test_templates(self):
        for c in (POWER, TREK, NET, RENEW, RAMP, SURVIVE):
            self.assertEqual(c.unsupported, [], c.name)

    def test_power_up_once_only(self):
        hero = self.perm(POWER)
        for _ in range(10):
            self.perm(PLAINS)
        self.assertTrue(self.game.activate(self.a, hero, "ability:0"))
        self.game.settle()
        self.assertEqual(hero.p1, 2)
        self.assertFalse(self.game.can_activate(self.a, hero, 0))

    def test_power_up_cheaper_when_it_just_entered(self):
        hero = self.perm(POWER)
        hero.entered_turn = self.game.turn
        for _ in range(2):
            self.perm(PLAINS)
        self.assertFalse(self.game.can_activate(self.a, hero, 0))      # {4}{W} less {1}{W} is {3}
        self.perm(PLAINS)
        self.assertTrue(self.game.can_activate(self.a, hero, 0))

    def test_keyword_counters_from_renew(self):
        target = self.perm(BEAR)
        for _ in range(3):
            self.perm(FOREST)
        self.a.graveyard.append(RENEW)
        opts = [c for c in self.game.spell_options(self.a) if c.name.startswith(RENEW.name)]
        self.assertTrue(opts)
        self.assertTrue(self.game.cast(self.a, opts[0], [target]))
        self.game.settle()
        self.assertEqual(target.p1, 1)
        self.assertTrue(target.has("trample"))
        self.assertIn(RENEW, self.a.exile)

    def test_braided_net_locks_activated_abilities(self):
        net = self.perm(NET)
        net.counters["net"] = 3
        hero = self.perm(POWER, self.b)
        for _ in range(10):
            self.perm(PLAINS, self.b)
        self.assertTrue(self.game.activate(self.a, net, "ability:0"))
        self.game.settle()
        self.assertTrue(hero.tapped)
        self.game.turn = 2
        self.assertFalse(self.game.can_activate(self.b, hero, 0))
        hero.tapped = False
        self.assertTrue(self.game.can_activate(self.b, hero, 0))

    def test_first_main_phase_trigger_adds_mana(self):
        self.perm(RAMP)
        self.game.fire(self.a, "main1_begin")
        self.game.settle()
        self.assertEqual(len(self.a.pool), 2)

    def test_survival_needs_a_tapped_creature(self):
        s = self.perm(SURVIVE)
        self.game.fire(self.a, "survival")
        self.game.settle()
        self.assertEqual(self.a.life, 20)
        s.tapped = True
        self.game.fire(self.a, "survival")
        self.game.settle()
        self.assertEqual(self.a.life, 22)

    def test_attacks_alone_pumps_the_attacker(self):
        self.perm(ALONE)
        bear = self.perm(BEAR)
        self.game.fire(self.a, "attacks_alone", context=bear)
        self.game.settle()
        self.assertEqual(bear.power, 3)
        self.assertTrue(bear.has("deathtouch"))

    def test_crime_when_targeting_an_opponent_once_per_turn(self):
        crim = self.perm(CRIME)
        self.perm(MOUNTAIN)
        self.perm(MOUNTAIN)
        for _ in range(2):
            self.a.hand.append(SPITE)
        self.assertTrue(self.game.cast(self.a, SPITE, [self.b]))
        self.game.settle()
        self.assertTrue(self.game.cast(self.a, SPITE, [self.b]))
        self.game.settle()
        self.assertEqual(crim.p1, 1)

    def test_discard_trigger(self):
        d = self.perm(DISCARDER)
        self.a.hand.append(BEAR)
        self.game.discard_card(self.a, BEAR)
        self.game.settle()
        self.assertEqual(d.power, 3)

    def test_sacrifice_gate_draws_when_a_token_is_spare(self):
        from mtgsim.cards import make_token
        self.a.hand = []
        token = self.game.enter_battlefield(self.a, make_token("Spirit", 1, 1))
        self.game.enter_battlefield(self.a, GATE)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)
        self.assertNotIn(token, self.a.battlefield)

    def test_sacrifice_gate_does_nothing_without_a_spare(self):
        self.a.hand = []
        self.game.enter_battlefield(self.a, GATE)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 0)


if __name__ == "__main__":
    unittest.main()

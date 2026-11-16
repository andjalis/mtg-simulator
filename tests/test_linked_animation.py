"""#316 slice: "<target> becomes a N/N artifact creature for as long as ~ remains tapped / remains on the battlefield".
The animation is continuous effects sourced from ~ and linked to the duration (cx_statics.link_effect / effect_alive):
untapping ~ ends a "remains tapped" one for good, ~ leaving the battlefield ends both."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_templates import BEAR, ISLAND, card

RELIC = card("Test Relic", "{2}", "Artifact", "")


class LinkedAnimation(unittest.TestCase):
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

    def activate(self, source, ability, target):
        effects = list(ability.effects)
        item = StackItem(self.a, effects, [target] + [None] * (len(effects) - 1), source=source, kind="ability")
        self.g.stack.append(item)
        self.g.resolve_top()

    def test_real_cards_are_full(self):
        for name in ("The Blackstaff of Waterdeep", "Skilled Animator", "Unctus's Retrofitter"):
            with self.subTest(card=name):
                self.assertEqual(self.real(name).unsupported, [])

    def test_refusals(self):
        for text in ("Target artifact you control becomes a 4/4 artifact creature for as long as you control ~.",
                     "Target artifact you control becomes a 4/4 artifact creature for as long as it has a +1/+1 "
                     "counter on it."):
            with self.subTest(text=text):
                effects, bad = _parse_effects(text)
                self.assertTrue(bad, effects)

    def test_blackstaff_lasts_while_tapped(self):
        staff = self.perm(self.real("The Blackstaff of Waterdeep"), self.a)
        relic = self.perm(RELIC, self.a)
        ability = [a for a in staff.card.activated if any(e.kind == "cx_animate" for e in a.effects)][0]
        staff.tapped = True
        self.activate(staff, ability, relic)
        self.assertTrue(relic.is_creature)
        self.assertEqual((relic.power, relic.toughness), (4, 4))
        self.g.expire_continuous_effects()               # not an end-of-turn effect
        self.assertTrue(relic.is_creature)
        staff.tapped = False
        self.assertFalse(relic.is_creature)
        staff.tapped = True                               # tapping again doesn't bring it back
        self.assertFalse(relic.is_creature)

    def test_skilled_animator_ends_when_it_leaves(self):
        relic = self.perm(RELIC, self.a)
        animator = self.real("Skilled Animator")
        self.g.rng = random.Random(0)
        source = self.perm(animator, self.a)
        trig = animator.triggers[0]
        effects = list(trig.effects)
        item = StackItem(self.a, effects, [relic] + [None] * (len(effects) - 1), source=source)
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertTrue(relic.is_creature)
        self.assertEqual((relic.power, relic.toughness), (5, 5))
        self.g.destroy(source)
        self.assertFalse(relic.is_creature)


if __name__ == "__main__":
    unittest.main()

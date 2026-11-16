"""#330 slice: "unless <payer> pays {N} for each <quantity>": the mana scales with a count read from the source
controller's side when the gate resolves (Extravagant Spirit, Megatherium, Fettergeist, Phantasmal Sphere,
Evasive Action)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class UnlessPerCount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def game(self, lands, hand=(), others=()):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [self.db.get("Island")] * 10
        for name in lands:
            g.enter_battlefield(a, self.db.get(name)).sick = False
        for name in others:
            g.enter_battlefield(a, self.db.get(name))
        a.hand = [self.db.get(n) for n in hand]
        g.settle()
        return g, a, b

    def upkeep(self, g, p):
        g.fire(p, "upkeep")
        g.settle()

    def test_parse(self):
        for name in ("Extravagant Spirit", "Megatherium", "Fettergeist", "Phantasmal Sphere", "Evasive Action"):
            self.assertEqual(self.db.get(name).unsupported, [], name)
        gate = next(e for t in self.db.get("Cyclone").triggers for e in t.effects if e.kind == "cx_unless")
        self.assertEqual(gate.data["costs"][0]["per"], ("counters", "wind"))     # not "winds"
        # "it" isn't the source when the gated effect acts on something else
        self.assertTrue(_parse_effects("Destroy target creature unless its controller pays {1} for each +1/+1 "
                                       "counter on it.")[1])
        self.assertTrue(_parse_effects("Sacrifice ~ unless you pay {1} for each blue card revealed this way.")[1])

    def test_extravagant_spirit_pays_per_card_in_hand(self):
        g, a, _ = self.game(["Island"] * 3, hand=["Island", "Island", "Island"])
        spirit = g.enter_battlefield(a, self.db.get("Extravagant Spirit"))
        self.upkeep(g, a)
        self.assertIn(spirit, a.battlefield)
        self.assertEqual(sum(x.tapped for x in a.battlefield if x.card.is_land), 3)     # three cards: {3}
        g, a, _ = self.game(["Island"] * 2, hand=["Island", "Island", "Island"])
        spirit = g.enter_battlefield(a, self.db.get("Extravagant Spirit"))
        self.upkeep(g, a)
        self.assertNotIn(spirit, a.battlefield)                              # can't pay {3}: sacrificed
        self.assertEqual(sum(x.tapped for x in a.battlefield if x.card.is_land), 0)     # no partial payment

    def test_empty_hand_costs_nothing(self):
        g, a, _ = self.game([])
        spirit = g.enter_battlefield(a, self.db.get("Extravagant Spirit"))
        self.upkeep(g, a)
        self.assertIn(spirit, a.battlefield)

    def test_megatherium_on_entering(self):
        g, a, _ = self.game(["Forest"] * 2, hand=["Island", "Island", "Island", "Island"])
        mega = g.enter_battlefield(a, self.db.get("Megatherium"))
        g.settle()
        self.assertNotIn(mega, a.battlefield)

    def test_fettergeist_counts_other_creatures(self):
        g, a, _ = self.game(["Island"] * 2, others=["Grizzly Bears", "Grizzly Bears"])
        geist = g.enter_battlefield(a, self.db.get("Fettergeist"))
        self.upkeep(g, a)
        self.assertIn(geist, a.battlefield)                                 # two others: {2}, paid
        g, a, _ = self.game(["Island"] * 2, others=["Grizzly Bears"] * 3)
        geist = g.enter_battlefield(a, self.db.get("Fettergeist"))
        self.upkeep(g, a)
        self.assertNotIn(geist, a.battlefield)

    def test_phantasmal_sphere_pays_per_counter_after_adding_one(self):
        g, a, _ = self.game(["Island"] * 2)
        sphere = g.enter_battlefield(a, self.db.get("Phantasmal Sphere"))
        sphere.counters["+1/+1"] = 1
        self.upkeep(g, a)                                                   # now 2 counters: {2}
        self.assertIn(sphere, a.battlefield)
        self.assertEqual(sphere.counters.get("+1/+1"), 2)
        self.upkeep(g, a)                                                   # lands still tapped: can't pay {3}
        self.assertNotIn(sphere, a.battlefield)

    def test_evasive_action_counts_my_domain(self):
        from mtgsim.engine import StackItem
        g, a, b = self.game(["Island", "Forest", "Swamp"])
        for _ in range(2):
            g.enter_battlefield(b, self.db.get("Mountain")).sick = False
        spell = StackItem(b, [], [], card=BEAR, name=BEAR.name)
        g.stack.append(spell)
        action = self.db.get("Evasive Action")
        item = StackItem(a, list(action.spell_effects), [None, spell],
                         card=action, name=action.name)
        g.stack.append(item)
        g.resolve_top()
        self.assertNotIn(spell, g.stack)                                    # domain 3: b can't pay {3} with 2
        g, a, b = self.game(["Island", "Forest"])
        for _ in range(2):
            g.enter_battlefield(b, self.db.get("Mountain")).sick = False
        spell = StackItem(b, [], [], card=BEAR, name=BEAR.name)
        g.stack.append(spell)
        item = StackItem(a, list(action.spell_effects), [None, spell],
                         card=action, name=action.name)
        g.stack.append(item)
        g.resolve_top()
        self.assertIn(spell, g.stack)                                       # domain 2: b pays {2}


if __name__ == "__main__":
    unittest.main()

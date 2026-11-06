"""cx_counters.py: counters on several targets at once."""
import random
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player
from mtgsim.engine.state import Permanent
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND


def effects(text):
    effs, bad = _parse_effects(text)
    assert not bad, bad
    return effs


class MultiTarget(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def put(self, p, n):
        out = []
        for _ in range(n):
            perm = Permanent(BEAR, p)
            p.battlefield.append(perm)
            out.append(perm)
        return out

    def run_effects(self, text):
        effs = effects(text)
        targets = self.game.auto_targets(self.a, effs)
        for e, t in zip(effs, targets):
            self.game.resolve(self.a, e, t)
        return targets

    def test_each_of_up_to_two_stun(self):
        bears = self.put(self.a, 3)
        self.run_effects("Put a stun counter on each of up to two target creatures.")
        self.assertEqual(sorted(b.counters.get("stun", 0) for b in bears), [0, 1, 1])

    def test_each_of_up_to_three_other_mine(self):
        bears = self.put(self.a, 2)
        self.run_effects("Put two +1/+1 counters on each of up to three other target creatures you control.")
        self.assertEqual(sum(b.counters.get("+1/+1", 0) for b in bears), 4)

    def test_fewer_targets_than_up_to(self):
        bears = self.put(self.a, 1)
        self.run_effects("Put a shield counter on each of up to two target creatures.")
        self.assertEqual(bears[0].counters.get("shield", 0), 1)


if __name__ == "__main__":
    unittest.main()


class Poison(MultiTarget):
    def test_you_get_poison(self):
        self.run_effects("You get two poison counters.")
        self.assertEqual(self.a.counters.get("poison", 0), 2)

    def test_that_player_gets_poison_in_trigger(self):
        from mtgsim.engine.state import StackItem
        eff = effects("That player gets a poison counter.")[0]
        self.assertEqual((eff.kind, eff.target), ("cx_poison", "that_player"))
        item = StackItem(self.a, [eff], [None], context=self.b)
        self.game.resolve(self.a, eff, None, item)
        self.assertEqual(self.b.counters.get("poison", 0), 1)


class EntersWithX(unittest.TestCase):
    def test_parse_and_enter(self):
        from tests.test_templates import card
        c = card("Test Gem", "{X}{2}", "Artifact", "~ enters with X gem counters on it.")
        c2 = card("Test Hydra", "{X}{G}", "Creature — Hydra", "~ enters with X +1/+1 counters on it.", 0, 0)
        self.assertEqual(c.etb_named_counters, ("gem", -1))
        self.assertEqual(c2.etb_counters, -1)
        a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
        game = Game(a, b, random.Random(0), log=True)
        game.enter_battlefield(a, c, x=3)
        self.assertEqual(a.battlefield[-1].counters["gem"], 3)


class PerCounter(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.a.library = [ISLAND] * 10

    def test_self_pump_per_counter(self):
        from tests.test_templates import card
        c = card("Test Oil", "{1}", "Creature — Golem", "This creature gets +2/+2 for each oil counter on it.", 0, 0)
        self.assertEqual((c.pt_per, c.pt_scale), ("ctr:oil", (2, 2)))
        perm = Permanent(c, self.a)
        self.a.battlefield.append(perm)
        perm.counters["oil"] = 2
        self.assertEqual((perm.power, perm.toughness), (4, 4))

    def test_equipment_per_counter(self):
        from tests.test_templates import card
        eq = card("Test Charger", "{2}", "Artifact — Equipment", "Equipped creature gets +1/+1 for each charge counter on this Equipment.\nEquip {2}")
        self.assertEqual(eq.pt_per, "ctr:charge")
        e, bear = Permanent(eq, self.a), Permanent(BEAR, self.a)
        self.a.battlefield += [e, bear]
        e.counters["charge"] = 3
        e.attached_to = bear
        bear.equipment.append(e) if e not in bear.equipment else None
        self.assertEqual(bear.power, 5)

    def test_draw_per_counter(self):
        from tests.test_templates import card
        c = card("Test Pile", "{1}", "Artifact", "{T}: Draw a card for each charge counter on this artifact.")
        perm = Permanent(c, self.a)
        self.a.battlefield.append(perm)
        perm.counters["charge"] = 2
        eff = c.activated[0].effects[0]
        item = type("I", (), {"source": perm, "card": None, "context": None})()
        before = len(self.a.hand)
        self.game.resolve(self.a, eff, None, item)
        self.assertEqual(len(self.a.hand) - before, 2)


class Distribute(MultiTarget):
    def test_distribute_over_chosen_targets(self):
        bears = self.put(self.a, 3)
        effs = effects("Distribute three +1/+1 counters among one, two, or three target creatures you control.")
        self.assertEqual(len(effs), 3)
        from mtgsim.engine.state import StackItem
        item = StackItem(self.a, effs, self.game.auto_targets(self.a, effs))
        for e, t in zip(item.effects, item.targets):
            self.game.resolve(self.a, e, t, item)
        self.assertEqual(sum(b.counters.get("+1/+1", 0) for b in bears), 3)

    def test_single_target_gets_all(self):
        bears = self.put(self.a, 1)
        effs = effects("Distribute three +1/+1 counters among up to two target creatures you control.")
        from mtgsim.engine.state import StackItem
        item = StackItem(self.a, effs, self.game.auto_targets(self.a, effs))
        for e, t in zip(item.effects, item.targets):
            self.game.resolve(self.a, e, t, item)
        self.assertEqual(bears[0].counters.get("+1/+1", 0), 3)

"""Verge-style lands: one colour needs a matching land type; Bastion-style: entered this turn or a basic."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, MOUNTAIN, card

VERGE = card("Floodfarm Verge", types="Land", text="{T}: Add {W}.\n{T}: Add {U}. Activate only if you control a Plains or an Island.")
BASTION = card("Gleaming Bastion", types="Land", text="{T}: Add {C}.\n{T}: Add {W} or {U}. Activate only if ~ entered this turn or if your control a basic land.")
ISLAND = card("Island", types="Basic Land — Island", text="{T}: Add {U}.")


class ManaGates(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"

    def perm(self, c, entered=1):
        p = Permanent(c, self.a)
        p.sick, p.entered_turn = False, entered
        self.a.battlefield.append(p)
        return p

    def colours(self, perm):
        return next((s.produces_now for s in self.game.mana_sources(self.a) if s is perm), set())

    def test_parses_fully(self):
        self.assertEqual(VERGE.unsupported, [])
        self.assertEqual(BASTION.unsupported, [])

    def test_verge_needs_matching_land(self):
        v = self.perm(VERGE)
        self.assertEqual(set(self.colours(v)), {"W"})
        self.perm(MOUNTAIN)
        self.assertEqual(set(self.colours(v)), {"W"})
        self.perm(ISLAND)
        self.assertEqual(set(self.colours(v)), {"W", "U"})

    def test_bastion_needs_basic_or_fresh(self):
        b = self.perm(BASTION)
        self.assertEqual(set(self.colours(b)), {"C"})
        self.perm(MOUNTAIN)
        self.assertEqual(set(self.colours(b)), {"C", "W", "U"})

    def test_bastion_fresh(self):
        b = self.perm(BASTION, entered=self.game.turn)
        self.assertEqual(set(self.colours(b)), {"C", "W", "U"})


if __name__ == "__main__":
    unittest.main()


class BounceAndCounterFilters(unittest.TestCase):
    def test_spell_or_permanent_bounces_a_permanent(self):
        a, b = Player("a", [BEAR] * 10, HeuristicAI()), Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 1, "main1"
        spell = card("Reverse", "{1}{U}", "Instant", "Return target spell or permanent to its owner's hand.")
        self.assertEqual(spell.unsupported, [])
        eff = spell.spell_effects[0]
        self.assertEqual((eff.kind, eff.target), ("bounce_spell", "spell_or_permanent"))
        bear = Permanent(BEAR, b)
        b.battlefield.append(bear)
        self.assertIn(bear, game.legal_targets(a, eff))
        game.counter(a, eff, bear)
        self.assertNotIn(bear, b.battlefield)
        self.assertEqual(len(b.hand), 1)

    def test_counter_by_mana_value(self):
        big = card("Disdain", "{1}{U}", "Instant", "Counter target spell with mana value 4 or greater.")
        self.assertEqual(big.unsupported, [])
        self.assertEqual(big.spell_effects[0].filter, "min_cmc:4")


class DomainQuantities(unittest.TestCase):
    def test_domain_counts_basic_land_types(self):
        a, b = Player("a", [BEAR] * 10, HeuristicAI()), Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        for c in (ISLAND, ISLAND, MOUNTAIN, VERGE):
            a.battlefield.append(Permanent(c, a))
        self.assertEqual(game.x_quantity(a, ("domain",), None, None), 2)
        self.assertEqual(game.x_quantity(a, ("named_lands",), None, None), 3)
        blast = card("Blast", "{2}{R}", "Instant", "Domain — ~ deals X damage to target tapped creature, where X is 1 plus the number of basic land types among lands you control.")
        self.assertEqual(blast.unsupported, [])


TOWN = card("Starting Town", types="Land", text="{T}: Add {C}.\n{T}, Pay 1 life: Add one mana of any color.")


class PayLifeMana(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        self.town = Permanent(TOWN, self.a)
        self.town.sick = False
        self.a.battlefield.append(self.town)

    def test_parses_fully(self):
        self.assertEqual(TOWN.unsupported, [])
        self.assertEqual(TOWN.mana_pay_life, 1)

    def test_colourless_costs_no_life_and_coloured_costs_one(self):
        life = self.a.life
        self.game.pay(self.a, {"generic": 1})
        self.assertEqual(self.a.life, life)
        self.town.tapped = False
        self.game.pay(self.a, {"R": 1})
        self.assertEqual(self.a.life, life - 1)

    def test_no_coloured_mana_at_last_life(self):
        self.a.life = 1
        self.assertEqual(set(self.colours()), {"C"})

    def colours(self):
        return next(s.produces_now for s in self.game.mana_sources(self.a) if s is self.town)


class OptionalBlight(unittest.TestCase):
    def test_blight_bonus_becomes_a_gate(self):
        hex_ = card("Requiting Hex", "{B}", "Instant", "As an additional cost to cast this spell, you may blight 1. (You may put a -1/-1 counter on a creature you control.)\nDestroy target creature with mana value 2 or less. If this spell's additional cost was paid, you gain 2 life.")
        self.assertEqual(hex_.unsupported, [])
        self.assertEqual([e.kind for e in hex_.spell_effects], ["destroy", "pay_gate", "gain_life"])


class RoundTwoTemplates(unittest.TestCase):
    def test_domain_cost_reduction(self):
        binding = card("Leyline Binding", "{5}{U}", "Enchantment", "Flash\nDomain — ~ costs {1} less to cast for each basic land type among lands you control.\nWhen ~ enters, exile target nonland permanent an opponent controls until ~ leaves the battlefield.")
        self.assertEqual(binding.cost_reduction, "domain")
        a, b = Player("a", [BEAR] * 10, HeuristicAI()), Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        before = sum(game.cost_of(a, binding).values())
        for c in (ISLAND, MOUNTAIN):
            a.battlefield.append(Permanent(c, a))
        self.assertEqual(sum(game.cost_of(a, binding).values()), before - 2)

    def test_draw_for_each_counter_on_it(self):
        walker = card("Marketback Walker", "{1}{B}", "Creature — Zombie", "When ~ dies, draw a card for each +1/+1 counter on it.", 1, 1)
        self.assertEqual(walker.unsupported, [])
        self.assertEqual(walker.triggers[0].effects[0].data["xq"], ("counters", "+1/+1"))

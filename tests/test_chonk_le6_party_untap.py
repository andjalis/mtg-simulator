"""le-chonk-6 engine batch, part 3: party counting, "choose not to untap", untap-X-lands.

- party_members()/party_size() (Coveted Prize's "costs {1} less for each creature in your
  party", Acquisitions Expert's "where X is the number of creatures in your party"), the
  ("party",) x-quantity, the "party" cost reduction and the party_counters kind
  (Squad Commander's "put a +1/+1 counter on each creature in your party")
- turns.untap_step consumes a recorded "choose not to untap" choice (perm.stay_tapped)
- the untap_lands kind ("Untap X target lands", Candelabra of Tawnos)
"""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import Activated, Effect
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_templates import BEAR, MOUNTAIN, card

CLERIC = card("Test Cleric", "{1}{W}", "Creature — Human Cleric", "", 1, 1)
ROGUE = card("Test Rogue", "{1}{B}", "Creature — Human Rogue", "", 1, 1)
WARRIOR = card("Test Warrior", "{1}{R}", "Creature — Human Warrior", "", 1, 1)
WIZARD = card("Test Wizard", "{1}{U}", "Creature — Human Wizard", "", 1, 1)
MULTI = card("Test Skulk", "{1}{B}", "Creature — Human Rogue Warrior", "", 1, 1)
CHANGLING = card("Test Changeling", "{2}", "Creature — Shapeshifter", "Changeling", 2, 2)

PRIZE = card("Test Prize", "{3}{B}", "Sorcery", "")
PRIZE.cost_reduction = "party"
PRIZE.spell_effects = [Effect("draw", 1)]

CANDELABRA = card("Test Candelabra", "{1}", "Artifact", "")
CANDELABRA.activated = [Activated(
    "ability", {"X": 1}, effects=[Effect("untap_lands", 0, data={"x": True})],
    text="{X}, {T}: Untap X target lands.", extra_costs={"tap": True})]


class Chonk6b(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        self.g.active_idx = 0
        for p in (self.a, self.b):
            p.ai.attack, p.ai.block = (), {}

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def land(self, p, n, c=MOUNTAIN):
        out = []
        for _ in range(n):
            land = Permanent(c, p)
            land.sick = False
            out.append(land)
            p.battlefield.append(land)
        return out


class Party(Chonk6b):
    def put(self, c):
        return self.perm(c, self.a)

    def test_party_counts_distinct_classes(self):
        self.put(CLERIC)
        self.put(ROGUE)
        self.put(WARRIOR)
        self.put(WIZARD)
        self.assertEqual(self.g.party_size(self.a), 4)

    def test_duplicates_do_not_add_up(self):
        self.put(CLERIC)
        self.put(CLERIC)
        self.put(CLERIC)
        self.assertEqual(self.g.party_size(self.a), 1)

    def test_a_multiclass_creature_fills_one_slot(self):
        multi = self.put(MULTI)
        self.assertEqual(self.g.party_members(self.a), [multi])
        self.put(ROGUE)          # the Rogue slot is already taken by MULTI
        self.put(WIZARD)
        self.assertEqual(self.g.party_size(self.a), 2)
        self.put(WARRIOR)        # ... but the Warrior slot is still open to another Warrior
        self.assertEqual(self.g.party_size(self.a), 3)

    def test_changeling_counts_as_a_party_member(self):
        self.put(CHANGLING)
        self.assertEqual(self.g.party_size(self.a), 1)

    def test_empty_party_is_zero(self):
        self.put(BEAR)
        self.assertEqual(self.g.party_size(self.a), 0)

    def test_party_x_quantity(self):
        item = StackItem(self.a, [], [])
        self.put(CLERIC)
        self.put(ROGUE)
        self.assertEqual(self.g.x_quantity(self.a, ("party",), item, None), 2)

    def test_party_cost_reduction(self):
        self.put(CLERIC)
        self.put(ROGUE)
        # {3}{B} less {1} per party member
        self.assertEqual(self.g.cost_of(self.a, PRIZE)["generic"], 1)

    def test_party_counters_kind(self):
        cleric, rogue, warrior, wizard = self.put(CLERIC), self.put(ROGUE), self.put(WARRIOR), self.put(WIZARD)
        bear = self.put(BEAR)
        eff = Effect("party_counters", 1)
        self.g.resolve(self.a, eff, None, StackItem(self.a, [eff], []))
        self.assertEqual([c.counters.get("+1/+1", 0) for c in (cleric, rogue, warrior, wizard)], [1, 1, 1, 1])
        self.assertEqual(bear.counters.get("+1/+1", 0), 0)


class ChooseNotToUntap(Chonk6b):
    def test_stay_tapped_keeps_the_permanent_tapped_once(self):
        land = self.land(self.a, 1)[0]
        land.tapped = True
        land.stay_tapped = True
        self.g.untap_step(self.a)
        self.assertTrue(land.tapped)
        self.assertFalse(getattr(land, "stay_tapped", False))    # consumed
        self.g.untap_step(self.a)
        self.assertFalse(land.tapped)

    def test_untap_step_untaps_everything_else(self):
        land = self.land(self.a, 2)
        bear = self.perm(BEAR, self.a)
        for x in (land[0], land[1], bear):
            x.tapped = True
        self.g.untap_step(self.a)
        self.assertFalse(any(x.tapped for x in (land[0], land[1], bear)))


class UntapXLands(Chonk6b):
    def test_untap_lands_resolves_with_a_fixed_amount(self):
        lands = self.land(self.a, 3)
        for x in lands:
            x.tapped = True
        eff = Effect("untap_lands", 2)
        self.g.resolve(self.a, eff, None, StackItem(self.a, [eff], []))
        self.assertEqual([x.tapped for x in lands], [False, False, True])

    def test_candelabra_untaps_x_lands(self):
        candelabra = self.perm(CANDELABRA, self.a)
        lands = self.land(self.a, 5)
        for x in lands[:3]:
            x.tapped = True
        # {X} paid with the two untapped Mountains: X = 2 untaps two of the three tapped lands
        self.assertTrue(self.g.can_activate(self.a, candelabra, 0, x=2))
        self.assertTrue(self.g.activate_ability(self.a, candelabra, 0, x=2))
        self.assertEqual([x.tapped for x in lands[:3]], [False, False, True])
        self.assertTrue(candelabra.tapped)


if __name__ == "__main__":
    unittest.main()

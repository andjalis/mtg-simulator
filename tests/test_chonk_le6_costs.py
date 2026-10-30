"""le-chonk-6 engine batch, part 2: exile-from-graveyard costs.

The parser templates are queued for the cards-side batch (they land once this engine
half exists), so these tests build the exact shapes the templates will emit:

- a spell's ``extra_exile_gy`` descriptor: "As an additional cost to cast ~, exile a(n)
  <desc> card from your graveyard" (Makeshift Mauler, Skaab Ruinator, Corpse Lunge) —
  gated in can_cast_now, chosen in costs.spell_plan, paid in play.cast
- an activated ability's extra_costs["exile_gy_card"] (Molten-Tail Masticore,
  Moorland Haunt, Graveyard Marshal) — gated in can_activate, chosen in
  costs.ability_plan, paid in abilities.activate_ability
- the ("exiled_gy", "power"/...) x-quantity reading the exiled card's stats
  (item.exiled_gy_stats for spells, source.last_exiled_gy for abilities)
"""
import random
import unittest

from mtgsim.cards import Activated, Effect
from mtgsim.engine import Game, Permanent, Player
from mtgsim.identity import instance
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

BIG = card("Test Giant", "{4}", "Creature — Giant", "", 4, 5)
LAND = card("Test Land", types="Land", text="{T}: Add {G}.")
SWAMP = card("Test Swamp", types="Basic Land — Swamp", text="{T}: Add {B}.")
PLAINS = card("Test Plains", types="Basic Land — Plains", text="{T}: Add {W}.")

MAULER = card("Test Mauler", "{1}{U}", "Creature — Zombie", "", 2, 3)
MAULER.extra_exile_gy = "creature card"

LUNGE = card("Test Lunge", "{1}{B}", "Sorcery", "")
LUNGE.extra_exile_gy = "creature card"
LUNGE.spell_effects = [Effect("damage", 1, target="any", data={"xq": ("exiled_gy", "power")})]

MASTICORE = card("Test Masticore", "{4}", "Artifact Creature — Masticore", "", 4, 4)
MASTICORE.activated = [Activated(
    "ability", {"R": 1}, effects=[Effect("damage", 1, target="any", data={"xq": ("exiled_gy", "power")})],
    text="{R}, Exile a creature card from your graveyard: Test Masticore deals damage "
         "equal to the exiled card's power to any target.",
    extra_costs={"exile_gy_card": "creature card"})]
HAUNT = card("Test Haunt", types="Land", text="{2}{W}, {T}, Exile a creature card from your "
             "graveyard: Create a 1/1 white Spirit creature token with flying.")
HAUNT.activated = [Activated(
    "ability", {"generic": 2, "W": 1}, effects=[Effect("token", 1, data={"name": "Spirit", "power": 1, "toughness": 1,
                          "keywords": ["flying"]})],
    text="{2}{W}, {T}, Exile a creature card from your graveyard: Create a 1/1 white Spirit.",
    extra_costs={"tap": True, "exile_gy_card": "creature card"})]


class ExileGraveyardCosts(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], None)
        self.b = Player("b", [], None)
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        self.g.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def gy_cost_card(self, c):
        """A hand instance carrying the extra_exile_gy attribute the cards-side template
        will declare on CardDef (CardInstance copies declared fields only)."""
        i = instance(c)
        i.extra_exile_gy = getattr(c, "extra_exile_gy", "")
        return i

    def land(self, p, n, c=MOUNTAIN):
        for _ in range(n):
            land = Permanent(c, p)
            land.sick = False
            p.battlefield.append(land)

    # ------------------------------------------------------------ cast costs
    def test_cast_exiles_the_cheapest_matching_graveyard_card(self):
        self.a.graveyard = [BIG, BEAR, LAND]
        mauler = self.gy_cost_card(MAULER)
        self.a.hand = [mauler]
        self.land(self.a, 3, ISLAND)
        self.assertTrue(self.g.cast(self.a, mauler))
        self.assertTrue(any(x.card.name == "Test Mauler" for x in self.a.battlefield))
        self.assertIn(BEAR, self.a.exile)          # cheapest creature card (cmc 2)
        self.assertNotIn(BEAR, self.a.graveyard)
        self.assertIn(BIG, self.a.graveyard)
        self.assertIn(LAND, self.a.graveyard)      # not a creature card

    def test_cast_is_refused_without_a_matching_graveyard_card(self):
        self.a.graveyard = [LAND, LAND]
        mauler = self.gy_cost_card(MAULER)
        self.a.hand = [mauler]
        self.land(self.a, 3, ISLAND)
        self.assertFalse(self.g.can_cast_now(self.a, mauler))
        self.assertFalse(self.g.cast(self.a, mauler))
        self.assertEqual(self.a.hand, [mauler])

    def test_cast_is_refused_with_an_empty_graveyard(self):
        self.a.hand = [self.gy_cost_card(MAULER)]
        self.land(self.a, 3, ISLAND)
        self.assertFalse(self.g.cast(self.a, MAULER))

    def test_spell_reads_the_exiled_cards_power(self):
        self.a.graveyard = [BIG, BEAR]
        lunge = self.gy_cost_card(LUNGE)
        self.a.hand = [lunge]
        self.land(self.a, 2, SWAMP)
        life = self.b.life
        self.assertTrue(self.g.cast(self.a, lunge, [self.b]))
        self.g.settle()
        self.assertEqual(self.b.life, life - 2)    # BEAR (power 2) was exiled as the cost

    # ------------------------------------------------------ ability costs
    def test_ability_exiles_and_reads_the_graveyard_card(self):
        core = Permanent(MASTICORE, self.a)
        core.sick = False
        self.a.battlefield.append(core)
        self.land(self.a, 1)
        self.a.graveyard = [BIG, BEAR]
        life = self.b.life
        self.assertTrue(self.g.can_activate(self.a, core, 0))
        self.assertTrue(self.g.activate_ability(self.a, core, 0, [self.b]))
        self.g.settle()
        self.assertIn(BEAR, self.a.exile)          # cheapest creature card
        self.assertNotIn(BEAR, self.a.graveyard)
        self.assertEqual(core.last_exiled_gy, (2, 2, 2))
        self.assertEqual(self.b.life, life - 2)

    def test_ability_is_refused_without_a_creature_in_the_graveyard(self):
        core = Permanent(MASTICORE, self.a)
        core.sick = False
        self.a.battlefield.append(core)
        self.land(self.a, 1)
        self.a.graveyard = [LAND]
        self.assertFalse(self.g.can_activate(self.a, core, 0))
        self.assertFalse(self.g.activate_ability(self.a, core, 0, [self.b]))
        self.assertEqual(self.b.life, 20)

    def test_tap_plus_exile_gy_ability(self):
        haunt = Permanent(HAUNT, self.a)
        haunt.sick = False
        self.a.battlefield.append(haunt)
        self.land(self.a, 3, PLAINS)
        self.a.graveyard = [BEAR]
        self.assertTrue(self.g.can_activate(self.a, haunt, 0))
        self.assertTrue(self.g.activate_ability(self.a, haunt, 0))
        self.g.settle()
        self.assertIn(BEAR, self.a.exile)
        self.assertTrue(haunt.tapped)
        self.assertEqual(sum(x.card.name.startswith("Spirit") for x in self.a.battlefield), 1)

    # ------------------------------------------------------------ x-quantity
    def test_exiled_gy_xq_without_a_recording_is_zero(self):
        item = self.g and None
        from mtgsim.engine import StackItem
        it = StackItem(self.a, [], [])
        self.assertEqual(self.g.x_quantity(self.a, ("exiled_gy", "power"), it, None), 0)
        it.exiled_gy_stats = (4, 5, 6)
        self.assertEqual(self.g.x_quantity(self.a, ("exiled_gy", "power"), it, None), 4)
        self.assertEqual(self.g.x_quantity(self.a, ("exiled_gy", "mana value"), it, None), 6)


if __name__ == "__main__":
    unittest.main()

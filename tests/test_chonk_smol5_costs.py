"""smol-chonk-5 batch 6: exile-from-graveyard costs, energy cost edges, sac_plus damage.

The parser templates this batch landed, driven end to end against the engine halves that
were already on the branch base:

- a spell's ``extra_exile_gy`` descriptor ("As an additional cost to cast this spell, exile
  a creature card from your graveyard", Makeshift Mauler, Corpse Lunge), gated in
  can_cast_now, chosen in costs.spell_plan and paid in play.cast
- an activated ability's extra_costs["exile_gy_card"] ("{4}, Exile a creature card from your
  graveyard: ...", Molten-Tail Masticore, Graveyard Marshal)
- word-number energy costs ("Pay eight {E}"), the "sacrifice/tap ~ unless you pay {E}"
  gates (the old pay_or_sac template silently dropped {E}, making them free), and the
  ("sac_plus", n, stat) X-quantity of Broadside Bombardiers' boast
"""
import random
import unittest


from mtgsim.engine import Game, Permanent, Player, StackItem
from mtgsim.identity import instance
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, SWAMP, card

BIG = card("Test Giant", "{4}", "Creature — Giant", "", 4, 5)           # power 4, cmc 4
LAND = card("Test Land", types="Land", text="{T}: Add {G}.")

MAULER = card("Makeshift Mauler", "{1}{U}", "Creature — Zombie",
              "As an additional cost to cast this spell, exile a creature card from your "
              "graveyard.", 2, 3)
LUNGE = card("Test Lunge", "{1}{B}", "Sorcery",
             "As an additional cost to cast this spell, exile a creature card from your "
             "graveyard.\nTest Lunge deals damage equal to the exiled card's power to "
             "target creature.")
MASTICORE = card("Test Masticore", "{4}", "Artifact Creature — Masticore",
                 "{4}, Exile a creature card from your graveyard: Test Masticore deals 4 "
                 "damage to any target.", 4, 4)
MARSHAL = card("Graveyard Marshal", "{2}{B}", "Creature — Zombie",
               "{2}{B}, Exile a creature card from your graveyard: Create a tapped 2/2 "
               "black Zombie creature token.", 2, 2)
ARCHITECT = card("Architect of the Untamed", "{2}{G}", "Creature — Elf Artificer Druid",
                 "Landfall — Whenever a land you control enters, you get {E} (an energy "
                 "counter).\nPay eight {E}: Create a 6/6 colorless Beast artifact creature "
                 "token.", 2, 2)
HELLION = card("Test Hellion", "{2}{R}", "Creature — Hellion",
               "Haste\nAt the beginning of your end step, sacrifice Test Hellion unless you "
               "pay {E}{E}.", 3, 3)
ZOOA = card("Test Zoa", "{1}{U}", "Creature — Beast",
            "At the beginning of your first main phase, tap Test Zoa unless you pay {E}.", 2, 2)
BROADSIDE = card("Broadside Bombardiers", "{2}{R}", "Creature — Goblin Pirate",
                 "Menace, haste\nBoast — Sacrifice another creature or artifact: Broadside "
                 "Bombardiers deals damage equal to 2 plus the sacrificed permanent's mana "
                 "value to any target.", 2, 2)


class Chonk5Costs(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], None)
        self.b = Player("b", [], None)
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        self.g.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def land(self, p, n, c=ISLAND):
        for _ in range(n):
            land = Permanent(c, p)
            land.sick = False
            p.battlefield.append(land)

    def perm(self, c, owner=None):
        perm = Permanent(c, owner or self.a)
        perm.sick, perm.tapped = False, False
        (owner or self.a).battlefield.append(perm)
        return perm


class ExileGraveyardCastCost(Chonk5Costs):
    def test_parse_sets_the_descriptor(self):
        self.assertEqual(MAULER.extra_exile_gy, "creature card")
        self.assertEqual(MAULER.unsupported, [])

    def test_cast_exiles_the_cheapest_matching_graveyard_card(self):
        self.a.graveyard = [BIG, BEAR, LAND]
        mauler = instance(MAULER)
        self.a.hand = [mauler]
        self.land(self.a, 3)
        self.assertTrue(self.g.cast(self.a, mauler))
        self.assertTrue(any(x.card.name == "Makeshift Mauler" for x in self.a.battlefield))
        self.assertIn(BEAR, self.a.exile)            # cheapest creature card (cmc 2)
        self.assertNotIn(BEAR, self.a.graveyard)
        self.assertIn(BIG, self.a.graveyard)
        self.assertIn(LAND, self.a.graveyard)        # not a creature card

    def test_cast_is_refused_without_a_matching_graveyard_card(self):
        self.a.graveyard = [LAND, LAND]
        mauler = instance(MAULER)
        self.a.hand = [mauler]
        self.land(self.a, 3)
        self.assertFalse(self.g.can_cast_now(self.a, mauler))
        self.assertFalse(self.g.cast(self.a, mauler))
        self.assertEqual(self.a.hand, [mauler])

    def test_spell_reads_the_exiled_cards_power(self):
        self.a.graveyard = [BIG, BEAR]
        lunge = instance(LUNGE)
        self.a.hand = [lunge]
        self.land(self.a, 2, SWAMP)
        victim = self.perm(BEAR, self.b)
        self.assertTrue(self.g.cast(self.a, lunge, [victim]))
        self.g.settle()
        self.assertIn(BEAR, self.a.exile)            # BEAR (power 2) exiled as the cost
        self.assertNotIn(victim, self.b.battlefield)  # 2 damage kills the 2/2


class ExileGraveyardAbilityCost(Chonk5Costs):
    def test_parse_sets_the_extra_cost(self):
        (act,) = MASTICORE.activated
        self.assertEqual(act.extra_costs.get("exile_gy_card"), "creature card")
        self.assertEqual(MASTICORE.unsupported, [])

    def test_activation_exiles_and_the_damage_lands(self):
        core = self.perm(MASTICORE)
        self.land(self.a, 4, MOUNTAIN)
        self.a.graveyard = [BIG, BEAR]
        life = self.b.life
        self.assertTrue(self.g.can_activate(self.a, core, 0))
        self.assertTrue(self.g.activate_ability(self.a, core, 0, [self.b]))
        self.g.settle()
        self.assertIn(BEAR, self.a.exile)            # cheapest creature card
        self.assertNotIn(BEAR, self.a.graveyard)
        self.assertEqual(self.b.life, life - 4)

    def test_activation_is_refused_without_a_creature_in_the_graveyard(self):
        core = self.perm(MASTICORE)
        self.land(self.a, 4, MOUNTAIN)
        self.a.graveyard = [LAND]
        self.assertFalse(self.g.can_activate(self.a, core, 0))
        self.assertFalse(self.g.activate_ability(self.a, core, 0, [self.b]))

    def test_marshal_token_ability(self):
        marshal = self.perm(MARSHAL)
        self.land(self.a, 3, SWAMP)
        self.a.graveyard = [BEAR]
        self.assertTrue(self.g.can_activate(self.a, marshal, 0))
        self.assertTrue(self.g.activate_ability(self.a, marshal, 0))
        self.g.settle()
        self.assertIn(BEAR, self.a.exile)
        zombies = [x for x in self.a.battlefield if x.card.name.startswith("Zombie")]
        self.assertEqual(len(zombies), 1)
        self.assertTrue(zombies[0].tapped)           # "Create a tapped ... token"


class EnergyCostEdges(Chonk5Costs):
    def test_word_number_energy_cost(self):
        (act,) = ARCHITECT.activated
        self.assertEqual(act.extra_costs.get("energy"), 8)
        self.assertEqual(ARCHITECT.unsupported, [])
        druid = self.perm(ARCHITECT)
        self.assertFalse(self.g.can_activate(self.a, druid, 0))
        self.a.counters["energy"] = 8
        self.assertTrue(self.g.can_activate(self.a, druid, 0))
        self.assertTrue(self.g.activate_ability(self.a, druid, 0))
        self.g.settle()
        self.assertEqual(self.a.counters["energy"], 0)
        self.assertEqual(sum(x.card.name.startswith("Beast") for x in self.a.battlefield), 1)

    def run_gate(self, cdef, energy):
        perm = self.perm(cdef)
        self.a.counters["energy"] = energy
        effects = [e for t in cdef.triggers if t.event in ("end_step", "main1_begin")
                   for e in t.effects]
        self.g.stack.append(StackItem(self.a, effects, [None] * len(effects),
                                      source=perm, kind="trigger"))
        self.g.resolve_top()
        return perm

    def test_sacrifice_unless_energy_pays_and_keeps_it(self):
        perm = self.run_gate(HELLION, 2)
        self.assertIn(perm, self.a.battlefield)
        self.assertEqual(self.a.counters["energy"], 0)

    def test_sacrifice_unless_energy_sacrifices_when_broke(self):
        perm = self.run_gate(HELLION, 1)
        self.assertNotIn(perm, self.a.battlefield)

    def test_tap_unless_energy(self):
        perm = self.run_gate(ZOOA, 0)
        self.assertTrue(perm.tapped)
        self.assertIn(perm, self.a.battlefield)

    def test_you_get_energy_as_a_gated_payoff(self):
        from mtgsim.cards import _parse_effects
        effs, bad = _parse_effects("you may pay {1}. If you do, you get {E}{E}.")
        self.assertEqual(bad, [])
        self.assertEqual([(e.kind, e.amount, e.cond) for e in effs],
                         [("pay_gate", 0, ""), ("energy", 2, "paid")])
        self.land(self.a, 1)
        self.g.stack.append(StackItem(self.a, effs, [None, None], kind="trigger"))
        self.g.resolve_top()
        self.assertEqual(self.a.counters.get("energy", 0), 2)


class SacPlus(Chonk5Costs):
    def test_boast_damage_is_two_plus_the_sacrificed_mana_value(self):
        (act,) = BROADSIDE.activated
        self.assertEqual(act.extra_costs.get("sacrifice"), "other creature or artifact")
        (eff,) = act.effects
        self.assertEqual(eff.data["xq"], ("sac_plus", 2, "mana value"))
        self.assertEqual(BROADSIDE.unsupported, [])
        goblin = self.perm(BROADSIDE)
        goblin.attack_count = (self.g.turn, 1)       # the boast gate: attacked this turn
        fodder = self.perm(BIG)                      # cmc 4
        self.assertTrue(self.g.can_activate(self.a, goblin, 0))
        self.assertTrue(self.g.activate_ability(self.a, goblin, 0, [self.b]))
        self.g.settle()
        self.assertNotIn(fodder, self.a.battlefield)
        self.assertEqual(self.b.life, 20 - (2 + 4))


if __name__ == "__main__":
    unittest.main()

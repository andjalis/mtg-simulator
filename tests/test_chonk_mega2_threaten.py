"""Mass threaten templates (Mob Rule, Broadcast Takeover, Call for Aid, Reins of Power,
Twist Allegiance, Dihada, Emrakul), the Kumano exile-instead-of-death static, the
subtype-plus-mana-value Rebel searches and the opponent-gain-life triggers."""
import dataclasses
import unittest

from mtgsim import counter_mechanics
from mtgsim.cards import Effect, _parse_effects
from mtgsim.engine import StackItem
from tests.test_batch1 import Batch1
from tests.test_combat_triggers import BEAR
from tests.test_templates import ISLAND, MOUNTAIN, card

BIG = card("Test Giant", "{4}", "Creature — Giant", "", 4, 5)
REBEL2 = card("Test Rebel", "{1}{W}", "Creature — Human Rebel", "", 1, 1)
REBEL5 = card("Test Rebel Lord", "{4}{W}", "Creature — Human Rebel", "", 3, 3)
KUMANO = dataclasses.replace(
    card("Test Kumano", "{3}{R}", "Creature — Human Shaman", "", 3, 3), exile_damaged=True)


class Mega2ThreatenParse(unittest.TestCase):
    def parse(self, text):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        return effects

    def test_all_creatures(self):
        (eff,) = self.parse("Gain control of all creatures until end of turn. Untap them. "
                            "They gain haste until end of turn.")
        self.assertEqual(eff.kind, "mass_threaten")
        self.assertEqual(eff.data, {"type": "creature"})

    def test_mob_rule_power_bounds(self):
        (big,) = self.parse("Gain control of all creatures with power 4 or greater until end of "
                            "turn. Untap those creatures. They gain haste until end of turn.")
        (small,) = self.parse("Gain control of all creatures with power 3 or less until end of "
                              "turn. Untap those creatures. They gain haste until end of turn.")
        self.assertEqual((big.data["power_min"], big.data.get("power_max")), (4, None))
        self.assertEqual((small.data.get("power_min"), small.data["power_max"]), (None, 3))

    def test_artifacts_and_nonland(self):
        (art,) = self.parse("Gain control of all artifacts your opponents control until end of "
                            "turn. Untap them. They gain haste until end of turn.")
        (nonland,) = self.parse("Gain control of all nonland permanents until end of turn. "
                                "Untap them. They gain haste until end of turn.")
        self.assertEqual(art.data["type"], "artifact")
        self.assertEqual(nonland.data["type"], "nonland")

    def test_target_opponent_scope(self):
        (eff,) = self.parse("Gain control of all creatures target opponent controls until end of "
                            "turn. Untap those creatures. Those creatures gain haste until end of turn.")
        self.assertEqual((eff.kind, eff.target), ("mass_threaten", "player"))

    def test_swap_is_one_simultaneous_effect(self):
        effects = self.parse("You and target opponent each gain control of all creatures the "
                             "other controls until end of turn. Untap those creatures. Those "
                             "creatures gain haste until end of turn.")
        effects_reins = self.parse("Untap all creatures you control and all creatures target "
                                   "opponent controls. You and that opponent each gain control of "
                                   "all creatures the other controls until end of turn. Those "
                                   "creatures gain haste until end of turn.")
        self.assertEqual([e.kind for e in effects], ["mass_threaten"])
        self.assertEqual([e.kind for e in effects_reins], ["mass_threaten"])
        self.assertTrue(effects[0].data["swap"])
        self.assertTrue(effects_reins[0].data["swap"])

    def test_permanent_control_without_riders(self):
        (eff,) = self.parse("Gain control of all creatures target player controls")
        self.assertEqual((eff.target, eff.data["until_eot"]), ("player", False))

    def test_per_opponent_is_single_threaten(self):
        effects = self.parse("For each opponent, gain control of up to one target creature that "
                             "player controls until end of turn. Untap those creatures. They gain "
                             "haste until end of turn.")
        self.assertEqual([e.kind for e in effects], ["threaten", "untap_prev", "grant"])
        self.assertEqual(effects[-1].data["keyword"], "haste")


class Mega2ThreatenBehavior(Batch1):
    def test_steals_untaps_and_hastes(self):
        bear, big = self.put(BEAR, self.b), self.put(BIG, self.b)
        bear.tapped = big.tapped = True
        bear.sick = True
        self.apply("Gain control of all creatures until end of turn. Untap them. "
                   "They gain haste until end of turn.")
        self.assertEqual({x.controller for x in (bear, big)}, {self.a})
        self.assertFalse(bear.tapped or big.tapped)
        self.assertFalse(bear.sick)
        counter_mechanics.expire_source_control(self.g, cleanup=True)
        self.assertEqual({x.controller for x in (bear, big)}, {self.b})

    def test_power_bound_filters_victims(self):
        bear, big = self.put(BEAR, self.b), self.put(BIG, self.b)
        self.apply("Gain control of all creatures with power 4 or greater until end of turn. "
                   "Untap those creatures. They gain haste until end of turn.")
        self.assertIs(big.controller, self.a)
        self.assertIs(bear.controller, self.b)

    def test_artifacts_only(self):
        rock = card("Test Rock", "{2}", "Artifact", "")
        bear = self.put(BEAR, self.b)
        gear = self.put(rock, self.b)
        self.apply("Gain control of all artifacts your opponents control until end of turn. "
                   "Untap them. They gain haste until end of turn.")
        self.assertIs(gear.controller, self.a)
        self.assertIs(bear.controller, self.b)

    def test_nonland_takes_creatures_and_artifacts(self):
        rock = card("Test Rock", "{2}", "Artifact", "")
        land = self.put(ISLAND, self.b)
        gear = self.put(rock, self.b)
        self.apply("Gain control of all nonland permanents until end of turn. Untap them. "
                   "They gain haste until end of turn.")
        self.assertIs(gear.controller, self.a)
        self.assertIs(land.controller, self.b)

    def test_target_opponent_scope_steals_from_target(self):
        bear = self.put(BEAR, self.b)
        own = self.put(BEAR)
        self.apply("Gain control of all creatures target opponent controls until end of turn. "
                   "Untap those creatures. Those creatures gain haste until end of turn.", [self.b])
        self.assertIs(bear.controller, self.a)
        self.assertIs(own.controller, self.a)

    def test_swap_exchanges_control(self):
        mine, theirs = self.put(BIG), self.put(BEAR, self.b)
        self.apply("You and target opponent each gain control of all creatures the other "
                   "controls until end of turn. Untap those creatures. Those creatures gain "
                   "haste until end of turn.", [self.b])
        self.assertIs(mine.controller, self.b)
        self.assertIs(theirs.controller, self.a)
        self.assertFalse(mine.tapped or theirs.tapped)

    def test_permanent_control_survives_cleanup(self):
        bear = self.put(BEAR, self.b)
        self.apply("Gain control of all creatures target player controls", [self.b])
        counter_mechanics.expire_source_control(self.g, cleanup=True)
        self.assertIs(bear.controller, self.a)


class Mega2Kumano(Batch1):
    def test_creature_damaged_by_source_is_exiled_when_it_dies(self):
        kumano = self.put(KUMANO, self.a)
        bear = self.put(BEAR, self.b)
        eff = Effect("damage", 3, target="creature")
        self.g.resolve(self.a, eff, bear, StackItem(self.a, [eff], [], source=kumano))
        self.g.settle()
        self.assertIn(BEAR, self.b.exile)
        self.assertNotIn(BEAR, self.b.graveyard)

    def test_creature_damaged_by_source_without_the_static_dies_normally(self):
        archer = self.put(card("Test Archer", "{3}{R}", "Creature — Human Shaman", "", 3, 3))
        bear = self.put(BEAR, self.b)
        eff = Effect("damage", 3, target="creature")
        self.g.resolve(self.a, eff, bear, StackItem(self.a, [eff], [], source=archer))
        self.g.settle()
        self.assertIn(BEAR, self.b.graveyard)

    def test_survivor_is_only_marked_not_exiled(self):
        kumano = self.put(KUMANO)
        bear = self.put(BEAR, self.b)
        eff = Effect("damage", 1, target="creature")
        self.g.resolve(self.a, eff, bear, StackItem(self.a, [eff], [], source=kumano))
        self.g.settle()
        self.assertIn(bear, self.b.creatures)
        self.assertEqual(bear.exile_if_dies, self.g.turn)


class Mega2RebelSearch(Batch1):
    def test_subtype_and_mana_value_search(self):
        self.a.library = [REBEL5, ISLAND, REBEL2, MOUNTAIN]
        self.apply("Search your library for a Rebel permanent card with mana value 3 or less, "
                   "put it onto the battlefield, then shuffle.")
        self.assertEqual([x.card.name for x in self.a.creatures], ["Test Rebel"])

    def test_no_cheap_rebel_finds_nothing(self):
        self.a.library = [REBEL5, ISLAND]
        self.apply("Search your library for a Rebel permanent card with mana value 3 or less, "
                   "put it onto the battlefield, then shuffle.")
        self.assertEqual(self.a.creatures, [])

    def test_unconstrained_subtype_search_still_works(self):
        self.a.library = [REBEL5, ISLAND, REBEL2]
        self.apply("Search your library for a Dragon permanent card, put that card onto the "
                   "battlefield, then shuffle.")
        self.assertEqual(self.a.creatures, [])


class Mega2OppGainsLife(Batch1):
    """The trigger templates parse today; the engine hook that fires ``opp_gains_life`` from
    Game.change_life is a one-line addition reported for game.py, so tests fire it directly."""

    def fire_opp_gains_life(self, gainer, amount):
        self.g.event_amount = amount
        self.g.fire(self.g.opponent(gainer), "opp_gains_life")
        self.g.event_amount = None
        self.g.settle()

    def test_kavu_predator_grows_by_that_much(self):
        from mtgsim.carddb import ALL_CARDS, CardDB
        if not ALL_CARDS.exists():
            self.skipTest("card database not built")
        kavu = self.put(CardDB().get("Kavu Predator"), self.b)
        life = self.a.life
        self.g.change_life(self.a, 3, "test")
        self.fire_opp_gains_life(self.a, 3)
        self.assertEqual(self.a.life, life + 3)
        self.assertEqual(kavu.counters["+1/+1"], 3)
        self.assertEqual((kavu.power, kavu.toughness), (2 + 3, 2 + 3))

    def test_punishing_fire_returns_from_graveyard_for_red(self):
        from mtgsim.carddb import ALL_CARDS, CardDB
        if not ALL_CARDS.exists():
            self.skipTest("card database not built")
        fire = CardDB().get("Punishing Fire")
        self.b.graveyard.append(fire)
        self.b.library = [MOUNTAIN] * 5
        self.put(MOUNTAIN, self.b)
        self.g.change_life(self.a, 2, "test")
        self.fire_opp_gains_life(self.a, 2)
        self.assertIn(fire, self.b.hand)
        self.assertNotIn(fire, self.b.graveyard)

    def test_punishing_fire_stays_when_unable_to_pay(self):
        from mtgsim.carddb import ALL_CARDS, CardDB
        if not ALL_CARDS.exists():
            self.skipTest("card database not built")
        fire = CardDB().get("Punishing Fire")
        self.b.graveyard.append(fire)
        self.b.library = [ISLAND] * 5
        self.put(ISLAND, self.b)
        self.g.change_life(self.a, 2, "test")
        self.fire_opp_gains_life(self.a, 2)
        self.assertIn(fire, self.b.graveyard)


if __name__ == "__main__":
    unittest.main()

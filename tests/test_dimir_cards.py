"""Dimir Midrange cards: Wan Shi Tong (X counters, half-X draw, search trigger)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import ISLAND, card

WAN = card("Test Librarian", "{X}{X}{U}", "Legendary Creature — Spirit", "Flash\nFlying, vigilance\n"
           "When ~ enters, put X +1/+1 counters on him. Then draw half X cards, rounded down.\n"
           "Whenever an opponent searches their library, put a +1/+1 counter on ~ and draw a card.", 1, 1)
FETCH = card("Test Fetch", "{1}", "Sorcery", "Search your library for a basic land card, reveal it, put it into your hand, then shuffle.")


class Dimir(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 20, HeuristicAI())
        self.b = Player("b", [ISLAND] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library.extend([ISLAND] * 10)

    def test_templates(self):
        self.assertEqual(WAN.unsupported, [])
        self.assertEqual(FETCH.unsupported, [])

    def test_x_counters_and_half_draw(self):
        perm = self.game.enter_battlefield(self.a, WAN, x=5)
        before = len(self.a.hand)
        self.game.settle()
        self.assertEqual(perm.p1, 5)
        self.assertEqual(len(self.a.hand) - before, 2)

    def test_search_trigger(self):
        perm = self.game.enter_battlefield(self.a, WAN, x=0)
        self.game.stack.clear()
        n = len(self.a.hand)
        self.game.library_searched(self.b)
        self.game.settle()
        self.assertEqual(perm.p1, 1)
        self.assertEqual(len(self.a.hand), n + 1)


TIDE = card("Test Tidebinder", "{2}{U}", "Creature — Merfolk Wizard", "Flash\nWhen ~ enters, counter up to one target activated or triggered "
            "ability. If an ability of an artifact, creature, or planeswalker is countered this way, that permanent loses all "
            "abilities for as long as ~ remains on the battlefield.", 3, 2)
PINGER = card("Test Pinger", "{2}", "Creature — Human", "Flying\n{T}: Draw a card.", 1, 1)


class Tidebinder(Dimir):
    def test_template(self):
        self.assertEqual(TIDE.unsupported, [])

    def test_counters_ability_and_silences_source(self):
        pinger = Permanent(PINGER, self.b)
        pinger.sick = False
        self.b.battlefield.append(pinger)
        self.assertTrue(pinger.has("flying"))
        self.assertTrue(self.game.can_activate(self.b, pinger, 0))
        self.game._priority_depth += 1      # keep the ability on the stack
        self.game.activate(self.b, pinger, "ability:0")
        self.game._priority_depth -= 1
        self.assertTrue(any(i.kind == "ability" for i in self.game.stack))
        tide = self.game.enter_battlefield(self.a, TIDE)
        self.game.flush_triggers()
        self.game.resolve_top()
        self.assertFalse([i for i in self.game.stack if i.kind == "ability"])
        self.assertFalse(pinger.has("flying"))
        self.assertFalse(self.game.can_activate(self.b, pinger, 0))
        self.game.leave_battlefield(tide, "graveyard")
        self.assertTrue(pinger.has("flying"))


import dataclasses

KAITO = dataclasses.replace(card(
    "Test Kaito", "{2}{U}{B}", "Legendary Planeswalker — Kaito",
    "Ninjutsu {1}{U}{B}\nDuring your turn, as long as ~ has one or more loyalty counters on him, he's a 3/4 Ninja "
    "creature and has hexproof.\n[+1]: You get an emblem with \"Ninjas you control get +1/+1.\"\n[−2]: Draw a card."),
    loyalty=4)
BEAR2 = card("Test Bear Two", "{2}", "Creature — Bear", "", 2, 2)


class Kaito(Dimir):
    def test_template(self):
        self.assertEqual(KAITO.unsupported, [])

    def test_creature_on_own_turn_only(self):
        perm = self.game.enter_battlefield(self.a, KAITO)
        self.assertTrue(perm.is_creature)
        self.assertEqual((perm.power, perm.toughness), (3, 4))
        self.assertIn("Ninja", perm.card.subtypes)
        self.assertTrue(perm.has("hexproof"))
        perm.animated = None   # the end-of-turn cleanup
        self.assertFalse(perm.is_creature)

    def test_emblem_pumps_ninjas(self):
        perm = self.game.enter_battlefield(self.a, KAITO)
        self.game.activate_loyalty(self.a, perm, 0)
        self.game.settle()
        self.assertEqual(self.a.emblems, [("Ninja", 1, 1)])
        self.assertEqual((perm.power, perm.toughness), (4, 5))

    def test_ninjutsu_returns_unblocked_attacker(self):
        bear = self.game.enter_battlefield(self.a, BEAR2)
        bear.sick = False
        self.game.attackers.append(bear)
        self.game.attack_targets[bear] = self.b
        self.a.hand.append(KAITO)
        swamp = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
        for land in (ISLAND, ISLAND, swamp):
            self.a.battlefield.append(Permanent(land, self.a))
        alt = KAITO.alt_costs[0]
        self.assertTrue(self.game.sneak(self.a, KAITO, alt, bear))
        kaito = next(x for x in self.a.battlefield if x.card.name == KAITO.name)
        self.assertTrue(kaito.tapped)
        self.assertIn(kaito, self.game.attackers)
        self.assertIn(BEAR2, self.a.hand)


WASP = card("Test Wasp", "{2}{U}", "Creature — Insect", "Flash\nFlying\nWasp's Sting — When ~ enters, tap up to one target creature. "
            "It loses all abilities for as long as ~ remains on the battlefield.", 2, 2)


class Wasp(Dimir):
    def test_taps_and_silences(self):
        self.assertEqual(WASP.unsupported, [])
        victim = Permanent(PINGER, self.b)
        self.b.battlefield.append(victim)
        wasp = self.game.enter_battlefield(self.a, WASP)
        self.game.settle()
        self.assertTrue(victim.tapped)
        self.assertFalse(victim.has("flying"))
        self.game.leave_battlefield(wasp, "graveyard")
        self.assertTrue(victim.has("flying"))


RAIDER = card("Test Raider", "{2}{R}", "Sorcery", "Create two 1/1 red Goblin creature tokens. Sacrifice them at the beginning of the next end step.")


class EndStepTokens(Dimir):
    def test_tokens_leave_at_end_step(self):
        self.assertEqual(RAIDER.unsupported, [])
        eff = RAIDER.spell_effects[0]
        self.assertEqual(eff.data.get("end"), "sacrifice")
        self.game.create_token(self.a, eff)
        self.assertEqual(len(self.a.creatures), 2)
        self.assertEqual(len(self.game.end_cleanup), 2)

    def test_end_of_turn_cleanup_runs(self):
        eff = RAIDER.spell_effects[0]
        self.game.main_phase = lambda p: self.game.create_token(p, eff) if p is self.a and not self.a.creatures else None
        self.game.take_turn(self.a)
        self.assertEqual(len(self.a.creatures), 0)
        self.assertEqual(self.game.end_cleanup, [])


BENDER = card("Test Bender", "{1}{W}", "Instant", "Airbend target nonland permanent.")


class Airbend(Dimir):
    def test_exiled_and_castable_for_two(self):
        self.assertEqual(BENDER.unsupported, [])
        bear = Permanent(BEAR2, self.b)
        self.b.battlefield.append(bear)
        self.game.resolve(self.a, BENDER.spell_effects[0], bear)
        self.assertNotIn(bear, self.b.battlefield)
        self.assertIn(BEAR2, self.b.airbent)
        for _ in range(2):
            self.b.battlefield.append(Permanent(ISLAND, self.b))
        self.game.step = "main1"
        self.game.active_idx = 1
        options = [c for c in self.game.spell_options(self.b) if c.name.startswith(BEAR2.name)]
        self.assertEqual(len(options), 1)
        self.assertTrue(self.game.can_cast_now(self.b, options[0]))
        self.game.cast(self.b, options[0])
        self.game.settle()
        self.assertTrue(any(x.card.name == BEAR2.name for x in self.b.battlefield))
        self.assertEqual(self.b.airbent, [])


DISC_DIED = card("Test Dread", "{3}{B}", "Instant", "~ costs {3} less to cast if a creature died this turn.\nDestroy target creature.")
DISC_BLOCK = card("Test Strike", "{3}{U}", "Instant", "~ costs {1} less to cast if it targets a blocking creature.\nTap target creature.")
DISC_ATK = card("Test Surge", "{4}{U}", "Instant", "~ costs {1} less to cast for each attacking creature.\nTap target creature.")


class Discounts(Dimir):
    def test_conditional_discount(self):
        self.assertEqual(DISC_DIED.unsupported, [])
        self.assertEqual(self.game.cost_of(self.a, DISC_DIED).get("generic"), 3)
        self.game.creature_died_turn = True
        self.assertEqual(self.game.cost_of(self.a, DISC_DIED).get("generic"), 0)

    def test_targets_blocking_creature(self):
        self.assertEqual(DISC_BLOCK.unsupported, [])
        blocker = Permanent(BEAR2, self.b)
        attacker = Permanent(BEAR2, self.a)
        self.a.battlefield.append(attacker)
        self.b.battlefield.append(blocker)
        self.assertEqual(self.game.cost_of(self.a, DISC_BLOCK).get("generic"), 3)
        self.game.attackers = [attacker]
        self.game.blocks = {attacker: [blocker]}
        self.assertEqual(self.game.cost_of(self.a, DISC_BLOCK).get("generic"), 2)

    def test_per_attacking_creature(self):
        self.assertEqual(DISC_ATK.unsupported, [])
        a1, a2 = Permanent(BEAR2, self.a), Permanent(BEAR2, self.a)
        self.game.attackers = [a1, a2]
        self.assertEqual(self.game.cost_of(self.a, DISC_ATK).get("generic"), 2)


SAC_PAY = card("Silent Echo", "{1}{B}", "Instant", "As an additional cost to cast ~, sacrifice a creature or planeswalker or pay {3}.\nDestroy target creature.")


class AdditionalCosts(Dimir):
    def test_sacrifice_or_pay(self):
        self.assertEqual(SAC_PAY.unsupported, [])
        self.assertEqual(SAC_PAY.extra_sac_or_pay, 3)
        self.assertEqual(self.game.cost_of(self.a, SAC_PAY).get("generic"), 4)
        self.a.battlefield.append(Permanent(BEAR2, self.a))
        self.assertEqual(self.game.cost_of(self.a, SAC_PAY).get("generic", 0), 1)


class AnotherPump(Dimir):
    def test_another_creature_pump(self):
        fox = card("Cunning Fox", "{2}{R}", "Creature — Fox",
                   "Whenever ~ attacks, another target creature you control gets +1/+0 and gains haste until end of turn.", 2, 2)
        self.assertEqual(fox.unsupported, [])
        bear = Permanent(BEAR2, self.a)
        self.a.battlefield.append(bear)
        self.game.resolve(self.a, fox.triggers[0].effects[0], bear)
        self.assertEqual(bear.power, 3)
        self.assertTrue(bear.has("haste"))

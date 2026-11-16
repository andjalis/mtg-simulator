"""Delayed triggers at the next upkeep / your next upkeep / your next end step / the next main phase this turn /
the next cleanup step, and the Pacts (#344, mtgsim/cx_delayed.py)."""
import os
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None
SWAMP = card("Test Swamp", "", "Basic Land — Swamp", "{T}: Add {B}.")


def spell(text):
    c = card("Test Delay", "", "Instant", text)
    assert not c.unsupported, c.unsupported
    return c


class Parse(unittest.TestCase):
    def test_timings(self):
        for text, at in (("At the beginning of your next upkeep, draw a card.", "upkeep_you"),
                         ("Draw a card at the beginning of the next upkeep.", "upkeep"),
                         ("At the beginning of your next end step, draw a card.", "end_you"),
                         ("Add {R} at the beginning of your next main phase this turn.", "main"),
                         ("At the beginning of the next cleanup step, draw a card.", "cleanup")):
            eff = spell(text).spell_effects[-1]
            self.assertEqual((eff.kind, eff.data.get("at")), ("cx_delay", at), text)
        self.assertNotIn("at", spell("At the beginning of the next end step, draw a card.").spell_effects[-1].data)

    def test_refusals(self):
        for text in ("At the beginning of their next upkeep, draw a card.",
                     "At the beginning of your next upkeep, pay {2}{B}. If you do, draw a card.",
                     "At the beginning of the next declare blockers step, draw a card."):
            self.assertTrue(card("Test", "", "Instant", text).unsupported, text)


class Timing(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 2, "main1", 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 30

    def resolve(self, who, c, step="main1"):
        self.game.step = step
        item = self.item(who, c)
        prev = None
        for e in c.spell_effects:
            self.game.resolve(who, e, None, item, prev)
        self.game.settle()

    def item(self, who, c):
        from mtgsim.engine.state import StackItem
        it = StackItem(who, c.spell_effects, [], card=c, kind="spell")
        it.cx_start = self.game.effect_clock
        return it

    def turn(self, who):
        """A whole turn for who (no spells, no combat)."""
        self.game.turn += 1
        self.game.active_idx = self.game.players.index(who)
        with patch.object(self.game, "main_phase"), patch.object(self.game, "combat"):
            self.game.take_turn(who)
        self.game.settle()

    def test_your_next_upkeep_skips_the_opponents(self):
        self.resolve(self.a, spell("At the beginning of your next upkeep, you gain 3 life."))
        self.turn(self.b)
        self.assertEqual(self.a.life, 20)
        self.turn(self.a)
        self.assertEqual(self.a.life, 23)
        self.turn(self.b)
        self.turn(self.a)
        self.assertEqual(self.a.life, 23)                       # once

    def test_the_next_upkeep_is_anyones(self):
        self.resolve(self.a, spell("At the beginning of the next upkeep, you gain 3 life."))
        self.turn(self.b)
        self.assertEqual(self.a.life, 23)

    def test_your_next_upkeep_created_on_the_opponents_turn(self):
        self.game.active_idx = 1
        self.resolve(self.a, spell("At the beginning of your next upkeep, you gain 3 life."), step="upkeep")
        self.turn(self.a)
        self.assertEqual(self.a.life, 23)

    def test_your_next_end_step(self):
        self.game.active_idx = 1                                # cast on b's turn
        self.resolve(self.a, spell("At the beginning of your next end step, you gain 3 life."))
        self.game.begin_end_step(self.b)
        self.game.settle()
        self.assertEqual(self.a.life, 20)
        self.turn(self.a)
        self.assertEqual(self.a.life, 23)

    def test_next_main_phase_this_turn(self):
        self.resolve(self.a, spell("At the beginning of your next main phase this turn, you gain 3 life."),
                     step="combat")
        self.game.step = "main2"
        from mtgsim import cx_delayed
        cx_delayed.at_step(self.game, "main2", self.a)
        self.game.settle()
        self.assertEqual(self.a.life, 23)

    def test_main_phase_this_turn_expires(self):
        self.resolve(self.a, spell("At the beginning of your next main phase this turn, you gain 3 life."),
                     step="main2")                             # no main phase left this turn
        self.turn(self.b)
        self.turn(self.a)
        self.assertEqual(self.a.life, 20)
        self.assertEqual(getattr(self.game, "cx_delayed_at", []), [])

    def test_next_cleanup_step(self):
        self.resolve(self.a, spell("At the beginning of the next cleanup step, you gain 3 life."))
        self.game.begin_end_step(self.a)
        self.game.settle()
        self.assertEqual(self.a.life, 20)
        self.turn(self.b)
        self.assertEqual(self.a.life, 23)


@unittest.skipUnless(HAVE_DB, "card database not built")
class Cards(Timing):
    def test_full(self):
        for n in ("Force of Rage", "Conduit of Storms", "Slaughter Pact", "Summoner's Pact", "Pact of Negation",
                  "Pact of the Titan", "Intervention Pact", "Casey Jones, Vigilante", "Cunning"):
            self.assertEqual(DB.get(n).unsupported, [], n)

    def test_force_of_rage_tokens_die_at_your_next_upkeep(self):
        self.game.active_idx = 1
        self.resolve(self.a, DB.get("Force of Rage"))
        tokens = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual(len(tokens), 2)
        self.game.begin_end_step(self.b)
        self.game.settle()
        self.assertEqual(len([x for x in self.a.battlefield if x.card.is_token]), 2)
        self.turn(self.a)
        self.assertEqual([x for x in self.a.battlefield if x.card.is_token], [])

    def test_conduit_adds_mana_in_the_second_main_phase(self):
        conduit = self.game.enter_battlefield(self.a, DB.get("Conduit of Storms"))
        conduit.sick = False
        self.game.step = "combat"
        self.game.fire(self.a, "attacks", conduit)
        self.game.settle()
        self.assertEqual(self.red(), 0)
        self.game.step = "main2"
        from mtgsim import cx_delayed
        cx_delayed.at_step(self.game, "main2", self.a)
        self.game.settle()
        self.assertEqual(self.red(), 1)

    def red(self):
        return sum(1 for m in self.a.pool if "R" in m.card.produces)

    def test_pact_paid_or_lost(self):
        for lands, lost in ((3, False), (2, True)):
            a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
            game = Game(a, b, random.Random(0))
            game.turn, game.step, game.active_idx = 2, "main1", 0
            a.library = b.library = [ISLAND] * 10
            for _ in range(lands):
                game.enter_battlefield(a, SWAMP)
            self.game, self.a, self.b = game, a, b
            self.resolve(a, DB.get("Slaughter Pact"))
            self.turn(b)
            self.turn(a)
            self.assertEqual(a.lost, lost, lands)

    def test_heuristic_ai_casts_a_pact_only_when_it_can_pay(self):
        for lands, ok in ((2, False), (3, True)):
            a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
            game = Game(a, b, random.Random(0))
            game.turn, game.step, game.active_idx = 3, "main1", 1
            for _ in range(lands):
                game.enter_battlefield(a, SWAMP)
            pact = DB.get("Slaughter Pact")
            a.hand = [pact]
            self.assertEqual(a.ai._can_cast(game, a, pact), ok, lands)       # main-phase and response choices
            from mtgsim.cx_delayed import pact_affordable
            self.assertTrue(pact_affordable(a, DB.get("Force of Rage")))      # no Pact: no limit

@unittest.skipUnless(HAVE_DB, "card database not built")
class Slice2(unittest.TestCase):
    """#344 slice 2: a delayed effect for a player fixed as it resolves; flash Auras' cleanup sacrifice."""
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 2, "main1", 1
        for p in (self.a, self.b):
            p.library = [ISLAND] * 30
        self.island = card("Test Island", "", "Basic Land — Island", "{T}: Add {U}.")
        self.mountain = card("Test Mountain", "", "Basic Land — Mountain", "{T}: Add {R}.")

    def turn(self, who):
        self.game.turn += 1
        self.game.active_idx = self.game.players.index(who)
        with patch.object(self.game, "main_phase"), patch.object(self.game, "combat"):
            self.game.take_turn(who)
        self.game.settle()

    def test_full(self):
        for n in ("Arcane Denial", "Lightning Reflexes"):
            self.assertEqual(DB.get(n).unsupported, [], n)

    def test_arcane_denial_its_controller_draws_two(self):
        from mtgsim.engine.state import StackItem
        bolt = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")
        self.game.stack.append(StackItem(self.b, bolt.spell_effects, [self.a], card=bolt, kind="spell"))
        denial = DB.get("Arcane Denial")
        for _ in range(2):
            self.game.enter_battlefield(self.a, self.island)
        self.a.hand = [denial]
        self.assertTrue(self.game.cast(self.a, denial, [self.game.stack[-1]]))
        self.game.settle()
        self.assertEqual(self.a.life, 20)                          # countered
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (0, 0))
        self.turn(self.a)                                          # the next turn's upkeep (then a's draw step)
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (2, 2))

    def flash_reflexes(self, active):
        self.game.active_idx = self.game.players.index(active)
        bear = self.game.enter_battlefield(self.a, card("Test Bear", "{1}{G}", "Creature — Bear", "", 2, 2))
        for _ in range(2):
            self.game.enter_battlefield(self.a, self.mountain)
        reflexes = DB.get("Lightning Reflexes")
        self.a.hand = [reflexes]
        self.assertTrue(self.game.cast(self.a, reflexes, [bear]))
        self.game.settle()
        return next(x for x in self.a.battlefield if x.card.name == "Lightning Reflexes")

    def test_flash_aura_cast_as_an_instant_is_sacrificed_at_cleanup(self):
        aura = self.flash_reflexes(self.b)                      # on the opponent's turn
        from mtgsim import cx_delayed
        cx_delayed.at_step(self.game, "cleanup", self.b)
        self.game.settle()
        self.assertNotIn(aura, self.a.battlefield)

    def test_flash_aura_cast_at_sorcery_timing_stays(self):
        aura = self.flash_reflexes(self.a)                      # own main phase, empty stack
        from mtgsim import cx_delayed
        cx_delayed.at_step(self.game, "cleanup", self.a)
        self.game.settle()
        self.assertIn(aura, self.a.battlefield)

    def test_heuristic_ai_casts_reflexes_in_its_main_phase_and_keeps_it(self):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        game = Game(a, b, random.Random(0))
        game.turn, game.step, game.active_idx = 3, "main1", 0
        a.library = b.library = [ISLAND] * 10
        game.enter_battlefield(a, card("Test Bear", "{1}{G}", "Creature — Bear", "", 2, 2)).sick = False
        for _ in range(2):
            game.enter_battlefield(a, self.mountain)
        a.hand = [DB.get("Lightning Reflexes")]
        a.ai.main_phase(game, a)
        game.settle()
        from mtgsim import cx_delayed
        cx_delayed.at_step(game, "cleanup", a)
        game.settle()
        self.assertTrue(any(x.card.name == "Lightning Reflexes" for x in a.battlefield))


if __name__ == "__main__":
    unittest.main()

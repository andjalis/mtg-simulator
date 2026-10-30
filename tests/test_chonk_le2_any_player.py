"""le-chonk-2 batch 3: "Any player may activate this ability" support.

The parser does not yet keep these ability lines (see the batch report), so the tests
hand-build ``Activated`` objects whose ``text`` carries the clause — exactly what
``card_from_scryfall`` will produce once the cards-side strip lands, since ``Activated.text``
keeps the original line. Covered: non-controllers may activate and pay for the ability,
"but only during their turn / any upkeep step / their draw step / as a sorcery" windows,
controller-only abilities stay controller-only, the AI activates worthwhile foreign
abilities and refuses to grow an opponent's creature, and a foreign "prevent the next
damage" ability can save a targeted creature.
"""
import dataclasses
import random
import unittest

from mtgsim.cards import Activated, Effect
from mtgsim.engine import Game, Player, StackItem
from mtgsim.engine.policy import (any_player_ability, any_player_worth, any_player_window,
                                  choose_ability, protective_ability)
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, SHOCK, card


def ability(cost, effects, text, **kw):
    return Activated("ability", cost, effects=effects, text=text, **kw)


def with_abilities(cdef, *acts):
    return dataclasses.replace(cdef, activated=list(acts))


WELL = with_abilities(                                       # Well of Knowledge wording
    card("Test Well", "{2}", "Artifact", ""),
    ability({"generic": 2}, [Effect("draw", 1)],
            "{2}: Draw a card. Any player may activate this ability."))
TOME = with_abilities(                                       # controller-only regression guard
    card("Test Tome", "{2}", "Artifact", ""),
    ability({"generic": 4}, [Effect("draw", 1)], "{4}: Draw a card."))
MONGER = with_abilities(                                     # Scandalmonger wording
    card("Test Monger", "{3}", "Creature — Human", "", 3, 3),
    ability({"generic": 2}, [Effect("discard", 1, target="player")],
            "{2}: Target player discards a card. Any player may activate this ability but only as a sorcery."))
HYDRA = with_abilities(                                      # Feral Hydra wording
    card("Test Hydra", "{2}{G}", "Creature — Hydra", "", 2, 2),
    ability({"generic": 3}, [Effect("p1_counters", 1, target="self")],
            "{3}: Put a +1/+1 counter on Test Hydra. Any player may activate this ability."))
PROWLER = with_abilities(                                    # Oona's Prowler wording
    card("Test Prowler", "{1}{B}", "Creature — Faerie Rogue", "Flying", 3, 1),
    ability({}, [Effect("pump", -2, 0, target="self")],
            "Discard a card: Test Prowler gets -2/-0 until end of turn. "
            "Any player may activate this ability.", extra_costs={"discard": 1}))
WELL_DRAW_STEP = with_abilities(                             # Well of Knowledge, restricted
    card("Test Draw Well", "{2}", "Artifact", ""),
    ability({"generic": 2}, [Effect("draw", 1)],
            "{2}: Draw a card. Any player may activate this ability but only during their draw step."))
CLOCK = with_abilities(                                      # Armageddon Clock wording
    card("Test Clock", "{4}", "Artifact", ""),
    ability({"generic": 4}, [Effect("draw", 1)],
            "{4}: Remove a doom counter from Test Clock. "
            "Any player may activate this ability but only during any upkeep step."))
VAPORS = with_abilities(                                     # Volrath's Dungeon wording
    card("Test Vapors", "{2}{B}", "Enchantment", ""),
    ability({}, [Effect("destroy", target="self")],
            "Pay 5 life: Destroy Test Vapors. Any player may activate this ability but only during their turn.",
            extra_costs={"life": 5}))
SANCTUARY = with_abilities(                                  # Samite Sanctuary wording
    card("Test Sanctuary", "{1}{W}", "Enchantment", ""),
    ability({"generic": 2}, [Effect("prevent_next", 1, target="creature")],
            "{2}: Prevent the next 1 damage that would be dealt to target creature this turn. "
            "Any player may activate this ability."))


class AnyPlayer(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, c, who=None):
        perm = self.game.enter_battlefield(who or self.a, c)
        perm.sick = False
        self.game.settle()
        return perm

    def mana(self, p, n=4):
        for _ in range(n):
            land = self.put(MOUNTAIN, p)
            land.tapped = False

    def test_flags(self):
        self.assertTrue(any_player_ability(WELL.activated[0]))
        self.assertTrue(any_player_ability(MONGER.activated[0]))
        self.assertFalse(any_player_ability(TOME.activated[0]))
        self.assertEqual(any_player_window(WELL.activated[0]), "")
        self.assertEqual(any_player_window(MONGER.activated[0]), "sorcery")
        self.assertEqual(any_player_window(WELL_DRAW_STEP.activated[0]), "draw_step")
        self.assertEqual(any_player_window(CLOCK.activated[0]), "upkeep")
        self.assertEqual(any_player_window(VAPORS.activated[0]), "their_turn")
        flagged = Activated("ability", {"generic": 1}, effects=[Effect("draw", 1)], text="{1}: Draw a card.")
        flagged.any_player = True                       # a parsed flag wins even without the text
        self.assertTrue(any_player_ability(flagged))
        self.assertTrue(any_player_window(flagged) == "")

    def test_non_controller_may_activate(self):
        well = self.put(WELL)                            # a controls the Well
        self.mana(self.a)
        self.mana(self.b)
        self.assertTrue(self.game.can_activate(self.a, well, 0))
        self.assertTrue(self.game.can_activate(self.b, well, 0))     # the opponent too
        tome = self.put(TOME)
        self.assertTrue(self.game.can_activate(self.a, tome, 0))
        self.assertFalse(self.game.can_activate(self.b, tome, 0))    # controller-only unchanged

    def test_opponent_activation_pays_and_resolves(self):
        well = self.put(WELL)
        self.mana(self.b, 2)
        self.b.hand = []
        self.assertTrue(self.game.activate(self.b, well, "ability:0"))
        self.game.settle()
        self.assertEqual(len(self.b.hand), 1)            # the activator draws
        self.assertEqual(len(self.a.hand), 0)
        self.assertIn(well, self.a.battlefield)         # the source stays with its controller
        self.assertTrue(all(m.tapped for m in self.b.battlefield))   # the activator's lands paid

    def test_discard_cost_paid_by_activator(self):
        prowler = self.put(PROWLER)                      # a's 3/1
        self.b.hand = [ISLAND, ISLAND, ISLAND]
        self.assertTrue(self.game.activate(self.b, prowler, "ability:0"))
        self.game.settle()
        self.assertEqual(len(self.b.hand), 2)           # b discarded their own card
        self.assertEqual(prowler.power, 1)               # ... to shrink a's creature to 1

    def test_sorcery_window(self):
        monger = self.put(MONGER)
        self.mana(self.a, 2)
        self.mana(self.b, 2)
        self.a.hand = [ISLAND, ISLAND]
        # a's turn: b may not (sorcery window), a may.
        self.assertFalse(self.game.can_activate(self.b, monger, 0))
        self.assertTrue(self.game.can_activate(self.a, monger, 0))
        # b's turn, empty stack: b may activate and make a discard.
        self.game.active_idx = 1
        self.assertTrue(self.game.can_activate(self.b, monger, 0))
        self.assertTrue(self.game.activate(self.b, monger, "ability:0", target=[self.a]))
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_draw_step_window(self):
        well = self.put(WELL_DRAW_STEP)
        self.mana(self.a, 2)
        self.mana(self.b, 2)
        self.game.step = "draw"
        self.assertFalse(self.game.can_activate(self.b, well, 0))     # not b's draw step
        self.assertTrue(self.game.can_activate(self.a, well, 0))
        self.game.active_idx = 1
        self.assertFalse(self.game.can_activate(self.a, well, 0))
        self.assertTrue(self.game.can_activate(self.b, well, 0))
        self.game.step = "main1"
        self.assertFalse(self.game.can_activate(self.b, well, 0))

    def test_upkeep_window(self):
        clock = self.put(CLOCK)
        self.mana(self.a, 4)
        self.mana(self.b, 4)
        self.assertFalse(self.game.can_activate(self.b, clock, 0))    # main phase: no
        self.game.step = "upkeep"                       # any player's upkeep: both may
        self.assertTrue(self.game.can_activate(self.a, clock, 0))
        self.assertTrue(self.game.can_activate(self.b, clock, 0))

    def test_their_turn_window(self):
        vapors = self.put(VAPORS)
        self.assertFalse(self.game.can_activate(self.b, vapors, 0))   # a's turn
        self.assertTrue(self.game.can_activate(self.a, vapors, 0))
        self.game.active_idx = 1
        self.assertTrue(self.game.can_activate(self.b, vapors, 0))
        self.assertFalse(self.game.can_activate(self.a, vapors, 0))

    def test_ai_uses_foreign_draw_ability(self):
        well = self.put(WELL, self.b)                    # b controls it
        self.mana(self.a, 2)
        action = choose_ability(self.game, self.a, instant=False)
        self.assertEqual(action, ("activate", well, "ability:0"))
        self.assertTrue(self.game.do_action(self.a, action))
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_ai_uses_foreign_discard_ability(self):
        monger = self.put(MONGER, self.b)
        self.mana(self.a, 2)
        self.b.hand = [ISLAND, ISLAND, ISLAND]
        action = choose_ability(self.game, self.a, instant=False)     # a's main phase: sorcery ok
        self.assertEqual(action, ("activate", monger, "ability:0"))
        self.assertTrue(self.game.do_action(self.a, action))
        self.game.settle()
        self.assertEqual(len(self.b.hand), 2)

    def test_ai_will_not_grow_opponents_creature(self):
        hydra = self.put(HYDRA, self.b)
        self.mana(self.a, 3)
        self.assertIsNone(choose_ability(self.game, self.a, instant=False))
        self.assertFalse(any_player_worth(self.game, self.a, hydra, 0))
        self.assertFalse(self.game.can_activate(self.a, hydra, 0) is False)   # legal, just unwise

    def test_ai_will_not_shrink_itself_symmetrically(self):
        warmonger = with_abilities(
            card("Test Warmonger", "{2}{R}", "Creature — Human", "", 2, 2),
            ability({"generic": 2}, [Effect("damage", 1, target="each_creature", filter="nonflying"),
                                     Effect("damage_each_player", 1)],
                    "{2}: Test Warmonger deals 1 damage to each creature without flying and each player. "
                    "Any player may activate this ability."))
        self.put(warmonger, self.b)
        self.mana(self.a, 2)
        self.assertIsNone(choose_ability(self.game, self.a, instant=False))

    def test_foreign_protective_ability(self):
        self.put(SANCTUARY, self.b)                      # b controls the saver
        self.mana(self.a, 2)
        victim = self.put(BEAR)                          # a's 2/2
        shock = StackItem(self.b, [Effect("damage", 2, target="creature")], [victim], card=SHOCK,
                          name="Shock", kind="spell")
        self.game.stack.append(shock)
        saver = protective_ability(self.game, self.a, shock, victim)
        self.assertIsNotNone(saver)
        self.assertEqual(saver[0], "activate")
        self.assertTrue(self.game.do_action(self.a, saver))
        self.game.settle()
        self.assertIn(victim, self.a.battlefield)        # shielded: survives the Shock
        self.assertEqual(len(self.b.hand), 0)            # b never got involved


if __name__ == "__main__":
    unittest.main()

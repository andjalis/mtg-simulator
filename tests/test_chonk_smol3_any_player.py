"""smol-chonk-3 batch 4: "Any player may activate this ability" wordings parse onto Activated.

The engine side (policy.any_player_ability / any_player_window, can_activate windows) landed with
656f97a; these tests parse the real wordings through card_from_scryfall — the trailing clause is
stripped, Activated.any_player is set, the "as a sorcery" variant keeps its window — and one
opponent activation is driven end to end off the parsed card.
"""
import random
import unittest

from mtgsim.engine import Game, Player, Permanent
from mtgsim.engine.policy import any_player_ability, any_player_window
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, MOUNTAIN, card

SCANDALMONGER = card("Scandalmonger", "{3}{B}", "Creature — Human Rogue",
                     "{2}: Target player discards a card. Any player may activate this ability but "
                     "only as a sorcery.", 3, 3)
WELL = card("Well of Knowledge", "{3}", "Artifact",
            "{2}: Draw a card. Any player may activate this ability.")
PROWLER = card("Oona's Prowler", "{1}{B}", "Creature — Faerie Rogue",
               "Flying\nDiscard a card: Oona's Prowler gets -2/-0 until end of turn. "
               "Any player may activate this ability.", 3, 1)
CLOCK = card("Armageddon Clock", "{6}", "Artifact",
             "{4}: Remove a doom counter from Armageddon Clock. Any player may activate this "
             "ability but only during any upkeep step.")
WELL_DRAW = card("Test Draw Well", "{3}", "Artifact",
                 "{2}: Draw a card. Any player may activate this ability but only during their draw step.")
VAPORS = card("Volrath's Dungeon", "{2}{B}{B}", "Enchantment",
              "Pay 5 life: Destroy Volrath's Dungeon. Any player may activate this ability but "
              "only during their turn.")
HYDRA = card("Feral Hydra", "{X}{G}", "Creature — Hydra",
             "This creature enters with X +1/+1 counters on it.\n{3}: Put a +1/+1 counter on this "
             "creature. Any player may activate this ability.", 1, 1)
TOME = card("Test Tome", "{2}", "Artifact", "{4}: Draw a card.")   # controller-only regression guard


class AnyPlayerParse(unittest.TestCase):
    def test_clauses_stripped_and_flagged(self):
        for cdef in (SCANDALMONGER, WELL, PROWLER, CLOCK, WELL_DRAW, VAPORS, HYDRA):
            self.assertEqual(cdef.unsupported, [], cdef.name)
        self.assertEqual(len(HYDRA.activated), 1)
        self.assertEqual(HYDRA.activated[0].effects[0].kind, "p1_counters")

    def test_any_player_flags_and_windows(self):
        self.assertTrue(any_player_ability(WELL.activated[0]))
        self.assertEqual(any_player_window(WELL.activated[0]), "")
        self.assertEqual(any_player_window(SCANDALMONGER.activated[0]), "sorcery")
        self.assertEqual(any_player_window(CLOCK.activated[0]), "upkeep")
        self.assertEqual(any_player_window(WELL_DRAW.activated[0]), "draw_step")
        self.assertEqual(any_player_window(VAPORS.activated[0]), "their_turn")
        for cdef in (SCANDALMONGER, WELL, PROWLER, CLOCK, WELL_DRAW, VAPORS, HYDRA):
            self.assertTrue(cdef.activated[0].any_player, cdef.name)
        self.assertFalse(any_player_ability(TOME.activated[0]))
        self.assertFalse(TOME.activated[0].any_player)

    def test_sorcery_variant_keeps_sorcery(self):
        self.assertTrue(SCANDALMONGER.activated[0].sorcery)
        self.assertFalse(WELL.activated[0].sorcery)

    def test_discard_cost_untouched(self):
        act = PROWLER.activated[0]
        self.assertEqual(act.extra_costs, {"discard": 1})
        self.assertEqual(act.effects[0].kind, "pump")

    def test_opponent_activates_end_to_end(self):
        a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
        game = Game(a, b, random.Random(0))
        game.turn, game.step, game.active_idx = 2, "main1", 0
        b.library = [ISLAND] * 20
        well = Permanent(WELL, a)
        well.sick = False
        a.battlefield.append(well)
        for _ in range(2):
            land = Permanent(MOUNTAIN, b)
            land.sick = False
            b.battlefield.append(land)
        self.assertTrue(game.can_activate(b, well, 0))       # not the controller: still legal
        self.assertTrue(game.activate(b, well, "ability:0"))
        game.settle()
        self.assertEqual(len(b.hand), 1)                     # the activator draws
        self.assertIn(well, a.battlefield)                   # the source stays with its controller

    def test_sorcery_window_blocks_opponent_on_others_turn(self):
        a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
        game = Game(a, b, random.Random(0))
        game.turn, game.step, game.active_idx = 2, "main1", 0
        monger = Permanent(SCANDALMONGER, a)
        monger.sick = False
        a.battlefield.append(monger)
        for _ in range(2):
            land = Permanent(MOUNTAIN, b)
            land.sick = False
            b.battlefield.append(land)
        self.assertFalse(game.can_activate(b, monger, 0))    # a's turn, sorcery window (b could pay)
        game.active_idx = 1
        self.assertTrue(game.can_activate(b, monger, 0))     # b's turn


if __name__ == "__main__":
    unittest.main()

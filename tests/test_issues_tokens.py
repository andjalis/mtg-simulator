"""Issues #253 (target player/opponent creates a token) and #259 (chosen-colour anthems)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.coverage import card_coverage
from mtgsim.cx_tokens import parse_create
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_templates import card

GOBLIN = card("Test Goblin", "{R}", "Creature — Goblin", "", 3, 1)
SPHINX = card("Test Sphinx", "{3}{U}{U}", "Creature — Sphinx", "", 4, 4)


class Parse(unittest.TestCase):
    def test_target_subjects(self):
        e = parse_create("target player", "a 6/5 blue Leviathan creature token with hexproof")[0]
        self.assertEqual((e.target, e.filter, e.data["side"]), ("player", "", "mine"))
        e = parse_create("target opponent", "a 3/3 green Dinosaur creature token with trample")[0]
        self.assertEqual((e.target, e.filter, e.data["side"]), ("player", "opp", "theirs"))

    def test_target_copy_stays_unmatched(self):
        from mtgsim.cards.model import NO_MATCH
        self.assertIs(parse_create("target player", "a token that's a copy of it"), NO_MATCH)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class Cards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [SPHINX] * 20, HeuristicAI())
        self.b = Player("b", [GOBLIN] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=False)
        for p in (self.a, self.b):
            p.library = list(p.deck)
        self.game.turn, self.game.step = 3, "main1"

    def put(self, name, who=None):
        return self.game.enter_battlefield(who or self.a, self.db.get(name))

    def test_cards_lose_the_token_clause(self):
        for name in ("Atlantis Attacks", "Baffling End"):
            self.assertEqual([u for u in self.db.get(name).unsupported if "creates" in u], [], name)
        for name in ("Hall of Triumph", "Heraldic Banner"):
            self.assertEqual(card_coverage(self.db.get(name)).ignored, [], name)
        for name in ("Caged Sun", "Gauntlet of Power"):          # the mana-doubling line is still unsupported
            self.assertEqual(len(self.db.get(name).unsupported), 1, name)

    def test_target_opponent_creates_for_the_opponent(self):
        eff = self.db.get("Baffling End").triggers[-1].effects[-1]
        from mtgsim.engine import default_choose_target
        tgt = default_choose_target(self.game, self.a, eff)
        self.assertIs(tgt, self.b)
        self.game.resolve(self.a, eff, tgt)
        self.assertEqual([x.card.name for x in self.b.battlefield if x.card.is_token], ["Dinosaur token"])
        self.assertFalse(self.a.battlefield)

    def test_leave_trigger_in_a_real_game(self):
        end = self.put("Baffling End")
        self.game.stack.clear()
        self.game.destroy(end)
        self.game.flush_triggers()
        while self.game.stack:
            self.game.resolve_top()
        self.assertEqual([x.card.name for x in self.b.battlefield if x.card.is_token], ["Dinosaur token"])
        self.assertFalse([x for x in self.a.battlefield if x.card.is_token])

    def test_target_player_creates_for_the_caster(self):
        eff = self.db.get("Atlantis Attacks").modes[0][0]
        from mtgsim.engine import default_choose_target
        tgt = default_choose_target(self.game, self.a, eff)
        self.assertIs(tgt, self.a)
        self.game.resolve(self.a, eff, tgt)
        tokens = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual([(x.power, x.toughness) for x in tokens], [(6, 5)])
        self.assertFalse(self.b.battlefield)

    def test_anthem_chosen_colour_is_the_decks_main_creature_colour(self):
        banner = self.put("Hall of Triumph")
        self.assertEqual(banner.chosen_color, "U")
        sphinx = self.game.enter_battlefield(self.a, SPHINX)
        goblin = self.game.enter_battlefield(self.a, GOBLIN)
        enemy = self.game.enter_battlefield(self.b, SPHINX)
        self.assertEqual((sphinx.power, sphinx.toughness), (5, 5))
        self.assertEqual((goblin.power, goblin.toughness), (3, 1))     # wrong colour
        self.assertEqual((enemy.power, enemy.toughness), (4, 4))       # not ours

    def test_heraldic_banner_power_only(self):
        self.put("Heraldic Banner")
        sphinx = self.game.enter_battlefield(self.a, SPHINX)
        self.assertEqual((sphinx.power, sphinx.toughness), (5, 4))

    def test_anthem_leaves_with_the_source(self):
        hall = self.put("Hall of Triumph")
        sphinx = self.game.enter_battlefield(self.a, SPHINX)
        self.a.battlefield.remove(hall)
        self.assertEqual(sphinx.power, 4)

    def test_both_sides_variant_via_card_data(self):
        import dataclasses
        base = self.db.get("Hall of Triumph")
        gauntlet = dataclasses.replace(base, anthem_sub=(("chosen_color:all", 1, 1, False),))
        self.game.enter_battlefield(self.a, gauntlet)
        mine = self.game.enter_battlefield(self.a, SPHINX)
        theirs = self.game.enter_battlefield(self.b, SPHINX)
        red = self.game.enter_battlefield(self.b, GOBLIN)
        self.assertEqual((mine.power, theirs.power, red.power), (5, 5, 3))


if __name__ == "__main__":
    unittest.main()

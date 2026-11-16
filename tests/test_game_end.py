"""#629: losing and winning the game: "<player> loses the game" (#760's life_total, kind player_loses, extended here with
"that player / its controller / defending player") and conditions on a library or an exact hand size (cx_library_conds), checked until the game really ends with the right winner."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Battle of Wits", "Door to Nothingness", "Triskaidekaphile", "Vorpal Sword")
DOOM = card("Test Doom", "{B}", "Sorcery", "Target player loses the game.")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


class Parse(unittest.TestCase):
    def test_lose_verb_and_conditions(self):
        self.assertEqual(DOOM.unsupported, [])
        # read by life_total (#760); the AI aims it at the opponent (Resolve)
        from mtgsim.cards.clauses import _if_cond
        self.assertEqual(_if_cond("your library has no cards in it"), 'lib:["res","you","library","==",0]')
        self.assertEqual(_if_cond("you have exactly thirteen cards in your hand"), 'lib:["res","you","hand","==",13]')
        self.assertEqual(_if_cond("you have 200 or more cards in your library"),
                         'lib:["res","you","library",">=",200]')

    def test_refusals(self):
        for text in ("Target player loses the game at the beginning of the next end step if they control no lands.",
                     "If you have exactly thirteen cards in your graveyard, you win the game."):
            self.assertTrue(card("Test Odd", "{B}", "Sorcery", text).unsupported, text)


class Resolve(unittest.TestCase):
    def test_target_player_loses_and_the_ai_aims_at_the_opponent(self):
        g, a, b = game()
        effects = list(DOOM.spell_effects)
        targets = g.auto_targets(a, effects, None)
        self.assertIs(targets[0], b)
        g.stack.append(StackItem(a, effects, targets, card=DOOM, name=DOOM.name))
        g.resolve_top()
        self.assertTrue(g.over)
        self.assertTrue(b.lost)
        self.assertFalse(a.lost)

    def test_cant_lose_stops_it(self):
        g, a, b = game()
        g.enter_battlefield(b, card("Test Angel", "{7}", "Artifact Creature — Angel", "Flying\nYou can't lose the "
                                    "game and your opponents can't win the game.", 4, 4))
        effects = list(DOOM.spell_effects)
        g.stack.append(StackItem(a, effects, [b], card=DOOM, name=DOOM.name))
        g.resolve_top()
        self.assertFalse(b.lost)
        self.assertFalse(g.over)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in FULL:
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)

    def test_triskaidekaphile_wins_at_upkeep_with_thirteen_cards(self):
        for hand, wins in ((13, True), (12, False)):
            g, a, b = game()
            g.enter_battlefield(a, self.db.get("Triskaidekaphile"))
            a.hand = [ISLAND] * hand
            g.upkeep(a) if hasattr(g, "upkeep") else g.fire(a, "upkeep")
            g.settle()
            self.assertEqual((b.lost, g.over), (wins, wins), hand)

    def test_battle_of_wits_wins_a_whole_game(self):
        """The real game loop: the deck with Battle of Wits casts it and wins at a later upkeep."""
        wits, idle = self.db.get("Battle of Wits"), self.db.get("Swamp")
        a = Player("wits", [wits] * 30 + [self.db.get("Island")] * 201, HeuristicAI())
        b = Player("idle", [idle] * 60, HeuristicAI())
        g = Game(a, b, random.Random(3), log=False)
        g.max_turns = 30
        winner = g.play()
        self.assertIs(winner, a)
        self.assertTrue(b.lost)
        self.assertFalse(a.lost)

    def test_vorpal_sword_grant_ends_the_game_on_combat_damage(self):
        from tests.test_combat_triggers import Scripted
        a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 2, "main1"
        for p in (a, b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
        bear = g.enter_battlefield(a, card("Bear", "{1}", "Creature — Bear", "", 2, 2))
        bear.sick = False
        sword = g.enter_battlefield(a, self.db.get("Vorpal Sword"))
        sword.attached_to = bear
        grant = sword.card.activated[-1] if sword.card.activated else None
        self.assertIsNotNone(grant)
        g.stack.append(StackItem(a, list(grant.effects), [None] * len(grant.effects), source=sword, name="sword"))
        g.resolve_top()
        g.settle()
        a.ai.attack = [bear]
        g.combat(a, b)
        g.settle()
        self.assertTrue(b.lost)
        self.assertTrue(g.over)


if __name__ == "__main__":
    unittest.main()

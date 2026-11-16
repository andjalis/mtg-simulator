"""#839: "~ can be your commander." and the other deck-building commander lines change nothing in a two-player game
(the simulator has no Commander format), so they are read as no-ops instead of blocking 34 planeswalkers."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


class Parse(unittest.TestCase):
    def test_commander_lines_do_not_block(self):
        for text in ("~ can be your commander.", "~ can be your Commander.", "Spell commander",
                     "~ can be your commander. If it is, your deck can contain any basic land cards and cards of any "
                     "color identity that can create Food tokens."):
            c = card("Test Legend", "{1}{G}", "Legendary Creature — Elf", text.replace("~", "Test Legend"), 2, 2)
            self.assertTrue(c.fully_supported, text)
            self.assertEqual((c.triggers, c.activated, c.spell_effects), ([], [], []), text)

    def test_refusals(self):
        # lines that do something with commanders in a game stay unsupported
        c = card("Test Thief", "{2}{B}", "Creature — Rogue", "When this creature enters, gain control of all "
                 "commanders.", 2, 2)
        self.assertFalse(c.fully_supported)

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_real_cards_full(self):
        for name in ("Lord Windgrace", "Quintorius, History Chaser", "Freyalise, Llanowar's Fury", "Commodore Guff",
                     "Ransack, the Lab", "Rampant, Growth"):
            self.assertTrue(db(name).fully_supported, name)
        self.assertFalse(db("Tevesh Szat, Doom of Fools").fully_supported)      # its commander abilities do things


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Play(unittest.TestCase):
    """The card plays as it did: loyalty abilities once per turn at sorcery speed, the cost paid, dies at 0."""

    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        self.game.active_idx = 0
        self.a.my_turn, self.b.my_turn = True, False
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_freyalise_loyalty_abilities(self):
        c = db("Freyalise, Llanowar's Fury")
        pw = self.game.enter_battlefield(self.a, c)
        self.game.settle()
        start = pw.loyalty
        plus = next(i for i, (cost, _) in enumerate(c.loyalty_abilities) if cost > 0)
        self.game.step = "combat"
        self.assertFalse(self.game.activate_loyalty(self.a, pw, plus))           # sorcery speed only
        self.game.step = "main1"
        self.assertTrue(self.game.activate_loyalty(self.a, pw, plus))            # +2: a 1/1 Elf Druid
        self.assertEqual(pw.loyalty, start + 2)
        self.assertTrue(any(x.card.is_token for x in self.a.battlefield))
        self.assertFalse(self.game.activate_loyalty(self.a, pw, plus))           # once per turn
        minus = max(range(len(c.loyalty_abilities)), key=lambda i: -c.loyalty_abilities[i][0])
        pw.loyalty_used = False
        cost = c.loyalty_abilities[minus][0]
        pw.counters["loyalty"] = -cost - 1
        self.assertFalse(self.game.activate_loyalty(self.a, pw, minus))          # can't pay more loyalty than it has
        pw.counters["loyalty"] = -cost
        self.assertTrue(self.game.activate_loyalty(self.a, pw, minus))           # down to 0: put into the graveyard
        self.game.settle()
        self.assertNotIn(pw, self.a.battlefield)
        self.assertIn("Freyalise, Llanowar's Fury", [x.name for x in self.a.graveyard])

    def test_ai_uses_a_commander_line_walker(self):
        pw = self.game.enter_battlefield(self.a, db("Freyalise, Llanowar's Fury"))
        self.game.settle()
        self.a.ai.use_abilities(self.game, self.a)
        self.game.settle()
        self.assertTrue(pw.loyalty_used)
        self.assertGreater(pw.loyalty, 3)                                         # +2: builds up, makes an Elf
        self.assertTrue(any(x.card.is_token for x in self.a.battlefield))


if __name__ == "__main__":
    unittest.main()

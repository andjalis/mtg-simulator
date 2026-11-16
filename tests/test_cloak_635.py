"""#635 MANIFEST/CLOAK: manifesting or cloaking more cards, from the hand, and "then attach ~ to it"."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


class Parse(unittest.TestCase):
    def test_wordings(self):
        for text, data, n in (("Manifest the top two cards of your library.", {"cloak": False}, 2),
                              ("Cloak the top card of your library.", {"cloak": True}, 1),
                              ("Cloak a card from your hand.", {"cloak": True, "from": "hand"}, 1),
                              ("Cloak the top card of your library, then attach ~ to it.",
                               {"cloak": True, "attach": True}, 1)):
            effects, bad = _parse_effects(text)
            self.assertEqual(bad, [], text)
            self.assertEqual((effects[0].kind, effects[0].amount, effects[0].data), ("manifest", n, data), text)

    def test_refusals(self):
        # "cloak two of them" from a look, and the opponent's library (who owns it?) stay unread for now
        for text in ("Look at the top five cards of your library, cloak two of them, and put the rest on the bottom "
                     "of your library in a random order.", "Manifest the top card of that player's library."):
            self.assertTrue(_parse_effects(text)[1], text)

    def test_real_cards_full(self):
        for name in ("Cryptic Coat", "Ethereal Ambush", "Scroll of Fate", "Vannifar, Evolved Enigma"):
            self.assertTrue(db(name).fully_supported, name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Game_(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def face_down(self, p):
        return [x for x in p.battlefield if x.hidden is not None]

    def test_ethereal_ambush_manifests_two(self):
        self.a.library = [ISLAND] * 5 + [db("Craw Wurm"), db("Shock")]
        c = db("Ethereal Ambush")
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [None], card=c, name=c.name))
        self.game.resolve_top()
        self.game.settle()
        self.assertEqual(sorted(x.hidden.name for x in self.face_down(self.a)), ["Craw Wurm", "Shock"])
        self.assertTrue(all((x.power, x.toughness, x.card.ward) == (2, 2, 0) for x in self.face_down(self.a)))

    def test_scroll_of_fate_manifests_a_creature_from_hand(self):
        scroll = self.game.enter_battlefield(self.a, db("Scroll of Fate"))
        self.a.hand = [db("Shock"), db("Craw Wurm"), ISLAND]
        self.assertTrue(self.game.activate_ability(self.a, scroll, 0))
        self.game.settle()
        self.assertEqual([x.hidden.name for x in self.face_down(self.a)], ["Craw Wurm"])
        self.assertEqual(sorted(c.name for c in self.a.hand), ["Island", "Shock"])

    def test_cryptic_coat_cloaks_and_attaches_with_ward(self):
        self.a.library = [ISLAND] * 5 + [db("Craw Wurm")]
        coat = self.game.enter_battlefield(self.a, db("Cryptic Coat"))
        self.game.settle()
        cloaked = self.face_down(self.a)[0]
        self.assertIs(coat.attached_to, cloaked)
        self.assertEqual((cloaked.card.ward, cloaked.power), (2, 3))      # ward {2}; +1/+0 from the Coat
        from mtgsim.face_states import turn_up
        self.assertTrue(turn_up(self.game, cloaked))
        self.assertEqual((cloaked.card.name, cloaked.card.ward), ("Craw Wurm", 0))


if __name__ == "__main__":
    unittest.main()

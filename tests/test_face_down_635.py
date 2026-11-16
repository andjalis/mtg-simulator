"""#635 FACE-UP/DOWN: turning a face-down creature face up by an effect, and turning a creature face down."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card

MOUNTAIN = card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


class Parse(unittest.TestCase):
    def test_wordings(self):
        effects, bad = _parse_effects("Turn target face-down creature an opponent controls face up.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].data["selector"], {"types_all": ["creature"], "traits": ["face-down"],
                                                       "controller": "opp"})
        effects, bad = _parse_effects("Turn ~ face down.")
        self.assertEqual((bad, effects[0].kind, effects[0].target), ([], "turn_face_down", "self"))
        effects, bad = _parse_effects("You may turn target creature with a morph ability face down.")
        self.assertEqual([e.kind for e in effects], ["pay_gate", "turn_face_down"])

    def test_refusals(self):
        # "any number of target creatures with morph abilities other than ~" and "turn all other nontoken creatures
        # face down" are other shapes: left unread
        for name in ("Weaver of Lies", "Ixidron"):
            self.assertFalse(db(name).fully_supported, name)

    def test_real_cards_full(self):
        for name in ("Backslide", "Break Open", "Ixidor, Reality Sculptor", "Master of the Veil", "Skirk Alarmist",
                     "Skittish Valesk", "Wall of Deceit"):
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

    def manifest(self, p, name):
        from mtgsim.manifest import manifest_one
        perm = manifest_one(self.game, p, db(name))
        self.game.settle()
        return perm

    def resolve(self, name, targets):
        c = db(name)
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), list(targets), card=c, name=c.name))
        self.game.resolve_top()
        self.game.settle()

    def test_break_open_turns_their_creature_up_and_fires_the_trigger(self):
        face_down = self.manifest(self.b, "Craw Wurm")
        self.resolve("Break Open", [face_down])
        self.assertEqual(face_down.card.name, "Craw Wurm")
        self.assertIsNone(face_down.hidden)

    def test_a_manifested_instant_stays_face_down(self):
        face_down = self.manifest(self.b, "Shock")
        self.resolve("Break Open", [face_down])
        self.assertEqual(face_down.card.name, "Face-down creature")

    def test_turned_face_up_trigger(self):
        thinner = self.game.enter_battlefield(self.a, card("Face-down", "{3}", "Creature", "", 2, 2))
        thinner.hidden = db("Skinthinner")
        wurm = self.game.enter_battlefield(self.b, db("Craw Wurm"))
        from mtgsim.face_states import turn_up
        self.assertTrue(turn_up(self.game, thinner))
        self.game.settle()
        self.assertNotIn(wurm, self.b.battlefield)          # "When ~ is turned face up, destroy target nonblack ..."

    def test_backslide_ai_turns_their_morph_creature_down(self):
        theirs = self.game.enter_battlefield(self.b, db("Skinthinner"))
        mine = self.game.enter_battlefield(self.a, db("Skinthinner"))
        for _ in range(2):
            self.game.enter_battlefield(self.a, ISLAND)
        self.a.hand = [db("Backslide")]
        self.assertTrue(self.game.cast(self.a, self.a.hand[0]))
        self.game.settle()
        self.assertEqual((theirs.card.name, theirs.power), ("Face-down creature", 2))
        self.assertEqual(theirs.hidden.name, "Skinthinner")
        self.assertEqual(mine.card.name, "Skinthinner")

    def test_wall_of_deceit_turns_itself_down_and_morphs_back(self):
        wall = self.game.enter_battlefield(self.a, db("Wall of Deceit"))
        for _ in range(4):
            self.game.enter_battlefield(self.a, ISLAND)
        self.assertTrue(self.game.activate_ability(self.a, wall, 0))
        self.game.settle()
        self.assertEqual(wall.card.name, "Face-down creature")
        self.game.turn_face_up(self.a)          # its morph {U} with the Island left
        self.assertEqual(wall.card.name, "Wall of Deceit")


if __name__ == "__main__":
    unittest.main()

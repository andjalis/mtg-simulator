"""#407: "If it would leave the battlefield, exile it instead of putting it anywhere else" on a reanimated
permanent (mtgsim.cx_replace_zones)."""
import unittest

from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

GIANT = card("Test Giant", "{4}", "Creature — Giant", "", 4, 4)
SENTENCE = "If it would leave the battlefield, exile it instead of putting it anywhere else."
QUOTED = 'It gains "If ~ would leave the battlefield, exile it instead of putting it anywhere else."'


class Parsing(unittest.TestCase):
    def test_sentence_and_quoted_grant(self):
        for rider in (SENTENCE, QUOTED,
                      "If that creature would leave the battlefield, exile it instead of putting it anywhere else."):
            effects, bad = _parse_effects("Return target creature card from your graveyard to the battlefield. " + rider)
            self.assertEqual(bad, [], rider)
            self.assertEqual([e.kind for e in effects], ["cx_bf_watch", "reanimate_one", "cx_leave_exile"])

    def test_refusals(self):
        for text in ("Draw a card. " + SENTENCE,                                         # nothing entered
                     "Return target creature card from your graveyard to the battlefield. Return target creature card "
                     "from your graveyard to the battlefield. " + SENTENCE,               # which one?
                     SENTENCE):
            effects, bad = _parse_effects(text)
            self.assertTrue(bad, text)
            self.assertNotIn("cx_leave_exile", [e.kind for e in effects])


class Engine(Base):
    def reanimate(self, rider=SENTENCE):
        effects, bad = _parse_effects("Return target creature card from your graveyard to the battlefield. " + rider)
        self.assertEqual(bad, [])
        self.a.graveyard = [GIANT]
        self.game.stack.append(StackItem(self.a, effects, [None] * len(effects), name="test", kind="trigger"))
        self.game.resolve_top()
        return next(x for x in self.a.battlefield if x.card.name == "Test Giant")

    def test_dies_to_exile(self):
        giant = self.reanimate()
        bear = self.perm(BEAR, self.a)
        self.game.destroy(giant)
        self.game.destroy(bear)
        self.game.state_based_actions()
        self.assertEqual([c.name for c in self.a.exile], ["Test Giant"])
        self.assertEqual([c.name for c in self.a.graveyard], [BEAR.name])     # an unmarked permanent dies normally

    def test_bounce_goes_to_exile_too(self):
        giant = self.reanimate(QUOTED)
        self.game.leave_battlefield(giant, "hand")
        self.assertEqual(([c.name for c in self.a.exile], self.a.hand), (["Test Giant"], []))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def test_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Gruesome Encore", "Moira and Teshar", "Whip of Erebos", "Geth, Thane of Contracts"):
            with self.subTest(name):
                self.assertEqual(db.get(name).unsupported, [])

    def test_whip_of_erebos(self):
        from mtgsim.carddb import CardDB
        whip = CardDB(offline=True).get("Whip of Erebos")
        source = self.perm(whip, self.a)
        self.a.graveyard = [GIANT]
        effects = whip.activated[0].effects
        self.game.stack.append(StackItem(self.a, list(effects), [None] * len(effects), source=source,
                                         name="Whip", kind="trigger"))
        self.game.resolve_top()
        giant = next(x for x in self.a.battlefield if x.card.name == "Test Giant")
        self.assertTrue(giant.has("haste"))
        self.game.sacrifice(giant)
        self.assertEqual(([c.name for c in self.a.exile], [c.name for c in self.a.graveyard]), (["Test Giant"], []))


if __name__ == "__main__":
    unittest.main()

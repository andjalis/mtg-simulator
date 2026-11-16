"""#635 ENTER-TRANSFORMED: "return it / this card to the battlefield [transformed] [tapped] under your / its owner's
control", with "it" bound to what left the battlefield, and the returned card as the "it" of the effects after."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


class Parse(unittest.TestCase):
    def test_wordings(self):
        effects, bad = _parse_effects("Return it to the battlefield transformed under your control.")
        self.assertEqual(bad, [])
        self.assertEqual((effects[0].kind, effects[0].target, effects[0].data["transformed"], effects[0].data["it"]),
                         ("return_self_bf", "prev", True, True))
        effects, bad = _parse_effects("Return this card to the battlefield tapped under its owner's control.")
        self.assertEqual((effects[0].target, effects[0].data["owner"], effects[0].data["tapped"]), ("none", True, True))

    def test_refusals(self):
        # the delayed "at the beginning of the next end step" forms belong to cx_delay, not to this kind
        effects, _ = _parse_effects("Return it to the battlefield transformed under your control at the beginning of "
                                    "the next end step.")
        self.assertFalse(any(e.kind == "return_self_bf" for e in effects))

    def test_real_cards_full(self):
        for name in ("Harvest Hand // Scrounged Scythe", "Skin Invasion // Skin Shedder", "Come Back Wrong",
                     "Vindictive Triumph", "Tenacious Dead", "Retched Wretch", "Journey to Eternity // Atzal, Cave of Eternity"):
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
            p.my_turn = p is self.a

    def names(self, p):
        return sorted(x.card.name for x in p.battlefield if not x.card.is_land)

    def resolve(self, name, targets):
        c = db(name)
        effects = list(c.spell_effects)
        self.game.stack.append(StackItem(self.a, effects, list(targets) + [None] * (len(effects) - len(targets)),
                                         card=c, name=c.name))
        self.game.resolve_top()
        self.game.settle()

    def test_harvest_hand_returns_transformed_and_back(self):
        hand = self.game.enter_battlefield(self.a, db("Harvest Hand // Scrounged Scythe"))
        self.game.destroy(hand)
        self.game.settle()
        scythe = next(x for x in self.a.battlefield if x.card.name == "Scrounged Scythe")
        self.game.transform(scythe)              # it remembers its front face
        self.assertEqual(scythe.card.name, "Harvest Hand")

    def test_aura_this_card_vs_it(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        for land in (SWAMP, SWAMP, FOREST):        # {1}{B}{G}
            self.game.enter_battlefield(self.a, land)
        journey = db("Journey to Eternity // Atzal, Cave of Eternity")
        self.a.hand = [journey]
        self.assertTrue(self.game.cast(self.a, journey, [bear]))
        self.game.settle()
        self.game.destroy(bear)
        self.game.settle()
        # "return it" is the creature, "return this card ... transformed" the Aura (a land back face, #790)
        self.assertIn("Grizzly Bears", self.names(self.a))
        self.assertIn("Atzal, Cave of Eternity", [x.card.name for x in self.a.battlefield])

    def test_come_back_wrong_returns_then_sacrifices_the_returned_creature(self):
        wurm = self.game.enter_battlefield(self.b, db("Craw Wurm"))
        self.resolve("Come Back Wrong", [wurm])
        self.assertEqual(self.names(self.a), ["Craw Wurm"])
        self.game.begin_end_step(self.a)
        self.game.settle()
        self.assertEqual(self.names(self.a), [])
        self.assertIn("Craw Wurm", [c.name for c in self.b.graveyard])

    def test_vindictive_triumph_mana_value_bands(self):
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.resolve("Vindictive Triumph", [bear])
        back = [x for x in self.a.creatures if x.card.name == "Grizzly Bears"]
        self.assertTrue(back and back[0].tapped)
        self.game.begin_end_step(self.a)
        self.game.settle()
        self.assertIn("Grizzly Bears", [c.name for c in self.b.exile])
        wurm = self.game.enter_battlefield(self.b, db("Craw Wurm"))
        self.resolve("Vindictive Triumph", [wurm])
        self.assertNotIn("Craw Wurm", self.names(self.a))

    def test_retched_wretch_returns_without_abilities(self):
        wretch = self.game.enter_battlefield(self.a, db("Retched Wretch"))
        wretch.counters["-1/-1"] = 1
        self.game.destroy(wretch)
        self.game.settle()
        back = next(x for x in self.a.battlefield if x.card.name == "Retched Wretch")
        self.assertTrue(back.abilities_suppressed)


if __name__ == "__main__":
    unittest.main()

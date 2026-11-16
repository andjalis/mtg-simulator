"""#839 'you may cast/play': impulse "cast" permissions after exiling the top of a library (no lands), and "you may
cast target red instant or sorcery card from your graveyard [this turn]" (the colour covers the whole phrase)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card

MOUNTAIN = card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


class Parse(unittest.TestCase):
    def kinds(self, text):
        effects, bad = _parse_effects(text)
        return [(e.kind, e.amount, e.data.get("cast_only", False)) for e in effects], bad

    def test_impulse_cast_and_play(self):
        self.assertEqual(self.kinds("Exile the top card of your library. You may cast that card this turn."),
                         ([("exile_top", 1, False), ("may_play_exiled", 0, True)], []))
        self.assertEqual(self.kinds("Exile the top three cards of your library. Until end of turn, you may play cards "
                                    "exiled this way."), ([("exile_top", 3, False), ("may_play_exiled", 0, False)], []))
        self.assertEqual(self.kinds("Exile the top two cards of your library. Until the end of your next turn, you may "
                                    "cast those cards."), ([("exile_top", 2, False), ("may_play_exiled", 2, True)], []))

    def test_refusals(self):
        # not after a top-of-library exile; the immediate "You may cast that card." (then "If you don't, ...")
        self.assertTrue(_parse_effects("Exile target creature. You may cast it this turn.")[1])
        self.assertTrue(_parse_effects("Exile the top card of your library. You may cast that card.")[1])
        self.assertTrue(_parse_effects("Exile the top card of your library. If it's red, you may cast it this turn.")[1])

    def test_graveyard_cast_colour(self):
        effects, bad = _parse_effects("You may cast target red instant or sorcery card from your graveyard. If that "
                                      "spell would be put into your graveyard, exile it instead.")
        self.assertEqual(bad, [])
        e, = effects
        self.assertEqual((e.kind, e.data["desc"], e.data["color"], e.data["gy_instead"]),
                         ("gy_cast", "instant or sorcery", "red", "exile"))
        self.assertEqual(_parse_effects("You may cast target instant or sorcery card from your graveyard this turn.")
                         [0][0].kind, "gy_cast")


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Play(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        self.game.active_idx = 0
        self.a.my_turn, self.b.my_turn = True, False
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def resolve(self, text):
        effects, bad = _parse_effects(text)
        self.assertEqual(bad, [])
        self.game.stack.append(StackItem(self.a, effects, [None] * len(effects), name="test"))
        self.game.resolve_top()
        self.game.settle()

    def test_cast_permission_takes_spells_not_lands(self):
        bolt = db("Lightning Bolt")
        self.a.library = [ISLAND] * 5 + [MOUNTAIN, bolt]
        self.resolve("Exile the top two cards of your library. Until end of turn, you may cast those cards.")
        self.assertEqual(self.game.impulse_cards(self.a), [bolt])           # the Mountain can't be cast
        self.game.enter_battlefield(self.a, MOUNTAIN).sick = False
        option = next(o for o in self.game.spell_options(self.a) if o.name.startswith("Lightning Bolt"))
        self.assertTrue(self.game.cast(self.a, option, [self.b]))
        self.game.settle()
        self.assertEqual(self.b.life, 17)

    def test_play_permission_keeps_lands(self):
        self.a.library = [ISLAND] * 5 + [MOUNTAIN]
        self.resolve("Exile the top card of your library. Until end of turn, you may play cards exiled this way.")
        self.assertEqual([c.name for c in self.game.impulse_cards(self.a)], ["Mountain"])

    def test_cast_permission_expires(self):
        bolt = db("Lightning Bolt")
        self.a.library = [ISLAND] * 5 + [bolt]
        self.resolve("Exile the top card of your library. You may cast that card this turn.")
        self.assertEqual(self.game.impulse_cards(self.a), [bolt])
        self.game.turn += 1
        self.assertEqual(self.game.impulse_cards(self.a), [])

    def test_chandra_flames_catalyst_casts_only_red(self):
        pw = self.game.enter_battlefield(self.a, db("Chandra, Flame's Catalyst"))
        self.game.settle()
        for _ in range(3):
            self.game.enter_battlefield(self.a, MOUNTAIN).sick = False
        self.a.graveyard = [db("Divination"), db("Lightning Bolt")]
        idx = next(i for i, (cost, _) in enumerate(pw.card.loyalty_abilities) if cost == -2)
        self.assertTrue(self.game.activate_loyalty(self.a, pw, idx))
        self.game.settle()
        self.assertEqual(self.b.life, 17)                                     # Bolt, not the blue Divination
        self.assertEqual([c.name for c in self.a.exile], ["Lightning Bolt"])   # exiled instead of the graveyard
        self.assertEqual([c.name for c in self.a.graveyard], ["Divination"])

    def test_jace_telepath_unbound_minus_three(self):
        jace = db("Jace, Vryn's Prodigy // Jace, Telepath Unbound").back
        pw = self.game.enter_battlefield(self.a, jace)
        self.game.settle()
        for _ in range(2):
            self.game.enter_battlefield(self.a, MOUNTAIN).sick = False
        self.a.graveyard = [db("Lightning Bolt")]
        idx = next(i for i, (cost, _) in enumerate(pw.card.loyalty_abilities) if cost == -3)
        self.assertTrue(self.game.activate_loyalty(self.a, pw, idx))
        self.game.settle()
        self.assertEqual([c.name for c in self.a.exile], ["Lightning Bolt"])
        self.assertEqual(self.a.graveyard, [])


if __name__ == "__main__":
    unittest.main()

"""#839: static emblem bodies. Anthems and keyword grants ("Creatures you control get +2/+2 and have flying.") live
on a command-zone emblem read through the residual source index; "You have no maximum hand size." is the permanent
player flag. Also: "Creatures you control get +N/+N" no longer parses as the subtype "Creature" (Ajani Resolute's
emblem pumped nothing while the card counted full)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


def walker(body):
    return card("Test Walker", "{3}{W}", "Legendary Planeswalker — Test",
                f"+1: You gain 1 life.\n−7: You get an emblem with \"{body}\"")


def ultimate(c):
    return min(c.loyalty_abilities, key=lambda a: a[0])[1]


class Parse(unittest.TestCase):
    def test_anthem_bodies(self):
        e, = ultimate(walker("Creatures you control get +2/+2 and have flying."))
        self.assertEqual(e.kind, "emblem_obj")
        self.assertEqual([(pp, tt) for _, pp, tt in e.data["static"]["anthems"]], [(2, 2)])
        self.assertEqual([kws for _, kws in e.data["static"]["grants"]], [("flying",)])
        e, = ultimate(walker("Creatures you control get +1/+1."))          # was kind 'emblem', subtype 'Creature'
        self.assertEqual((e.kind, [(pp, tt) for _, pp, tt in e.data["static"]["anthems"]]), ("emblem_obj", [(1, 1)]))
        e, = ultimate(walker("Ninjas you control get +1/+1."))              # a real subtype: the older emblem kind
        self.assertEqual((e.kind, e.data["subtype"]), ("emblem", "Ninja"))

    def test_no_maximum_hand_size(self):
        e, = ultimate(walker("You have no maximum hand size."))
        self.assertEqual((e.kind, e.data["flag"], e.data["forever"]), ("cx_player_flag", "no_max_hand", True))

    def test_period_inside_the_quote_then_another_sentence(self):
        c = card("Test Walker", "{3}{G}", "Legendary Planeswalker — Test", "+1: You gain 1 life.\n−8: You get an "
                 "emblem with \"Lands you control have indestructible.\" Search your library for a Forest card, put "
                 "it onto the battlefield tapped, then shuffle.")
        self.assertEqual([e.kind for e in ultimate(c)][0], "emblem_obj")

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_real_cards(self):
        for name in ("Elspeth, Sun's Champion", "Ajani Resolute", "Gideon, Ally of Zendikar", "Vivien Reid",
                     "Wrenn and Seven"):
            self.assertTrue(db(name).fully_supported, name)


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

    def put(self, p, c):
        x = self.game.enter_battlefield(p, db(c) if isinstance(c, str) else c)
        self.game.settle()
        return x

    def ult(self, name):
        pw = self.put(self.a, name)
        idx = min(range(len(pw.card.loyalty_abilities)), key=lambda i: pw.card.loyalty_abilities[i][0])
        pw.counters["loyalty"] = -pw.card.loyalty_abilities[idx][0]
        self.assertTrue(self.game.activate_loyalty(self.a, pw, idx))
        self.game.settle()
        self.assertNotIn(pw, self.a.battlefield)                     # 0 loyalty: gone; the emblem stays
        return pw

    def test_elspeth_anthem_and_flying_for_mine_only(self):
        mine, theirs = self.put(self.a, BEAR), self.put(self.b, BEAR)
        self.ult("Elspeth, Sun's Champion")
        later = self.put(self.a, BEAR)
        for x in (mine, later):
            self.assertEqual((x.power, x.toughness, x.has("flying")), (4, 4, True))
        self.assertEqual((theirs.power, theirs.toughness, theirs.has("flying")), (2, 2, False))
        self.assertEqual(len(self.a.command), 1)

    def test_ajani_resolute_pumps_creatures(self):
        bear = self.put(self.a, BEAR)
        self.ult("Ajani Resolute")
        self.assertEqual((bear.power, bear.toughness), (4, 4))

    def test_keywords_only(self):
        bear = self.put(self.a, BEAR)
        self.ult("Domri Rade")
        self.assertTrue(all(bear.has(k) for k in ("double strike", "trample", "hexproof", "haste")))
        self.assertEqual(bear.power, 2)

    def test_emblem_survives_a_wrath(self):
        self.ult("Ajani Resolute")
        wrath = card("Test Wrath", "{2}{W}{W}", "Sorcery", "Destroy all creatures.")
        from mtgsim.engine import StackItem
        self.game.stack.append(StackItem(self.a, list(wrath.spell_effects), [None] * len(wrath.spell_effects),
                                         card=wrath, name=wrath.name))
        self.game.resolve_top()
        self.game.settle()
        bear = self.put(self.a, BEAR)
        self.assertEqual(bear.power, 4)

    def test_wrenn_and_seven_no_maximum_hand_size(self):
        from mtgsim.cx_next_turn import player_flag
        self.ult("Wrenn and Seven")
        self.game.turn += 3
        self.assertTrue(player_flag(self.game, self.a, "no_max_hand"))
        self.assertFalse(player_flag(self.game, self.b, "no_max_hand"))

    def test_ai_values_an_anthem_emblem(self):
        from mtgsim.engine.policy import _mode_value
        self.put(self.a, BEAR)
        self.assertGreater(_mode_value(self.game, self.a, ultimate(db("Elspeth, Sun's Champion"))), 0)


if __name__ == "__main__":
    unittest.main()

"""#839 (opus-cast slice): "−X" loyalty costs. The X is chosen on activation (0..loyalty), X loyalty counters are
removed, and the ability's X effects read it like a spell's X."""
import unittest

from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import card, BEAR


def walker(text, loyalty=4, name="Test Walker"):
    return card_from_scryfall({"name": name, "mana_cost": "{3}{R}", "cmc": 4, "type_line": "Legendary Planeswalker — Test",
                               "oracle_text": text, "loyalty": str(loyalty)})


NALAAR = walker("+1: Test Walker deals 1 damage to target player or planeswalker.\n"
                "−X: Test Walker deals X damage to target creature.")
OGRE = card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)


class Parse(unittest.TestCase):
    def test_minus_x(self):
        self.assertEqual(NALAAR.loyalty_x, frozenset({1}))
        cost, effects = NALAAR.loyalty_abilities[1]
        self.assertEqual((cost, effects[0].kind, effects[0].data.get("x")), (0, "damage", True))
        self.assertEqual(NALAAR.unsupported, [])

    def test_plus_x_refused(self):
        c = walker("+X: Draw X cards.")
        self.assertEqual(c.loyalty_abilities, [])
        self.assertTrue(any("+X" in u for u in c.unsupported))


class Activation(Base):
    def setUp(self):
        super().setUp()
        self.game.turn, self.game.step = 3, "main1"
        self.game.active_idx = 0
        self.pw = Permanent(NALAAR, self.a)
        self.pw.counters["loyalty"] = 4
        self.ogre = Permanent(OGRE, self.b)
        self.a.battlefield, self.b.battlefield = [self.pw], [self.ogre]

    def test_x_paid_and_dealt(self):
        self.assertTrue(self.game.activate_loyalty(self.a, self.pw, 1, [self.ogre], x=3))
        self.game.settle()
        self.assertEqual(self.pw.loyalty, 1)
        self.assertNotIn(self.ogre, self.b.battlefield)

    def test_x_cannot_exceed_loyalty(self):
        self.assertFalse(self.game.activate_loyalty(self.a, self.pw, 1, [self.ogre], x=5))
        self.assertEqual(self.pw.loyalty, 4)
        self.assertFalse(self.pw.loyalty_used)

    def test_once_per_turn(self):
        self.assertTrue(self.game.activate_loyalty(self.a, self.pw, 1, [self.ogre], x=1))
        self.game.settle()
        self.assertFalse(self.game.activate_loyalty(self.a, self.pw, 0, [self.b]))

    def test_sorcery_speed(self):
        self.game.active_idx = 1
        self.assertFalse(self.game.activate_loyalty(self.a, self.pw, 1, [self.ogre], x=3))
        self.game.active_idx = 0
        self.game.step = "combat"
        self.assertFalse(self.game.activate_loyalty(self.a, self.pw, 1, [self.ogre], x=3))

    def test_dies_at_zero(self):
        self.assertTrue(self.game.activate_loyalty(self.a, self.pw, 1, [self.ogre], x=4))
        self.game.settle()
        self.assertNotIn(self.pw, self.a.battlefield)
        self.assertNotIn(self.ogre, self.b.battlefield)

    def test_default_x_is_the_smallest_that_kills(self):
        """With no X given, X is chosen: the smallest X that kills the 3/3, keeping the rest of the loyalty."""
        self.assertTrue(self.game.activate_loyalty(self.a, self.pw, 1))
        self.game.settle()
        self.assertNotIn(self.ogre, self.b.battlefield)
        self.assertEqual(self.pw.loyalty, 1)


class AI(Base):
    def setUp(self):
        super().setUp()
        self.game.turn, self.game.step = 3, "main1"
        self.game.active_idx = 0

    def board(self, theirs):
        pw = Permanent(NALAAR, self.a)
        pw.counters["loyalty"] = 4
        self.a.battlefield, self.b.battlefield = [pw], theirs
        return pw

    def test_ai_kills_a_threat_with_minus_x(self):
        ogre = Permanent(OGRE, self.b)
        pw = self.board([ogre])
        self.assertEqual(self.a.ai.choose_loyalty(self.game, self.a, pw), 1)
        self.a.ai.use_abilities(self.game, self.a)
        self.game.settle()
        self.assertNotIn(ogre, self.b.battlefield)
        self.assertEqual(pw.loyalty, 1)

    def test_ai_ticks_up_with_nothing_to_kill(self):
        pw = self.board([])
        self.assertEqual(self.a.ai.choose_loyalty(self.game, self.a, pw), 0)

    def test_ai_does_not_overpay(self):
        bear = Permanent(BEAR, self.b)
        pw = self.board([bear])
        self.a.ai.use_abilities(self.game, self.a)
        self.game.settle()
        if bear not in self.b.battlefield:
            self.assertEqual(pw.loyalty, 2)        # X = 2 for a 2/2, not all four


UGIN = walker("+2: Test Ugin deals 3 damage to any target.\n"
              "−X: Exile each permanent with mana value X or less that's one or more colors.", loyalty=7, name="Test Ugin")
ROCK = card("Test Rock", "{3}", "Artifact", "")


class Ugin(Base):
    def setUp(self):
        super().setUp()
        self.game.turn, self.game.step = 3, "main1"
        self.game.active_idx = 0

    def test_parse(self):
        self.assertEqual(UGIN.loyalty_x, frozenset({1}))
        eff = UGIN.loyalty_abilities[1][1][0]
        self.assertEqual((eff.kind, eff.data["op"], eff.data.get("stat_x")), ("group_remove", "exile", True))

    def test_exiles_colored_permanents_up_to_x(self):
        pw = Permanent(UGIN, self.a)
        pw.counters["loyalty"] = 7
        ogre, giant, rock = Permanent(OGRE, self.b), Permanent(card("Test Giant", "{4}{G}", "Creature — Giant", "", 5, 5),
                                                                self.b), Permanent(ROCK, self.b)
        self.a.battlefield, self.b.battlefield = [pw], [ogre, giant, rock]
        self.assertTrue(self.game.activate_loyalty(self.a, pw, 1, x=3))
        self.game.settle()
        self.assertEqual(pw.loyalty, 4)
        self.assertNotIn(ogre, self.b.battlefield)          # red, MV 3
        self.assertIn(giant, self.b.battlefield)            # MV 5
        self.assertIn(rock, self.b.battlefield)             # colorless

    def test_ai_sweeps_their_board(self):
        pw = Permanent(UGIN, self.a)
        pw.counters["loyalty"] = 7
        ogres = [Permanent(OGRE, self.b) for _ in range(3)]
        self.a.battlefield, self.b.battlefield = [pw], list(ogres)
        self.assertEqual(self.a.ai.choose_loyalty(self.game, self.a, pw), 1)
        self.a.ai.use_abilities(self.game, self.a)
        self.game.settle()
        self.assertFalse(any(o in self.b.battlefield for o in ogres))
        self.assertEqual(pw.loyalty, 4)                     # X = 3: enough for the MV-3 Ogres


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        from mtgsim.coverage import card_coverage
        for name in ("Chandra Nalaar", "Chandra, Flamecaller", "Tezzeret the Seeker", "Ugin, the Spirit Dragon"):
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)
        for name in ("Chandra Nalaar", "Sorin, Grim Nemesis", "Chandra, Flamecaller", "Tibalt, Wicked Tormentor"):
            c = db.get(name)
            self.assertEqual(len(c.loyalty_x), 1, name)
            (idx,) = c.loyalty_x
            self.assertTrue(any(e.data.get("x") for e in c.loyalty_abilities[idx][1]), name)


if __name__ == "__main__":
    unittest.main()

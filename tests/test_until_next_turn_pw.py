"""#839 (opus-cast slice): "until your next turn" on planeswalker abilities.
- "Until your next turn, whenever <event>, <effects>": a delayed trigger watched until the controller's next turn.
- "Until your next turn, prevent all damage that would be dealt to and dealt by target permanent an opponent
  controls" (Dovin, Hand of Control; Kiora, the Tide's Fury) and "... target permanent would deal" (Gideon of the
  Trials): a damage shield that lasts until the controller's next turn."""
import unittest

from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import card

OGRE = card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)


def walker(text, loyalty=4, name="Test Walker"):
    return card_from_scryfall({"name": name, "mana_cost": "{2}{U}", "cmc": 3, "type_line": "Legendary Planeswalker — Test",
                               "oracle_text": text, "loyalty": str(loyalty)})


SHIELD = walker("−1: Until your next turn, prevent all damage that would be dealt to and dealt by target permanent an "
                "opponent controls.", 5)
WATCH = walker("+1: Until your next turn, whenever a creature an opponent controls attacks, it gets -1/-0 until end of "
               "turn.")


class Parse(unittest.TestCase):
    def test_shield(self):
        eff = SHIELD.loyalty_abilities[0][1][0]
        self.assertEqual((eff.kind, eff.target, eff.data.get("until_next_turn"), eff.data["selector"]),
                         ("cx_shield", "permanent", True, {"controller": "opp"}))
        self.assertEqual(SHIELD.unsupported, [])

    def test_watch(self):
        eff = WATCH.loyalty_abilities[0][1][0]
        self.assertEqual((eff.kind, eff.data.get("next_turn_watch")), ("cx_turn_trigger", True))
        self.assertEqual(WATCH.unsupported, [])

    def test_refusal_head_naming_the_source(self):
        c = walker("+1: Until your next turn, whenever a creature deals combat damage to Test Walker, destroy that "
                   "creature.")
        self.assertTrue(c.unsupported)


class Lifetime(Base):
    def setUp(self):
        super().setUp()
        self.game.turn, self.game.step = 3, "main1"
        self.game.active_idx = 0

    def next_turn(self):
        self.game.turn += 1
        self.game.active_idx = 1 - self.game.active_idx

    def test_shield_lasts_until_my_next_turn(self):
        pw = Permanent(SHIELD, self.a)
        pw.counters["loyalty"] = 5
        ogre = Permanent(OGRE, self.b)
        self.a.battlefield, self.b.battlefield = [pw], [ogre]
        self.assertTrue(self.game.activate_loyalty(self.a, pw, 0, [ogre]))
        self.game.settle()
        self.assertEqual(pw.loyalty, 4)
        self.next_turn()                                     # their turn: no damage to or by it
        self.game.deal_damage(ogre, 5, by=self.a)
        self.game.deal_damage(self.a, 3, by=self.b, source=ogre)
        self.assertEqual((ogre.damage, self.a.life), (0, 20))
        self.next_turn()                                     # my next turn: the shield is gone
        self.game.deal_damage(self.a, 3, by=self.b, source=ogre)
        self.assertEqual(self.a.life, 17)

    def test_watch_lasts_through_their_turn(self):
        pw = Permanent(WATCH, self.a)
        pw.counters["loyalty"] = 4
        self.a.battlefield = [pw]
        self.assertTrue(self.game.activate_loyalty(self.a, pw, 0))
        self.game.settle()
        from mtgsim import cx_trig_turn
        self.assertEqual(len(cx_trig_turn.watchers(self.game)), 1)
        self.next_turn()
        self.assertEqual(len(cx_trig_turn.watchers(self.game)), 1)
        self.next_turn()
        self.assertEqual(cx_trig_turn.watchers(self.game), [])

    def test_ai_uses_the_shield_on_their_creature(self):
        pw = Permanent(SHIELD, self.a)
        pw.counters["loyalty"] = 5
        ogre = Permanent(OGRE, self.b)
        self.a.battlefield, self.b.battlefield = [pw], [ogre]
        self.a.ai.use_abilities(self.game, self.a)
        self.game.settle()
        self.assertEqual(pw.loyalty, 4)
        self.game.deal_damage(self.a, 3, by=self.b, source=ogre)
        self.assertEqual(self.a.life, 20)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Dovin, Hand of Control", "Kiora, the Tide's Fury"):
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)


if __name__ == "__main__":
    unittest.main()

"""Audit 2026-11-16 (opus-cast), round 3:
- "Untap ~ and put a +1/+1 counter on it": "it" after an untargeted ~ effect had no referent (Grimgrin and 4 more).
- Wormfang Behemoth: the hand it exiled on entry never came back when it left (no link from the zone exile)."""
import unittest

from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, ISLAND, card

GRIM = card("Test Grim", "{3}{U}{B}", "Creature — Zombie Warrior", "Sacrifice another creature: Untap ~ and put a "
            "+1/+1 counter on it.", 5, 5)
WORMFANG = card("Test Wormfang", "{3}{U}{U}", "Creature — Nightmare Fish Beast", "When this creature enters, exile all "
                "cards from your hand.\nWhen this creature leaves the battlefield, return the exiled cards to their "
                "owner's hand.", 5, 5)


class SelfThenIt(Base):
    def test_untap_self_then_counter_on_it(self):
        grim = self.perm(GRIM, self.a)
        grim.tapped = True
        self.perm(BEAR, self.a)
        self.assertTrue(self.game.activate_ability(self.a, grim, 0))
        self.game.settle()
        self.assertFalse(grim.tapped)
        self.assertEqual(grim.counters.get("+1/+1"), 1)


class ExiledHandReturns(Base):
    def test_bounced(self):
        self.a.hand = [BEAR, ISLAND]
        w = self.game.enter_battlefield(self.a, WORMFANG)
        self.game.settle()
        self.assertEqual(self.a.hand, [])
        self.game.leave_battlefield(w, "hand")
        self.game.settle()
        self.assertEqual(sorted(c.name for c in self.a.hand), ["Grizzly Bears", "Island", "Test Wormfang"])

    def test_dies(self):
        self.a.hand = [BEAR]
        w = self.game.enter_battlefield(self.a, WORMFANG)
        self.game.settle()
        self.game.destroy(w)
        self.game.settle()
        self.assertEqual([c.name for c in self.a.hand], ["Grizzly Bears"])

    def test_a_card_that_left_exile_stays_where_it_is(self):
        self.a.hand = [BEAR]
        w = self.game.enter_battlefield(self.a, WORMFANG)
        self.game.settle()
        self.a.exile.remove(self.a.exile[0])
        self.game.destroy(w)
        self.game.settle()
        self.assertEqual(self.a.hand, [])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def test_grimgrin(self):
        from mtgsim.carddb import CardDB
        grim = self.game.enter_battlefield(self.a, CardDB(offline=True).get("Grimgrin, Corpse-Born"))
        self.perm(BEAR, self.a)
        self.game.settle()
        self.game.activate_ability(self.a, grim, 0)
        self.game.settle()
        self.assertEqual((grim.tapped, grim.counters.get("+1/+1")), (False, 1))


if __name__ == "__main__":
    unittest.main()

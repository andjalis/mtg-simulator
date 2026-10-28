"""O4 round 1: graveyard self-return triggers worded "return this card from your graveyard"."""
import unittest

from tests.test_templates import MOUNTAIN, SANCTIFIER, SWAMP, Base, card

GHAST = card("Bloodghast", "{B}{B}", "Creature — Vampire Spirit", "This creature can't block.\nLandfall — "
             "Whenever a land you control enters, you may return this card from your graveyard to the battlefield.", 2, 1)
FIREBIRD = card("Akoum Firebird", "{2}{R}{R}", "Creature — Phoenix", "Flying, haste\nLandfall — Whenever a land you "
                "control enters, you may pay {4}{R}{R}. If you do, return this card from your graveyard to the "
                "battlefield.", 3, 3)
MINER = card("Forsaken Miner", "{B}", "Creature — Skeleton Rogue", "This creature can't block.\nWhenever you commit "
             "a crime, you may pay {B}. If you do, return this card from your graveyard to the battlefield.", 2, 2)
# Still unsupported: an intervening "if" before the return.
ARCLIGHT = card("Test Phoenix", "{3}{R}", "Creature — Phoenix", "At the beginning of combat on your turn, if you've "
                "cast three or more instant and sorcery spells this turn, return this card from your graveyard to "
                "the battlefield.", 3, 2)


class GraveyardSelfReturn(Base):
    def names(self, player):
        return [c.card.name for c in player.creatures]

    def test_templates(self):
        for c in (GHAST, FIREBIRD, MINER):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
                self.assertEqual(len(c.gy_triggers), 1)
                self.assertEqual(c.triggers, [])
        self.assertEqual([e.kind for e in FIREBIRD.gy_triggers[0].effects], ["pay_gate", "return_self_gy"])

    def test_intervening_if_stays_unsupported(self):
        self.assertEqual(len(ARCLIGHT.unsupported), 1)
        self.assertEqual(ARCLIGHT.gy_triggers, [])

    def test_landfall_returns_this_card(self):
        self.a.graveyard = [GHAST]
        self.game.enter_battlefield(self.a, SWAMP)
        self.game.settle()
        self.assertEqual(self.names(self.a), ["Bloodghast"])
        self.assertEqual(self.a.graveyard, [])

    def test_opponents_land_does_not_trigger(self):
        self.a.graveyard = [GHAST]
        self.game.enter_battlefield(self.b, SWAMP)
        self.game.settle()
        self.assertEqual((self.names(self.a), self.a.graveyard), ([], [GHAST]))

    def test_paid_return_needs_the_mana(self):
        self.a.graveyard = [FIREBIRD]
        self.game.enter_battlefield(self.a, MOUNTAIN)
        self.game.settle()
        self.assertEqual((self.names(self.a), self.a.graveyard), ([], [FIREBIRD]))
        for _ in range(6):
            self.perm(MOUNTAIN, self.a)
        self.game.enter_battlefield(self.a, MOUNTAIN)
        self.game.settle()
        self.assertEqual(self.names(self.a), ["Akoum Firebird"])
        self.assertEqual(sum(x.tapped for x in self.a.battlefield), 6)

    def test_crime_trigger_pays_and_returns(self):
        self.perm(SWAMP, self.a)
        self.a.graveyard = [MINER]
        self.game.fire(self.a, "crime")
        self.game.settle()
        self.assertEqual(self.names(self.a), ["Forsaken Miner"])

    def test_return_triggers_enters_abilities(self):
        self.perm(SANCTIFIER, self.a)
        self.a.graveyard = [GHAST]
        self.game.enter_battlefield(self.a, SWAMP)
        self.game.settle()
        self.assertIn("Bloodghast", self.names(self.a))
        self.assertEqual(self.a.life, 21)


if __name__ == "__main__":
    unittest.main()

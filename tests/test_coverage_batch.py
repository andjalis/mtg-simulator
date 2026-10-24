"""Coverage batch: Snarls and Thriving lands, searches with a mana value and for a named card, transmute,
reinforce, dethrone, training, melee, outlast and amplify."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

SNARL = card("Test Snarl", "", "Land", "As ~ enters, you may reveal a Forest or Island card from your hand. If you "
                                       "don't, ~ enters tapped.\n{T}: Add {G} or {U}.")
THRIVING = card("Test Thriving", "", "Land", "~ enters tapped.\nAs ~ enters, choose a color other than red.\n{T}: Add {R} "
                                             "or one mana of the chosen color.")
FOREST = card("Forest", "", "Basic Land — Forest", "({T}: Add {G}.)")
REBEL = card("Test Rebel", "{1}{W}", "Creature — Human Rebel", "{2}, {T}: Search your library for a Rebel permanent card "
             "with mana value 2 or less, put it onto the battlefield, then shuffle.", 1, 1)
SEEKER = card("Test Seeker", "{2}{W}", "Creature — Human", "When ~ enters, you may search your library and/or graveyard "
              "for a card named Test Rebel, reveal it, and put it into your hand. If you search your library this way, "
              "shuffle.", 2, 2)
LOOP = card("Test Transmuter", "{1}{U}{U}", "Instant", "Draw a card.\nTransmute {1}{U}{U}")
TROOPER = card("Test Trooper", "{1}{W}", "Creature — Human", "Reinforce 2—{1}{W}", 2, 2)
KING = card("Test Usurper", "{1}{B}", "Creature — Human", "Dethrone", 2, 2)
CADET = card("Test Cadet", "{W}", "Creature — Human", "Training", 1, 1)
DUELIST = card("Test Duelist", "{1}{R}", "Creature — Human", "Melee", 2, 2)
PATIENT = card("Test Patient", "{1}{W}", "Creature — Human", "Outlast {1}{W}", 1, 1)
LOUD = card("Test Loud", "{2}{R}", "Creature — Dwarf", "Amplify 1", 2, 2)


class CoverageBatch(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def test_templates(self):
        for c in (SNARL, THRIVING, REBEL, SEEKER, LOOP, TROOPER, KING, CADET, DUELIST, PATIENT, LOUD):
            self.assertEqual(c.unsupported, [], c.name)

    def test_snarl_and_thriving(self):
        self.a.hand[:] = []
        self.assertTrue(self.game.enter_battlefield(self.a, SNARL).tapped)
        self.a.hand[:] = [FOREST]
        self.assertFalse(self.game.enter_battlefield(self.a, SNARL).tapped)
        self.a.library = [card("Test Blue", "{U}{U}", "Sorcery", "Draw a card.")] * 10
        land = self.game.enter_battlefield(self.a, THRIVING)
        self.assertEqual(land.card.produces, frozenset({"R", "U"}))

    def test_searches(self):
        self.a.library = [BEAR, REBEL, ISLAND]
        rebel = self.put(self.a, REBEL)
        self.put(self.a, ISLAND)
        self.put(self.a, ISLAND)
        self.assertTrue(self.game.activate_ability(self.a, rebel, 0))
        self.game.settle()
        self.assertEqual(sum(x.card.name == REBEL.name for x in self.a.battlefield), 2)
        self.a.graveyard.append(REBEL)
        self.put(self.a, SEEKER)
        self.assertIn(REBEL, self.a.hand)

    def test_transmute_and_reinforce(self):
        self.a.library = [card("Test Three", "{2}{B}", "Sorcery", "Draw a card.")] + [ISLAND] * 5
        for _ in range(3):
            self.put(self.a, ISLAND)
        self.a.hand[:] = [LOOP] + [ISLAND] * 7
        self.game.cycle_spare(self.a)
        self.assertIn("Test Three", [c.name for c in self.a.hand])
        bear = self.put(self.a, BEAR)
        self.put(self.a, card("Test Plains", "", "Basic Land — Plains", "({T}: Add {W}.)"))
        for x in self.a.battlefield:
            x.tapped = False
        self.a.hand[:] = [TROOPER] + [ISLAND] * 7
        self.game.cycle_spare(self.a)
        self.assertEqual(bear.p1, 2)

    def test_attack_keywords(self):
        king, cadet, duelist = self.put(self.a, KING), self.put(self.a, CADET), self.put(self.a, DUELIST)
        self.a.ai.attack = [king, cadet, duelist]
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual((king.p1, cadet.p1), (1, 1))          # tied life: dethrone; a bigger attacker: training
        self.assertEqual(self.b.life, 20 - 3 - 2 - 3)

    def test_outlast_and_amplify(self):
        patient = self.put(self.a, PATIENT)
        self.put(self.a, card("Test Plains", "", "Basic Land — Plains", "({T}: Add {W}.)"))
        self.put(self.a, ISLAND)
        self.assertTrue(self.game.activate_ability(self.a, patient, 0))
        self.game.settle()
        self.assertEqual(patient.p1, 1)
        self.a.hand[:] = [card("Test Dwarf", "{R}", "Creature — Dwarf", "", 1, 1)] * 2
        self.assertEqual(self.put(self.a, LOUD).p1, 2)


if __name__ == "__main__":
    unittest.main()

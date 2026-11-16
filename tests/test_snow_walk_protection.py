"""#646 slice 9: snow landwalk (CR 702.14c) and protection from everything / monocolored / snow (CR 702.16)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent, can_block, protected_from
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, SHOCK, SWAMP, card

SNOW_SWAMP = card("Snow-Covered Swamp", types="Basic Snow Land — Swamp", text="({T}: Add {B}.)")
SNOW_FOREST = card("Snow-Covered Forest", types="Basic Snow Land — Forest", text="({T}: Add {G}.)")
LEGIONS = card("Test Legions", "{3}{B}", "Creature — Zombie", "Snow swampwalk", 2, 3)
MUSHER = card("Test Musher", "{3}{B}", "Snow Creature — Zombie", "Snow landwalk", 2, 3)
PROGENITUS = card("Test Progenitus", "{W}{W}{U}{U}{B}{B}{R}{R}{G}{G}", "Legendary Creature — Hydra Avatar",
                  "Protection from everything", 10, 10)
GUARDIAN = card("Test Guardian", "{3}{B}", "Creature — Spirit", "Protection from monocolored", 2, 3)
HULK = card("Test Hulk", "{4}{G}", "Creature — Beast", "Protection from snow", 5, 6)
ROCK = card("Test Rock", "{1}", "Artifact Creature — Golem", "", 1, 1)
DUO = card("Test Duo", "{U}{R}", "Creature — Human", "", 2, 2)
SNOWBEAR = card("Test Snow Bear", "{1}{G}", "Snow Creature — Bear", "", 2, 2)


class Parsing(unittest.TestCase):
    def test_keywords(self):
        for c, kw in ((LEGIONS, "snow swampwalk"), (MUSHER, "snow landwalk"), (PROGENITUS, "protection from everything"),
                      (GUARDIAN, "protection from monocolored"), (HULK, "protection from snow")):
            self.assertEqual(c.unsupported, [], c.name)
            self.assertIn(kw, c.keywords)

    def test_refusal(self):
        c = card("X", "{1}", "Creature — Bear", "Snow deserthwalk", 1, 1)
        self.assertTrue(c.unsupported)


class Engine(Base):
    def test_snow_swampwalk_needs_a_snow_swamp(self):
        """CR 702.14c: can't be blocked as long as the defending player controls a snow Swamp (a plain one isn't)."""
        legions = Permanent(LEGIONS, self.a)
        blocker = self.perm(BEAR, self.b)
        self.perm(SWAMP, self.b)
        self.assertTrue(can_block(blocker, legions))
        self.perm(SNOW_SWAMP, self.b)
        self.assertFalse(can_block(blocker, legions))

    def test_snow_landwalk_any_snow_land(self):
        musher = Permanent(MUSHER, self.a)
        blocker = self.perm(BEAR, self.b)
        self.assertTrue(can_block(blocker, musher))
        self.perm(SNOW_FOREST, self.b)
        self.assertFalse(can_block(blocker, musher))

    def test_protection_from_everything(self):
        """CR 702.16j: protection from everything, colorless sources included."""
        prog = self.perm(PROGENITUS, self.a)
        self.assertTrue(protected_from(prog, Permanent(ROCK, self.b)))
        self.assertFalse(can_block(Permanent(ROCK, self.b), prog))
        self.assertFalse(self.game.targetable(prog, self.b, SHOCK))

    def test_protection_from_monocolored(self):
        g = self.perm(GUARDIAN, self.a)
        self.assertTrue(protected_from(g, SHOCK))                       # red
        self.assertFalse(protected_from(g, DUO))                        # two colours
        self.assertFalse(protected_from(g, ROCK))                       # colourless

    def test_protection_from_snow(self):
        h = self.perm(HULK, self.a)
        self.assertTrue(protected_from(h, Permanent(SNOWBEAR, self.b)))
        self.assertFalse(protected_from(h, Permanent(BEAR, self.b)))


class HeuristicUse(Base):
    def test_ai_does_not_target_progenitus(self):
        from mtgsim.ai import _legal
        prog = self.perm(PROGENITUS, self.a)
        bear = self.perm(BEAR, self.a)
        eff = SHOCK.spell_effects[0]
        with self.game.targeting(SHOCK):
            self.assertFalse(_legal(self.game, self.b, eff, prog, SHOCK))
            self.assertTrue(_legal(self.game, self.b, eff, bear, SHOCK))
        self.assertIs(self.b.ai.choose_target(self.game, self.b, eff, SHOCK), bear)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Rime Dryad", "Legions of Lim-Dûl", "Zombie Musher", "Guardian of the Guildpact", "Hexdrinker",
                     "Progenitus", "Ronom Hulk"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()

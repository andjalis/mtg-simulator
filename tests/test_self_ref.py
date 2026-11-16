"""#795 follow-up (audit 2026-11-16, opus-cast): after an untargeted effect on ~, "it" is ~ (Grimgrin), but an explicit
"that creature" keeps the trigger's subject. #795 pointed both at ~, so Flame-Kin War Scout and Grave Peril were
sacrificed and their payoff hit the sacrificed source instead of the creature that entered (#840)."""
import unittest

from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

SCOUT = card("Test Scout", "{3}{R}", "Creature — Elemental Scout", "When another creature enters, sacrifice this "
             "creature. If you do, this creature deals 4 damage to that creature.", 2, 4)
PERIL = card("Test Peril", "{1}{B}", "Enchantment", "When a nonblack creature enters, sacrifice this enchantment. If "
             "you do, destroy that creature.")
GRIM = card("Test Grim", "{3}{U}{B}", "Creature — Zombie Warrior", "Sacrifice another creature: Untap ~ and put a "
            "+1/+1 counter on it.", 5, 5)
OGRE = card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)


class ExplicitThatCreature(Base):
    def test_parse_marks_only_the_explicit_wording(self):
        sac = next(e for e in SCOUT.triggers[0].effects if e.kind == "sacrifice_self")
        self.assertTrue(sac.data.get("keep_ctx"))
        untap = GRIM.activated[0].effects[0]
        self.assertEqual(untap.kind, "untap_self")
        self.assertFalse(untap.data.get("keep_ctx"))

    def test_scout_hits_the_creature_that_entered(self):
        scout = self.game.enter_battlefield(self.a, SCOUT)
        self.game.settle()
        ogre = self.game.enter_battlefield(self.b, OGRE)
        self.game.settle()
        self.assertNotIn(scout, self.a.battlefield)
        self.assertNotIn(ogre, self.b.battlefield)

    def test_grave_peril_destroys_the_creature_that_entered(self):
        peril = self.game.enter_battlefield(self.a, PERIL)
        self.game.settle()
        ogre = self.game.enter_battlefield(self.b, OGRE)
        self.game.settle()
        self.assertNotIn(peril, self.a.battlefield)
        self.assertNotIn(ogre, self.b.battlefield)

    def test_grimgrin_it_is_still_the_source(self):
        grim = Permanent(GRIM, self.a)
        grim.tapped = True
        self.a.battlefield = [grim, Permanent(BEAR, self.a)]
        self.assertTrue(self.game.activate_ability(self.a, grim, 0))
        self.game.settle()
        self.assertFalse(grim.tapped)
        self.assertEqual(grim.counters.get("+1/+1"), 1)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Flame-Kin War Scout", "Grave Peril"):
            effs = [e for t in db.get(name).triggers for e in t.effects if e.kind == "sacrifice_self"]
            self.assertTrue(effs and all(e.data.get("keep_ctx") for e in effs), name)
        for name in ("Grimgrin, Corpse-Born", "Axgard Braggart"):
            effs = [e for a in db.get(name).activated for e in a.effects if e.kind == "untap_self"]
            self.assertTrue(effs and not any(e.data.get("keep_ctx") for e in effs), name)


if __name__ == "__main__":
    unittest.main()

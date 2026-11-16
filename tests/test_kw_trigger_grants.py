"""#633: triggered keywords granted to groups and hosts (mtgsim.kw_trigger_grants)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.kw_trigger_grants import _keyword_triggers
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

ADRIANA = card("Test Adriana", "{3}{W}", "Legendary Creature — Human Knight",
               "Other creatures you control have melee.", 4, 4)
DAGGER = card("Test Dagger", "{2}", "Artifact — Equipment", "Equipped creature gets +2/+0 and has afflict 1.\nEquip {2}")
CAYTH = card("Test Cayth", "{2}{W}", "Creature — Human Artificer",
             "Other nontoken creatures you control have fabricate 1.", 2, 2)


class Parsing(unittest.TestCase):
    def test_lines(self):
        for c in (ADRIANA, DAGGER, CAYTH):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(DAGGER.equip_bonus, (2, 0))
        self.assertEqual([t.event for spec, ts in ADRIANA.trigger_grants for t in ts], ["attacks"])

    def test_only_purely_triggered_keywords(self):
        self.assertIsNotNone(_keyword_triggers("melee"))
        self.assertIsNotNone(_keyword_triggers("afflict 3"))
        for kw in ("riot", "myriad", "exalted", "outlast {2}", "training", "frenzy 1", "flying", "foo"):
            self.assertIsNone(_keyword_triggers(kw), kw)

    def test_refusals(self):
        for text in ("Creatures you control have outlast {2}.", "Other creatures you control have myriad.",
                     "Equipped creature has frenzy 1."):
            c = card("Test Refused", "{3}", "Artifact — Equipment", text + "\nEquip {1}")
            self.assertTrue(c.unsupported, text)


class Engine(Base):
    def test_melee_for_others(self):
        adriana = self.perm(ADRIANA, self.a)
        bear = self.perm(BEAR, self.a)
        self.game.fire(self.a, "attacks", bear)
        self.game.fire(self.a, "attacks", adriana)
        self.game.settle()
        self.assertEqual((bear.power, bear.toughness), (3, 3))
        self.assertEqual(adriana.power, 4)                          # "other"
        self.a.battlefield.remove(adriana)
        self.assertFalse([t for t in bear.triggers if t.event == "attacks"])

    def test_afflict_on_the_equipped_creature(self):
        bear = self.perm(BEAR, self.a)
        dagger = self.perm(DAGGER, self.a)
        dagger.attached_to = bear
        bear.equipment.append(dagger)
        self.assertEqual(bear.power, 4)
        blocker = self.perm(BEAR, self.b)
        life = self.b.life
        self.game.fire(self.a, "becomes_blocked", bear, context=blocker)
        self.game.settle()
        self.assertEqual(self.b.life, life - 1)

    def test_fabricate_on_entering(self):
        self.perm(CAYTH, self.a)
        before = len(self.a.battlefield)
        self.game.enter_battlefield(self.a, BEAR)
        self.game.settle()
        bear = next(x for x in self.a.battlefield if x.card.name == "Grizzly Bears")
        # fabricate 1: a +1/+1 counter or a 1/1 Servo
        self.assertTrue(bear.p1 == 1 or len(self.a.battlefield) == before + 2)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Adriana, Captain of the Guard", "Cyberman Patrol", "Dagger of the Worthy",
                     "Drogskol Reinforcements", "Glory to the Empire!", "Titania, Proud Pummeler", "Lazotep Sliver",
                     "Cayth, Famed Mechanist", "Propagator Drone"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()

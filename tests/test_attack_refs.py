"""#628: attack triggers whose body acts on "they / those creatures / each of them", the attackers that triggered it
(mtgsim.cx_attack_refs)."""
import random
import unittest
from pathlib import Path

from mtgsim.engine import Game, Player
from mtgsim.cx_attack_refs import rewrite
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Angelic Guardian", "Champions from Beyond", "Lulu, Wild Hollyphant", "Vrestin, Menoptra Leader")


class Rewrite(unittest.TestCase):
    def test_rewrites(self):
        cases = {
            "Whenever one or more creatures you control attack, they gain indestructible until end of turn.":
            "Whenever one or more creatures you control attack, each attacking creature you control gains "
            "indestructible until end of turn.",
            "Whenever you attack with one or more other creatures with flying, those creatures get +2/+2 until end "
            "of turn.":
            "Whenever you attack with one or more other creatures with flying, each other attacking creature you "
            "control with flying gets +2/+2 until end of turn.",
            "Whenever you attack with one or more Insects, put a +1/+1 counter on each of them.":
            "Whenever you attack with one or more Insects, put a +1/+1 counter on each attacking Insect you control.",
        }
        for line, want in cases.items():
            self.assertEqual(rewrite(line), want)

    def test_refusals(self):
        for line in (
            # anyone's attackers, or the ones attacking you: not your attacking creatures
            "Whenever one or more creatures attack you, those creatures get -1/-0 until end of turn.",
            "Whenever one or more creatures attack, ~ deals damage to each of those creatures equal to the number "
            "of attacking creatures.",
            # the rider still talks about them in the plural
            "Whenever you attack with one or more creatures, they gain trample until end of turn unless their "
            "controller pays {1}.",
            # not a creature type
            "Whenever you attack with one or more Blorps, put a +1/+1 counter on each of them.",
        ):
            self.assertEqual(rewrite(line), line)


class Combat(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.g.enter_battlefield(who, c)
        perm.sick = False
        self.g.settle()
        return perm

    def bear(self, who=None, text="", name="Bear", subtype="Bear"):
        return self.put(who or self.a, card(name, "{1}", f"Creature — {subtype}", text, 2, 2))

    def fight(self, attackers):
        self.a.ai.attack = attackers
        self.g.combat(self.a, self.b)
        self.g.settle()

    def test_only_the_attackers_gain_it(self):
        guardian = self.put(self.a, card("Test Guardian", "{4}", "Creature — Angel",
                                         "Whenever one or more creatures you control attack, they gain indestructible "
                                         "until end of turn.", 2, 4))
        x, home = self.bear(), self.bear()
        self.fight([x])
        self.assertTrue(x.has("indestructible"))
        self.assertFalse(home.has("indestructible") or guardian.has("indestructible"))

    def test_other_flyers_only(self):
        lulu = self.put(self.a, card("Test Lulu", "{3}", "Creature — Elephant", "Flying\nWhenever you attack with one "
                                     "or more other creatures with flying, those creatures get +2/+2 until end of "
                                     "turn.", 3, 3))
        bird, bear = self.bear(text="Flying", subtype="Bird"), self.bear()
        self.fight([lulu, bird, bear])
        self.assertEqual((bird.power, bear.power, lulu.power), (4, 2, 3))

    def test_counters_on_each_attacking_insect(self):
        self.put(self.a, card("Test Hive", "{3}", "Enchantment", "Whenever you attack with one or more Insects, put a "
                                                                 "+1/+1 counter on each of them."))
        bug, home_bug, bear = self.bear(subtype="Insect"), self.bear(subtype="Insect"), self.bear()
        self.fight([bug, bear])
        self.assertEqual((bug.p1, home_bug.p1, bear.p1), (1, 0, 0))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in FULL:
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)

    def test_champions_needs_eight_attackers(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for n, power in ((2, 2), (8, 6)):
            a, b = Player("a", [], Scripted()), Player("b", [], Scripted())
            g = Game(a, b, random.Random(0), log=True)
            g.turn, g.step = 2, "main1"
            for p in (a, b):
                p.library = [ISLAND] * 20
                p.ai.attack, p.ai.block = (), {}
            g.enter_battlefield(a, db.get("Champions from Beyond"))
            g.settle()
            bears = [g.enter_battlefield(a, card("Bear", "{1}", "Creature — Bear", "", 2, 2)) for _ in range(n)]
            for x in bears:
                x.sick = False
            a.ai.attack = bears
            g.combat(a, b)
            g.settle()
            self.assertEqual({x.power for x in bears}, {power}, n)


if __name__ == "__main__":
    unittest.main()

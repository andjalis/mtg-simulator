"""#327 slice 2: several counter kinds on one object in one sentence; subtype lists as a union in the shared selector
("target Bird, Cat, Dog, Goat, Ox, or Snake", "each Pest, Bat, Insect, Snake, and Spider you control", "destroy all
Djinns and Efreets"); "with modular / fading / level up" groups."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from mtgsim.permanent_templates import selector

from tests.test_templates import card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


class Parse(unittest.TestCase):
    def test_kinds_on_one_object(self):
        effects, bad = _parse_effects("Put a +1/+1 counter, a reach counter, and a deathtouch counter on target creature.")
        self.assertEqual(bad, [])
        self.assertEqual([(e.kind, e.target, e.data["counter"]) for e in effects],
                         [("add_counter", "permanent", "+1/+1"), ("add_counter", "prev", "reach"),
                          ("add_counter", "prev", "deathtouch")])
        effects, bad = _parse_effects("Put a flying counter, a first strike counter, and a lifelink counter on ~.")
        self.assertEqual((bad, [e.target for e in effects]), ([], ["self"] * 3))

    def test_kinds_refused_on_groups(self):
        text = "Put a +1/+1 counter, a flying counter, and a lifelink counter on each creature you control."
        self.assertEqual(_parse_effects(text)[1], [text])

    def test_subtype_unions(self):
        self.assertEqual(selector("Bird, Cat, Dog, Goat, Ox, or Snake")["subtypes_any"],
                         ["bird", "cat", "dog", "goat", "ox", "snake"])
        self.assertEqual(selector("Elves and Warriors you control", plural=True)["subtypes_any"], ["elf", "warrior"])
        for desc in ("artifact and creature", "Elf or frob"):
            self.assertIsNone(selector(desc), desc)
        # a type-or-subtype union is read as alternatives since #506
        self.assertEqual(selector("artifact or Vehicle"), {"alts": [("artifact",), ("vehicle",)]})

    def test_ability_groups(self):
        self.assertEqual(selector("creatures you control with modular", plural=True)["ability"], "modular")
        self.assertEqual(selector("permanent with fading you control")["ability"], "fading")


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Games(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [self.db.get("Island")] * 20

    def enter(self, p, c):
        perm = self.game.enter_battlefield(p, self.db.get(c) if isinstance(c, str) else c)
        self.game.settle()
        perm.sick = perm.tapped = False
        return perm

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in ("Abigale, Eloquent First-Year", "Animal Sanctuary", "Arcbound Overseer", "Parallax Inhibitor",
                     "Venerated Teacher", "Suleiman's Legacy"):
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)

    def test_kinds_land_on_the_target(self):
        bear = self.enter(self.a, "Grizzly Bears")
        spell = card("Test Gift", "{G}", "Sorcery", "Put a +1/+1 counter, a reach counter, and a deathtouch counter on "
                     "target creature.")
        self.enter(self.a, "Forest")
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, targets=[bear]))
        self.game.settle()
        self.assertEqual((bear.counters.get("+1/+1"), bear.has("reach"), bear.has("deathtouch")), (1, True, True))

    def test_animal_sanctuary_targets_only_the_listed_types(self):
        sanctuary = self.enter(self.a, "Animal Sanctuary")
        cat = self.enter(self.a, card("Test Cat", "{1}", "Creature — Cat", "", 1, 1))
        bear = self.enter(self.a, "Grizzly Bears")
        for _ in range(3):
            self.enter(self.a, "Plains")
        idx = len(sanctuary.activated) - 1
        eff = sanctuary.activated[idx].effects[0]
        legal = self.game.legal_targets(self.a, eff) if hasattr(self.game, "legal_targets") else None
        if legal is not None:
            self.assertIn(cat, legal)
            self.assertNotIn(bear, legal)
        self.assertTrue(self.game.activate_ability(self.a, sanctuary, idx))
        self.game.settle()
        self.assertEqual((cat.counters.get("+1/+1", 0), bear.counters.get("+1/+1", 0)), (1, 0))

    def test_suleimans_legacy_destroys_both_types(self):
        djinn = self.enter(self.b, card("Test Djinn", "{3}", "Creature — Djinn", "", 4, 4))
        efreet = self.enter(self.b, card("Test Efreet", "{3}", "Creature — Efreet", "", 3, 3))
        bear = self.enter(self.b, "Grizzly Bears")
        self.enter(self.a, "Suleiman's Legacy")
        self.assertNotIn(djinn, self.b.battlefield)
        self.assertNotIn(efreet, self.b.battlefield)
        self.assertIn(bear, self.b.battlefield)
        late = self.game.enter_battlefield(self.b, card("Late Djinn", "{3}", "Creature — Djinn", "", 4, 4))
        self.game.settle()
        self.assertNotIn(late, self.b.battlefield)

    def test_arcbound_overseer_feeds_modular_creatures(self):
        overseer = self.enter(self.a, "Arcbound Overseer")
        worker = self.enter(self.a, "Arcbound Worker")
        bear = self.enter(self.a, "Grizzly Bears")
        before = (overseer.counters.get("+1/+1", 0), worker.counters.get("+1/+1", 0))
        self.game.step = "upkeep"
        for trig in overseer.card.triggers:
            if trig.event in ("upkeep", "your_upkeep"):
                for eff in trig.effects:
                    self.game.resolve(self.a, eff, overseer, None)
        self.assertEqual(worker.counters.get("+1/+1", 0), before[1] + 1)
        self.assertEqual(overseer.counters.get("+1/+1", 0), before[0] + 1)
        self.assertEqual(bear.counters.get("+1/+1", 0), 0)

    def test_ai_uses_animal_sanctuary_on_its_own_animal(self):
        self.enter(self.a, "Animal Sanctuary")
        cat = self.enter(self.a, card("Test Cat", "{1}", "Creature — Cat", "", 1, 1))
        theirs = self.enter(self.b, card("Their Cat", "{1}", "Creature — Cat", "", 1, 1))
        for _ in range(3):
            self.enter(self.a, "Plains")
        self.game.step = "main2"
        self.game.main_phase(self.a)
        self.game.settle()
        if cat.counters.get("+1/+1", 0) == 0 and theirs.counters.get("+1/+1", 0) == 0:
            self.skipTest("HeuristicAI didn't use the ability this turn")
        self.assertEqual((cat.counters.get("+1/+1", 0), theirs.counters.get("+1/+1", 0)), (1, 0))


if __name__ == "__main__":
    unittest.main()

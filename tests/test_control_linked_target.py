"""Audit 2026-11-16 (opus-cast): "gain control of target ... for as long as ..." (control_linked) had no case in the
default target chooser, so a mandatory trigger fizzled with a legal target (CR 603.3d) and an optional one never
targeted (Giant's Grasp, Scroll of Isildur)."""
import unittest

from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

GRASP = card("Test Grasp", "{2}{U}{U}", "Enchantment — Aura", "Enchant Giant you control\nWhen this Aura enters, gain "
             "control of target nonland permanent for as long as this Aura remains on the battlefield.")
GIANT = card("Test Giant", "{3}{R}", "Creature — Giant", "", 4, 4)
WURM = card("Test Wurm", "{4}{G}{G}", "Creature — Wurm", "Trample", 6, 4)
ISLAND = card("Island", types="Basic Land — Island", text="({T}: Add {U}.)")


class ChooserTests(Base):
    def test_mandatory_trigger_takes_the_opponents_best(self):
        giant = self.perm(GIANT, self.a)
        wurm, bear = self.perm(WURM, self.b), self.perm(BEAR, self.b)
        self.a.battlefield += [Permanent(ISLAND, self.a) for _ in range(4)]
        self.a.hand = [GRASP]
        self.game.cast(self.a, GRASP, [giant])
        self.game.settle()
        self.assertIn(wurm, self.a.battlefield)            # the better one, not the Bear
        self.assertIn(bear, self.b.battlefield)
        self.assertNotIn("fizzles", " ".join(self.game.events[-3:]))

    def test_it_never_takes_its_own(self):
        from mtgsim.engine.policy import default_choose_target
        eff = GRASP.triggers[0].effects[0]
        self.perm(BEAR, self.a)
        self.assertIsNone(default_choose_target(self.game, self.a, eff))
        theirs = self.perm(BEAR, self.b)
        self.assertIs(default_choose_target(self.game, self.a, eff), theirs)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def test_scroll_of_isildur_chapter_one_takes_their_artifact(self):
        from mtgsim.carddb import CardDB
        scroll = CardDB(offline=True).get("Scroll of Isildur")
        rock = self.perm(card("Test Rock", "{2}", "Artifact", "{T}: Add {C}."), self.b)
        self.game.enter_battlefield(self.a, scroll)
        self.game.settle()
        self.assertIn(rock, self.a.battlefield)

    def test_dragonlord_silumgar_steals_on_entry(self):
        from mtgsim.carddb import CardDB
        wurm = self.perm(WURM, self.b)
        self.game.enter_battlefield(self.a, CardDB(offline=True).get("Dragonlord Silumgar"))
        self.game.settle()
        self.assertIn(wurm, self.a.battlefield)

    def test_ai_activates_olivia_voldaren(self):
        """HeuristicAI uses the activated steal on the opponent's Vampire."""
        from mtgsim.carddb import CardDB
        self.game.step = "main2"
        olivia = self.game.enter_battlefield(self.a, CardDB(offline=True).get("Olivia Voldaren"))
        olivia.sick = False
        vampire = self.perm(card("Test Vampire", "{1}{B}", "Creature — Vampire", "", 2, 2), self.b)
        for c in "BBBRRR":
            self.a.battlefield.append(Permanent(card({"B": "Swamp", "R": "Mountain"}[c],
                                                     types=f"Basic Land — {({'B': 'Swamp', 'R': 'Mountain'})[c]}",
                                                     text=f"({{T}}: Add {{{c}}}.)"), self.a))
        self.a.ai.use_abilities(self.game, self.a)
        self.game.settle()
        self.assertIn(vampire, self.a.battlefield)


if __name__ == "__main__":
    unittest.main()

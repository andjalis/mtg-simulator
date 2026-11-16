"""#646 slice 2: Champion (CR 702.72, mtgsim.champion)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
PACKMASTER = card("Test Packmaster", "{3}{G}", "Creature — Elf Warrior", "Champion an Elf", 5, 5)
ELF = card("Test Elf", "{G}", "Creature — Elf Druid", "", 1, 1)
SEER = card("Test Seer", "{1}{G}", "Creature — Elf Shaman", "When this creature enters, you gain 3 life.", 1, 1)
ASH = card("Test Ash", "{3}{G}", "Creature — Treefolk Warrior", "Champion a Treefolk or Warrior", 5, 5)
WARRIOR = card("Test Warrior", "{R}", "Creature — Human Warrior", "", 1, 1)


class Parsing(unittest.TestCase):
    def test_positives(self):
        for c, want in ((PACKMASTER, {"controller": "mine", "subtypes": ["elf"], "types_any": ["permanent"],
                                      "other": True}),
                        (ASH, {"controller": "mine", "any_subtypes": ["treefolk", "warrior"],
                               "types_any": ["permanent"], "other": True})):
            self.assertEqual(c.unsupported, [])
            (eff,) = [e for t in c.triggers if t.event == "etb" for e in t.effects]
            self.assertEqual(eff.kind, "champion")
            self.assertEqual(eff.data["selector"], want)
        c = card("X", "{3}", "Creature — Shapeshifter", "Champion a creature", 4, 4)
        self.assertEqual(c.unsupported, [])

    def test_refusals(self):
        for text in ("Champion a Treefolk or Forest", "Champion a Goblin or Shaman or Elf", "Champion a Blorb",
                     "Champion two Elves", "Champion an Elf you don't control"):
            c = card("X", "{3}", "Creature — Elf", text, 4, 4)
            self.assertTrue(c.unsupported, text)
            self.assertFalse([e for t in c.triggers for e in t.effects if e.kind == "champion"], text)


class Engine(Base):
    def enter(self, c, owner=None):
        owner = owner or self.a
        perm = self.game.enter_battlefield(owner, c)
        self.game.settle()
        return perm

    def test_champions_an_elf_and_returns_it_when_it_leaves(self):
        """CR 702.72a: exile another Elf you control; when the champion leaves, the card returns under its owner's
        control."""
        elf = self.perm(ELF, self.a)
        pack = self.enter(PACKMASTER)
        self.assertNotIn(elf, self.a.battlefield)
        self.assertIn(ELF, self.a.exile)
        self.assertIn(pack, self.a.battlefield)
        self.game.destroy(pack)
        self.game.settle()
        self.assertIn("Test Elf", [x.card.name for x in self.a.battlefield])
        self.assertNotIn(ELF, self.a.exile)

    def test_sacrificed_with_nothing_to_champion(self):
        """CR 702.72a: "sacrifice it unless you exile another [object] you control"; an opponent's Elf or a
        non-Elf doesn't count."""
        self.perm(ELF, self.b)
        self.perm(BEAR, self.a)
        self.enter(PACKMASTER)
        self.assertNotIn("Test Packmaster", [x.card.name for x in self.a.battlefield])
        self.assertIn("Test Packmaster", [c.name for c in self.a.graveyard])
        self.assertEqual(len(self.b.battlefield), 1)

    def test_either_subtype(self):
        """"Champion a Treefolk or Warrior": a Warrior is enough."""
        self.perm(WARRIOR, self.a)
        ash = self.enter(ASH)
        self.assertIn(ash, self.a.battlefield)
        self.assertIn(WARRIOR, self.a.exile)

    def test_prefers_a_creature_that_enters_again(self):
        self.perm(ELF, self.a)
        self.perm(SEER, self.a)
        self.enter(PACKMASTER)
        self.assertIn(SEER, self.a.exile)
        self.assertIn("Test Elf", [x.card.name for x in self.a.battlefield])


class HeuristicUse(Base):
    def setup_turn(self, *others):
        self.game.step = "main1"
        self.a.hand = [PACKMASTER]
        self.a.battlefield = [Permanent(FOREST, self.a) for _ in range(4)] + [Permanent(c, self.a) for c in others]
        for x in self.a.battlefield:
            x.sick = False
        self.a.ai.main_phase(self.game, self.a)

    def test_ai_holds_a_champion_with_nothing_to_champion(self):
        self.setup_turn(BEAR)
        self.assertEqual([c.name for c in self.a.hand], ["Test Packmaster"])

    def test_ai_casts_it_onto_an_elf(self):
        self.setup_turn(ELF)
        self.assertIn("Test Packmaster", [x.card.name for x in self.a.battlefield])
        self.assertIn(ELF, self.a.exile)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Thoughtweft Trio", "Unstoppable Ash", "Changeling Berserker", "Nova Chaser",
                     "Wanderwine Prophets", "Supreme Exemplar", "Changeling Titan", "Lightning Crafter",
                     "Wren's Run Packmaster", "Boggart Mob", "Changeling Hero"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))

    def test_mistbind_clique_stays_partial(self):
        from mtgsim.carddb import CardDB
        self.assertEqual(card_coverage(CardDB(offline=True).get("Mistbind Clique")).status, "partial")


if __name__ == "__main__":
    unittest.main()

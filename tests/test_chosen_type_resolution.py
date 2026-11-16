"""#627: a creature type chosen on resolution ("Choose a creature type. ...", "... of the creature type of your
choice ..."), stored on the stack item, and the AI's pick from public information only (mtgsim.cx_chosen_type)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cx_chosen_type import pick
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("And They Shall Know No Fear", "Witch's Vengeance", "Extinction", "Tribal Forcemage", "Defensive Maneuvers",
        "Riptide Chronologist", "Walking Desecration", "Kindred Dominance", "Kindred Judgment", "Raise the Palisade",
        "Roar of the Crowd", "Pack's Disdain", "Coordinated Barrage")
GOB = card("Goblin", "{1}", "Creature — Goblin", "", 2, 2)
ELF = card("Elf", "{1}", "Creature — Elf", "", 3, 3)
ORC = card("Orc", "{1}", "Creature — Orc", "", 2, 2)


def game():
    a, b = Player("a", [GOB] * 20, HeuristicAI()), Player("b", [ELF] * 20, HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


def cast(g, p, c, targets=None):
    effects = list(c.spell_effects)
    item = StackItem(p, effects, targets or [None] * len(effects), card=c, name=c.name)
    g.stack.append(item)
    g.resolve_top()
    g.settle()
    return item


class Parse(unittest.TestCase):
    def test_choose_then_group(self):
        c = card("Test Fear", "{1}{W}", "Instant", "Choose a creature type. Creatures you control of the chosen type "
                                                   "get +1/+0 and gain indestructible until end of turn.")
        self.assertEqual(c.unsupported, [])
        self.assertEqual(c.spell_effects[0].kind, "choose_ctype")
        self.assertFalse(c.spell_effects[0].data["hostile"])

    def test_of_your_choice_is_one_sentence(self):
        c = card("Test Extinction", "{4}{B}", "Sorcery", "Destroy all creatures of the creature type of your choice.")
        self.assertEqual(c.unsupported, [])
        self.assertEqual([e.kind for e in c.spell_effects], ["choose_ctype", "group_remove"])
        self.assertTrue(c.spell_effects[0].data["hostile"])

    def test_arent_of_the_chosen_type_names_your_own(self):
        c = card("Test Dominance", "{5}{B}{B}", "Sorcery", "Choose a creature type. Destroy all creatures that aren't "
                                                           "of the chosen type.")
        self.assertEqual(c.unsupported, [])
        self.assertFalse(c.spell_effects[0].data["hostile"])

    def test_targets_restricted_by_the_type_are_refused(self):
        c = card("Test Snare", "{X}{U}", "Sorcery", "Return X target creatures of the creature type of your choice to "
                                                    "their owner's hand.")
        self.assertTrue(c.unsupported)


class Resolve(unittest.TestCase):
    def test_count_reads_the_choice(self):
        g, a, b = game()
        for _ in range(3):
            g.enter_battlefield(a, GOB)
        roar = card("Test Roar", "{3}{R}", "Sorcery", "Choose a creature type. ~ deals damage to any target equal to "
                                                      "the number of permanents you control of the chosen type.")
        item = cast(g, a, roar, [None, b])
        self.assertEqual((item.chosen_type, b.life), ("Goblin", 17))

    def test_harmful_names_the_opponents_type(self):
        g, a, b = game()
        mine = g.enter_battlefield(a, GOB)
        elf = g.enter_battlefield(b, ELF)
        item = cast(g, a, card("Test Vengeance", "{1}{B}{B}", "Sorcery", "Creatures of the creature type of your "
                               "choice get -3/-3 until end of turn."))
        self.assertEqual(item.chosen_type, "Elf")
        self.assertNotIn(elf, b.battlefield)
        self.assertIn(mine, a.battlefield)

    def test_arent_keeps_your_type(self):
        g, a, b = game()
        mine = g.enter_battlefield(a, GOB)
        elf = g.enter_battlefield(b, ELF)
        cast(g, a, card("Test Dominance", "{5}{B}{B}", "Sorcery", "Choose a creature type. Destroy all creatures that "
                        "aren't of the chosen type."))
        self.assertIn(mine, a.battlefield)
        self.assertNotIn(elf, b.battlefield)


class HiddenInformation(unittest.TestCase):
    def test_the_opponents_hand_and_library_do_not_change_the_pick(self):
        picks = []
        for hidden in ([], [ORC] * 7):
            g, a, b = game()
            g.enter_battlefield(b, ELF)
            b.hand = list(hidden)
            b.library = list(hidden) + [ISLAND] * 10
            b.deck = list(hidden) + [ELF] * 20
            picks.append(pick(g, a, True))
        self.assertEqual(picks, ["Elf", "Elf"])

    def test_nothing_public_names_no_type(self):
        g, a, b = game()
        b.hand = [ORC] * 7                      # hidden: never read
        self.assertEqual(pick(g, a, True), "")

    def test_their_graveyard_is_public(self):
        g, a, b = game()
        b.graveyard = [ORC, ORC]
        self.assertEqual(pick(g, a, True), "Orc")

    def test_ties_are_deterministic(self):
        g, a, b = game()
        g.enter_battlefield(b, ELF)
        g.enter_battlefield(b, ORC)
        self.assertEqual(pick(g, a, True), "Elf")


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in FULL:
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)

    def test_riptide_chronologist_untaps_your_type(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        g, a, b = game()
        gobs = [g.enter_battlefield(a, GOB) for _ in range(2)]
        elves = [g.enter_battlefield(b, ELF) for _ in range(2)]
        for x in gobs + elves:
            x.tapped = True
        rc = g.enter_battlefield(a, db.get("Riptide Chronologist"))
        rc.sick = False
        g.enter_battlefield(a, db.get("Island"))
        self.assertTrue(g.activate_ability(a, rc, 0))
        g.settle()
        self.assertEqual(([x.tapped for x in gobs], [x.tapped for x in elves]), ([False, False], [True, True]))


if __name__ == "__main__":
    unittest.main()

"""#625: gated top-of-library permissions (mtgsim.cx_top): "As long as <condition>, ...", "Once each turn, ...",
mana-value and power bounds, several permissions on one card."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, FOREST, ISLAND, card

GIANT = card("Test Giant", "{3}{G}", "Creature — Giant", "", 4, 4)
AUGUR = card("Test Augur", "{1}{G}{G}", "Creature — Elf Druid",
             "You may play lands from the top of your library.\nCoven — As long as you control three or more creatures "
             "with different powers, you may cast creature spells from the top of your library.", 2, 3)
MATERIA = card("Test Materia", "{2}", "Artifact — Equipment",
               "As long as ~ is attached to a creature, you may cast creature spells from the top of your library.\n"
               "Equip {2}")
GLARB = card("Test Glarb", "{B}{G}{U}", "Creature — Frog",
             "You may play lands and cast spells with mana value 4 or greater from the top of your library.", 2, 4)
JOHANN = card("Test Johann", "{U}{R}", "Creature — Human Wizard",
              "Once each turn, you may cast an instant or sorcery spell from the top of your library.", 1, 3)
ASSEMBLE = card("Test Assemble", "{1}{W}", "Enchantment",
                "Once each turn, you may cast a creature spell with power 2 or less from the top of your library.")
RANGERS = card("Test Rangers", "{2}{R}{G}", "Creature — Elf Scout",
               "As long as an opponent controls more lands than you, you may play lands from the top of your library.",
               3, 3)
OPT = card("Test Opt", "{U}", "Instant", "Draw a card.")


class Parsing(unittest.TestCase):
    def test_lines(self):
        for c in (AUGUR, MATERIA, GLARB, JOHANN, ASSEMBLE, RANGERS):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(len(AUGUR.advanced_rules["cx_top"]), 2)
        self.assertEqual(GLARB.advanced_rules["cx_top"][0][:2], (True, ["card with mana value 4 or greater"]))
        self.assertEqual(ASSEMBLE.advanced_rules["cx_top"][0][1], ["creature card with power 2 or less"])
        self.assertTrue(JOHANN.advanced_rules["cx_top"][0][3])

    def test_refusals(self):
        for text in ("You may cast a creature spell from the top of your library.",      # an article, not once
                     "Once each turn, you may play lands from the top of your library.",   # once-each-turn lands
                     "As long as you control a foo, you may cast creature spells from the top of your library.",
                     "You may cast creature spells of the chosen type from the top of your library.",
                     "You may cast spells with flash or flying from the top of your library."):
            c = card("Test Refused", "{1}{G}", "Enchantment", text)
            self.assertTrue(c.unsupported, text)
            self.assertFalse(c.advanced_rules.get("cx_top"), text)


class Engine(Base):
    def top_options(self):
        return [o for o in self.game.spell_options(self.a) if self.game._origin(o)[1] == "cx_top"]

    def lands(self, land, n):
        for _ in range(n):
            self.perm(land, self.a)

    def test_coven_condition(self):
        self.perm(AUGUR, self.a)
        self.lands(FOREST, 4)
        self.a.library = [GIANT]
        self.assertFalse(self.top_options())                       # one power only (2)
        self.perm(BEAR, self.a)                                     # 2 again
        self.perm(card("Test One", "{G}", "Creature — Elf", "", 1, 1), self.a)
        self.perm(GIANT, self.a)                                    # powers 2, 1, 4
        self.assertEqual(len(self.top_options()), 1)

    def test_land_permission_is_separate(self):
        self.perm(AUGUR, self.a)
        self.a.library = [FOREST]
        self.game.play_land(self.a, self.a.library[-1])
        self.assertIn("Forest", [x.card.name for x in self.a.battlefield])

    def test_attached_equipment(self):
        materia = self.perm(MATERIA, self.a)
        self.lands(FOREST, 2)
        self.a.library = [BEAR]
        self.assertFalse(self.top_options())
        materia.attached_to = self.perm(BEAR, self.a)
        self.assertEqual(len(self.top_options()), 1)

    def test_mana_value_bound(self):
        self.perm(GLARB, self.a)
        self.lands(FOREST, 4)
        self.a.library = [BEAR]
        self.assertFalse(self.top_options())                        # mana value 2
        self.a.library = [GIANT]
        self.assertEqual(len(self.top_options()), 1)

    def test_once_each_turn(self):
        self.perm(JOHANN, self.a)
        self.lands(ISLAND, 2)
        self.a.library = [ISLAND] * 3 + [OPT, OPT]
        self.assertTrue(self.game.cast(self.a, self.top_options()[0]))
        self.assertIn("Test Opt", [c.name for c in self.a.graveyard])
        self.a.library = [ISLAND, OPT]
        self.assertFalse(self.top_options())                        # used this turn
        self.game.turn += 2
        self.assertEqual(len(self.top_options()), 1)

    def test_once_and_power_bound(self):
        self.perm(ASSEMBLE, self.a)
        self.lands(FOREST, 4)
        self.a.library = [GIANT]
        self.assertFalse(self.top_options())                        # power 4
        self.a.library = [BEAR, BEAR]
        self.assertTrue(self.game.cast(self.a, self.top_options()[0]))
        self.assertFalse(self.top_options())

    def test_opponent_has_more_lands(self):
        self.perm(RANGERS, self.a)
        self.a.library = [FOREST]
        from mtgsim.cx_top import land_ok
        self.assertFalse(land_ok(self.a, self.a.library[-1]))
        self.perm(FOREST, self.b)
        self.assertTrue(land_ok(self.a, self.a.library[-1]))


class HeuristicUse(Base):
    def test_ai_casts_from_the_top_under_its_condition(self):
        self.a.battlefield = [Permanent(MATERIA, self.a)] + [Permanent(FOREST, self.a) for _ in range(4)]
        host = Permanent(BEAR, self.a)
        self.a.battlefield.append(host)
        self.a.battlefield[0].attached_to = host
        for x in self.a.battlefield:
            x.sick = False
        self.a.hand = []
        self.a.library = [ISLAND] * 5 + [GIANT]
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn("Test Giant", [x.card.name for x in self.a.creatures])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Glarb, Calamity's Augur", "Augur of Autumn", "Summoning Materia", "The Reality Chip",
                     "Verge Rangers", "Johann, Apprentice Sorcerer", "Assemble the Players"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()

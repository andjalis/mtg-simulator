"""#625: alternative costs a permanent gives a group of spells (mtgsim.group_altcost)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, FOREST, ISLAND, MOUNTAIN, PLAINS, card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
FIST = card("Test Fist", "{5}", "Artifact",
            "You may pay {W}{U}{B}{R}{G} rather than pay the mana cost for spells you cast.")
STORM = card("Test Storm", "{4}{B}", "Enchantment",
             "You may pay {0} rather than pay the mana cost for Zombie creature spells you cast.")
KENTARO = card("Test Kentaro", "{1}{R}{W}", "Legendary Creature — Human Samurai",
               "You may pay {X} rather than pay the mana cost for Samurai spells you cast, where X is that spell's "
               "mana value.", 2, 3)
MONOLITH = card("Test Monolith", "{3}", "Artifact",
                "Once each turn, you may pay {0} rather than pay the mana cost for a colorless spell you cast from "
                "your hand.")
OMNI = card("Test Omniscience", "{7}{U}{U}{U}", "Enchantment",
            "You may cast spells from your hand without paying their mana costs.")
ZOMBIE = card("Test Zombie", "{3}{B}{B}", "Creature — Zombie", "", 5, 5)
SAMURAI = card("Test Samurai", "{2}{W}{W}", "Creature — Human Samurai", "", 3, 3)
GOLEM = card("Test Golem", "{4}", "Artifact Creature — Golem", "", 3, 3)
TITAN = card("Test Titan", "{8}{G}{G}", "Creature — Giant", "", 10, 10)


class Parsing(unittest.TestCase):
    def test_lines(self):
        for c in (FIST, STORM, KENTARO, MONOLITH, OMNI):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(STORM.advanced_rules["group_alt"], (({"generic": 0}, [{"sub": ["Zombie"],
                                                                                 "types": ["creature"]}], False),))
        self.assertEqual(KENTARO.advanced_rules["group_alt"][0][0], "mv")
        self.assertTrue(MONOLITH.advanced_rules["group_alt"][0][2])

    def test_hand_only_is_recorded(self):
        self.assertEqual(card_coverage(OMNI).status, "full")
        self.assertEqual(card_coverage(MONOLITH).status, "full")
        self.assertEqual(card_coverage(FIST).status, "simplified")     # also from other zones: not offered there

    def test_refusals(self):
        for text in ("You may pay {X} rather than pay the mana cost for Samurai spells you cast.",
                     "Once each turn, you may pay {0} rather than pay the mana cost for spells you cast.",
                     "You may pay {0} rather than pay the mana cost for a spell you cast.",
                     "You may cast foo spells without paying their mana costs.",
                     "You may cast spells with mana value less than or equal to the number of creatures you control "
                     "from your hand without paying their mana costs.",
                     "You may pay eight {E} rather than pay the mana cost for permanent spells you cast."):
            c = card("Test Refused", "{3}", "Artifact", text)
            self.assertTrue(c.unsupported, text)


class Engine(Base):
    def alts(self, name):
        return [c for c in self.game.spell_options(self.a) if c.name.startswith(name) and "group_alt" in c.name]

    def test_five_colors_for_anything(self):
        self.perm(FIST, self.a)
        self.a.hand = [TITAN]
        for land in (PLAINS, ISLAND, SWAMP, MOUNTAIN, FOREST):
            self.perm(land, self.a)
        option = self.alts("Test Titan")
        self.assertEqual(len(option), 1)
        self.assertTrue(self.game.cast(self.a, option[0]))
        self.assertIn("Test Titan", [x.card.name for x in self.a.creatures])

    def test_group_filter_and_zero(self):
        self.perm(STORM, self.a)
        self.a.hand = [ZOMBIE, BEAR]
        self.assertEqual([c.name for c in self.alts("Test")], ["Test Zombie (group_alt_generic0)"])
        self.assertTrue(self.game.cast(self.a, self.alts("Test Zombie")[0]))
        self.assertIn("Test Zombie", [x.card.name for x in self.a.creatures])

    def test_x_is_the_mana_value_in_any_mana(self):
        self.perm(KENTARO, self.a)
        self.a.hand = [SAMURAI]
        for _ in range(4):
            self.perm(ISLAND, self.a)                                 # no white at all
        self.assertTrue(self.game.cast(self.a, self.alts("Test Samurai")[0]))
        self.assertTrue(all(x.tapped for x in self.a.battlefield if x.card.is_land))

    def test_once_each_turn(self):
        self.perm(MONOLITH, self.a)
        self.a.hand = [GOLEM, BEAR]
        self.assertEqual(len(self.alts("Test Golem")), 1)
        self.assertFalse(self.alts("Grizzly"))                          # not colorless
        self.assertTrue(self.game.cast(self.a, self.alts("Test Golem")[0]))
        self.a.hand.append(card("Test Golem", "{4}", "Artifact Creature — Golem", "", 3, 3))
        self.assertFalse(self.alts("Test Golem"))                       # used this turn
        self.game.turn += 2
        self.assertEqual(len(self.alts("Test Golem")), 1)

    def test_not_from_other_zones(self):
        self.perm(OMNI, self.a)
        self.a.graveyard = [TITAN]
        self.assertFalse(self.alts("Test Titan"))


class HeuristicUse(Base):
    def test_ai_casts_for_free(self):
        self.a.battlefield = [Permanent(OMNI, self.a)]
        self.a.hand = [TITAN]
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn("Test Titan", [x.card.name for x in self.a.creatures])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealOmniscience(Base):
    """The real Omniscience plays right (CR 118.9): the spell costs nothing, X is 0, additional costs still apply."""
    BLAZE = card("Test Blaze", "{X}{R}", "Sorcery", "~ deals X damage to any target.")
    FEAST = card("Test Feast", "{4}{B}", "Sorcery",
                 "As an additional cost to cast this spell, sacrifice a creature.\nDraw two cards.")

    def setUp(self):
        super().setUp()
        from mtgsim.carddb import CardDB
        self.a.battlefield = [Permanent(CardDB(offline=True).get("Omniscience"), self.a)]

    def free(self, c):
        self.a.hand = [c]
        options = [v for v in self.game.spell_options(self.a) if "group_alt" in v.name]
        self.assertEqual(len(options), 1, c.name)
        return options[0]

    def test_ai_casts_a_big_spell_for_nothing(self):
        lands = [self.perm(ISLAND, self.a) for _ in range(3)]
        self.a.hand = [TITAN]
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn("Test Titan", [x.card.name for x in self.a.creatures])
        self.assertFalse(any(x.tapped for x in lands))          # no mana paid

    def test_x_is_zero(self):
        lands = [self.perm(MOUNTAIN, self.a) for _ in range(3)]
        self.assertTrue(self.game.cast(self.a, self.free(self.BLAZE), [self.b]))
        self.game.settle()
        self.assertEqual(self.b.life, 20)                       # X = 0 under an alternative cost
        self.assertFalse(any(x.tapped for x in lands))

    def test_additional_cost_still_paid(self):
        self.assertFalse(self.game.cast(self.a, self.free(self.FEAST), []))     # no creature to sacrifice
        bear = self.perm(BEAR, self.a)
        self.a.library = [ISLAND] * 5
        self.assertTrue(self.game.cast(self.a, self.free(self.FEAST), []))
        self.game.settle()
        self.assertNotIn(bear, self.a.battlefield)
        self.assertEqual(len(self.a.hand), 2)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_statuses(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Omniscience", "Darksteel Monolith"):
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)
        for name in ("Fist of Suns", "Jodah, Archmage Eternal", "Leyline of Mutation", "Runeforge Champion",
                     "Rooftop Storm", "Kentaro, the Smiling Cat", "Dracogenesis"):
            self.assertEqual(card_coverage(db.get(name)).status, "simplified", name)


if __name__ == "__main__":
    unittest.main()

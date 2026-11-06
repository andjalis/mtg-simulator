"""The animation verb family (mtgsim.cx_grammar_animate): type changes and becoming a creature."""
import unittest

from mtgsim.cx_grammar import parse_sentence

from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import card

RELIC = card("Test Relic", "{2}", "Artifact", "")
CART = card("Test Cart", "{2}", "Artifact — Vehicle", "", 3, 3)
GROVE = card("Test Grove", "", "Land — Forest", "{T}: Add {G}.")
ALTAR = card("Test Altar", "{2}", "Enchantment", "")


class Parsing(unittest.TestCase):
    def test_rejects(self):
        for s in ("~ becomes a 3/3 creature with banding until end of turn.",       # unknown keyword
                  "~ becomes an artifact creature this turn.",                       # not a duration it takes
                  "~ becomes a copy of target creature.",
                  "~ becomes a 2/2 Foo creature until end of turn.",                 # not a creature type
                  "~ becomes an artifact creature with flying until end of turn."):  # keywords without a P/T
            self.assertIsNone(parse_sentence(s), s)


class Resolving(Base):
    def test_artifact_becomes_a_creature_until_end_of_turn(self):
        relic = self.perm(RELIC, self.a)
        spell = self.spell("Until end of turn, target noncreature artifact you control becomes a 4/4 Golem artifact "
                           "creature with trample.")
        self.cast(spell, [relic])
        self.assertTrue(relic.is_creature)
        self.assertEqual((relic.power, relic.toughness), (4, 4))
        self.assertTrue(relic.has("trample"))
        self.assertIn("Golem", relic.card.subtypes)
        self.end_turn()
        self.game.cleanup(self.a) if hasattr(self.game, "cleanup") else None
        relic.animated = None
        self.assertFalse(relic.is_creature)

    def test_vehicle_keeps_its_printed_size_and_subtype(self):
        cart = self.perm(CART, self.a)
        self.cast(self.spell("Vehicles you control become artifact creatures until end of turn."))
        self.assertTrue(cart.is_creature)
        self.assertEqual((cart.power, cart.toughness), (3, 3))
        self.assertIn("Vehicle", cart.card.subtypes)
        self.end_turn()
        self.assertFalse(cart.is_creature)

    def test_still_a_land(self):
        grove = self.perm(GROVE, self.a)
        from mtgsim.cards import parse as P
        effects, bad = P._parse_effects("~ becomes a 3/3 Elemental artifact creature that's still a land.")
        self.assertEqual(bad, [])
        eff = effects[0]
        self.game.resolve(self.a, eff, grove)
        self.assertTrue(grove.is_creature)
        self.assertEqual({"Land", "Artifact", "Creature"}, set(grove.card.types))
        self.end_turn()
        self.assertTrue(grove.is_creature)          # no duration: for good
        self.assertTrue({"Forest", "Elemental"} <= set(grove.card.subtypes))

    def test_without_still_a_land_it_stops_being_a_land(self):
        grove = self.perm(GROVE, self.a)
        eff = parse_sentence("Target land becomes a 2/2 Spirit creature until end of turn.")[0]
        self.game.resolve(self.a, eff, grove)
        self.assertEqual(set(grove.card.types), {"Creature"})

    def test_in_addition(self):
        altar = self.perm(ALTAR, self.a)
        eff = parse_sentence("Target enchantment becomes a 4/4 Wall creature with defender in addition to its other "
                             "types until end of turn.")[0]
        self.game.resolve(self.a, eff, altar)
        self.assertEqual(set(altar.card.types), {"Enchantment", "Creature"})
        self.assertTrue(altar.has("defender"))
        self.assertEqual(altar.toughness, 4)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Chimeric Idol", "Alloy Animist", "Izzet Keyrune", "Stalking Stones"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()

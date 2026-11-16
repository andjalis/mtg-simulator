"""#646 slice 6: Evoke with a non-mana cost (CR 702.74, mtgsim.evoke_costs)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, ISLAND, card

SOLITUDE = card("Test Solitude", "{3}{W}{W}", "Creature — Elemental Incarnation",
                "Flash\nLifelink\nWhen this creature enters, exile up to one other target creature. That creature's "
                "controller gains life equal to its power.\nEvoke—Exile a white card from your hand.", 3, 2)
PRIEST = card("Test Priest", "{1}{W}", "Creature — Human Cleric", "", 2, 2)
GIANT = card("Test Giant", "{4}{R}", "Creature — Giant", "", 5, 5)


def evoke_variant(game, p):
    return [o for o in game.spell_options(p) if game._origin(o)[0].name == SOLITUDE.name and game._origin(o)[1]]


class Parsing(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(SOLITUDE.unsupported, [])
        (alt,) = [a for a in SOLITUDE.alt_costs if a.kind.startswith("cond_alt_")]
        self.assertEqual(SOLITUDE.advanced_rules["evoke_alts"], (alt.kind,))
        code, parts = SOLITUDE.advanced_rules["alt_if"][int(alt.kind[9:])]
        self.assertEqual([p[0] for p in parts], ["pitch"])

    def test_refusals(self):
        for text in ("Evoke—Exile a colorless card from your hand.", "Evoke—Exile two white cards from your hand.",
                     "Evoke—Celebrate an opponent.", "Evoke—Discard a card."):
            c = card("X", "{3}{W}", "Creature — Elemental", text, 2, 2)
            self.assertTrue(c.unsupported, text)
            self.assertNotIn("evoke_alts", c.advanced_rules, text)


class Engine(Base):
    def test_evoked_by_pitching_a_white_card(self):
        """CR 702.74a: cast it by exiling a white card instead of paying its mana cost; when it enters it is
        sacrificed, and its own enters trigger still resolves."""
        giant = self.perm(GIANT, self.b)
        self.a.hand = [SOLITUDE, PRIEST]
        (variant,) = evoke_variant(self.game, self.a)
        self.assertTrue(self.game.cast(self.a, variant, None))
        self.game.settle()
        self.assertIn(PRIEST, self.a.exile)                    # the pitched card
        self.assertIn(SOLITUDE, self.a.graveyard)              # sacrificed
        self.assertNotIn(giant, self.b.battlefield)            # exiled by the enters trigger
        self.assertEqual(self.b.life, 25)

    def test_not_offered_without_a_white_card_or_when_it_can_be_hard_cast(self):
        self.a.hand = [SOLITUDE, BEAR]
        self.assertEqual(evoke_variant(self.game, self.a), [])
        self.a.hand = [SOLITUDE, PRIEST]
        self.a.battlefield = [Permanent(card("Plains", types="Basic Land — Plains", text="({T}: Add {W}.)"),
                                        self.a) for _ in range(5)]
        self.assertEqual(evoke_variant(self.game, self.a), [])     # the mana cost can be paid: cast it normally


class HeuristicUse(Base):
    def test_ai_evokes_only_with_something_to_exile(self):
        self.game.step = "main1"
        self.a.hand = [SOLITUDE, PRIEST]
        self.a.battlefield = [Permanent(ISLAND, self.a)]
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn(SOLITUDE, self.a.hand)                   # nothing to exile: keep both cards
        giant = self.perm(GIANT, self.b)
        self.a.ai.main_phase(self.game, self.a)
        self.game.settle()
        self.assertNotIn(giant, self.b.battlefield)            # aimed at the opponent's creature
        self.assertIn(SOLITUDE, self.a.graveyard)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Solitude", "Fury", "Grief"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()

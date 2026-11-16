"""#625: "Exile cards from the top of your library until you exile a nonland card. You may cast that card ..."
(mtgsim.until_nonland)."""
import unittest

from mtgsim.cards.parse import _parse_effects
from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent, StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, FOREST, ISLAND, card

HEAD = "Exile cards from the top of your library until you exile a nonland card. "
SHOCK = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to any target.")
GIANT = card("Test Giant", "{3}{G}", "Creature — Giant", "", 4, 4)


class Parsing(unittest.TestCase):
    def test_wordings(self):
        for rider, then in (("You may cast that card without paying its mana cost.", "free"),
                            ("You may cast that card this turn.", "turn"),
                            ("You may play that card this turn.", "turn")):
            effects, bad = _parse_effects(HEAD + rider)
            self.assertEqual(bad, [], rider)
            self.assertEqual([(e.kind, e.data) for e in effects], [("until_nonland", {"then": then})])

    def test_refusals(self):
        for rider in ("You may cast that card without paying its mana cost if the spell's mana value is 8 or less.",
                      "You may cast that card by discarding a card rather than paying its mana cost.",
                      "You may cast that card until the end of your next turn.",
                      "Put that card into your hand."):
            effects, bad = _parse_effects(HEAD + rider)
            self.assertTrue(bad, rider)
            self.assertNotIn("until_nonland", [e.kind for e in effects], rider)


class Engine(Base):
    def resolve(self, rider):
        effects, _ = _parse_effects(HEAD + rider)
        self.game.stack.append(StackItem(self.a, effects, [None] * len(effects), name="test", kind="trigger"))
        self.game.resolve_top()

    def test_free_cast_of_the_found_card(self):
        self.a.library = [ISLAND, GIANT, FOREST, FOREST]          # top is the end of the list
        self.resolve("You may cast that card without paying its mana cost.")
        self.assertEqual([x.card.name for x in self.a.creatures], ["Test Giant"])
        self.assertEqual(sorted(c.name for c in self.a.exile), ["Forest", "Forest"])   # the lands stay exiled
        self.assertEqual([c.name for c in self.a.library], ["Island"])

    def test_targets_the_opponent(self):
        self.a.library = [SHOCK]
        life = self.b.life
        self.resolve("You may cast that card without paying its mana cost.")
        self.assertEqual(self.b.life, life - 2)

    def test_this_turn_permission_paid(self):
        self.a.library = [GIANT, FOREST]
        self.resolve("You may cast that card this turn.")
        options = [c for c in self.game.spell_options(self.a) if c.name.startswith("Test Giant")]
        self.assertEqual(len(options), 1)
        self.assertFalse(self.game.cast(self.a, options[0]))            # no mana: not free
        for _ in range(4):
            self.perm(FOREST, self.a)
        self.assertTrue(self.game.cast(self.a, options[0]))
        self.game.turn += 1
        self.a.library = [BEAR]
        self.resolve("You may cast that card this turn.")
        self.game.turn += 1
        self.assertFalse([c for c in self.game.spell_options(self.a) if c.name.startswith("Grizzly")])

    def test_only_lands(self):
        self.a.library = [FOREST, FOREST]
        self.resolve("You may cast that card without paying its mana cost.")
        self.assertEqual(self.a.library, [])
        self.assertEqual(len(self.a.exile), 2)


class HeuristicUse(Base):
    def test_ai_activates_and_casts_for_free(self):
        nico = card("Test Nico", "{2}{R}", "Legendary Creature — Human Warlock",
                    "{1}, {T}: Exile cards from the top of your library until you exile a nonland card. You may cast "
                    "that card without paying its mana cost.", 2, 2)
        self.assertEqual(nico.unsupported, [])
        self.game.step = "main2"
        self.a.battlefield = [Permanent(nico, self.a), Permanent(ISLAND, self.a)]
        for x in self.a.battlefield:
            x.sick = False
        self.a.library = [ISLAND] * 3 + [GIANT]
        self.a.ai.use_abilities(self.game, self.a)
        self.assertIn("Test Giant", [x.card.name for x in self.a.creatures])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Q, Your Illustrious Host", "Nico Minoru, Runaway", "Wanda's Vision", "Territorial Bruntar",
                     "Exploratory Mission", "Sarevok's Tome"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()

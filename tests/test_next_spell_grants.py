"""#633: "The first <kind> spell you cast each turn has X" and "the next <kind> spell you cast this turn has X"
(mtgsim.spell_grants)."""
import unittest

from mtgsim.cards.parse import _parse_effects
from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent, StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

NEXUS = card("Test Nexus", "{3}", "Enchantment", "The first spell you cast each turn has cascade.")
CURRICULUM = card("Test Curriculum", "{1}{U}", "Enchantment", "The first Merfolk spell you cast each turn has convoke.")
SHOCK = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to any target.")
DRAW = card("Test Draw", "{3}", "Sorcery", "Draw a card.")
GOLEM = card("Test Golem", "{4}", "Artifact Creature — Golem", "", 3, 3)
MERFOLK = card("Test Merfolk", "{3}", "Creature — Merfolk", "", 2, 2)


class Parsing(unittest.TestCase):
    def test_lines(self):
        for c in (NEXUS, CURRICULUM):
            self.assertEqual(c.unsupported, [], c.name)
        effects, bad = _parse_effects("The next noncreature spell you cast this turn has cascade.")
        self.assertEqual((bad, [e.kind for e in effects]), ([], ["next_spell_grant"]))
        effects, bad = _parse_effects("The next instant spell and the next sorcery spell you cast this turn each "
                                      "have cascade.")
        self.assertEqual((bad, len(effects[0].data["groups"])), ([], 2))

    def test_refusals(self):
        for text in ("The next spell you cast has convoke.",                         # no "this turn"
                     "The next noncreature spell you cast this turn has affinity for artifacts.",
                     "The next spell you cast this turn has demonstrate."):
            effects, bad = _parse_effects(text)
            self.assertTrue(bad, text)
        c = card("Test Refused", "{3}", "Enchantment", "The first spell you cast from exile each turn has cascade.")
        self.assertTrue(c.unsupported)


class Engine(Base):
    def lands(self, land, n):
        for _ in range(n):
            self.perm(land, self.a)

    def grant(self, text):
        effects, _ = _parse_effects(text)
        self.game.stack.append(StackItem(self.a, effects, [None] * len(effects), name="grant", kind="ability"))
        self.game.resolve_top()

    def test_first_spell_each_turn_cascades(self):
        self.perm(NEXUS, self.a)
        self.lands(MOUNTAIN, 6)
        self.a.library = [ISLAND] * 6 + [SHOCK, ISLAND, SHOCK]
        self.a.hand = [DRAW, DRAW]
        life = self.b.life
        self.game.cast(self.a, self.a.hand[0])
        self.game.settle()
        self.assertEqual(self.b.life, life - 2)                         # the first spell cascaded into a Shock
        self.game.cast(self.a, next(c for c in self.a.hand if c.name == "Test Draw"))
        self.game.settle()
        self.assertEqual(self.b.life, life - 2)                         # the second one didn't

    def test_first_of_a_kind(self):
        self.game.step = "main2"
        self.perm(CURRICULUM, self.a)
        for _ in range(2):
            self.perm(BEAR, self.a)
        self.lands(ISLAND, 1)
        self.assertTrue(self.game.spell_payable(self.a, MERFOLK))       # convoke: 1 land + 2 creatures
        self.assertFalse(self.game.spell_payable(self.a, GOLEM))

    def test_next_spell_once(self):
        self.game.step = "main2"
        for _ in range(4):
            self.perm(BEAR, self.a)
        self.assertFalse(self.game.spell_payable(self.a, GOLEM))
        self.grant("The next spell you cast this turn has convoke.")
        self.assertTrue(self.game.spell_payable(self.a, GOLEM))
        self.a.hand = [GOLEM]
        self.assertTrue(self.game.cast(self.a, GOLEM))
        for x in self.a.creatures:
            x.tapped = False
        self.assertFalse(self.game.spell_payable(self.a, card("Test Golem 2", "{4}", "Artifact", "")))   # used up

    def test_next_spell_kind_and_turn(self):
        self.game.step = "main2"
        for _ in range(4):
            self.perm(BEAR, self.a)
        self.grant("The next noncreature spell you cast this turn has convoke.")
        self.assertFalse(self.game.spell_payable(self.a, GOLEM))         # a creature spell: not this grant
        relic = card("Test Relic", "{4}", "Artifact", "")
        self.assertTrue(self.game.spell_payable(self.a, relic))
        self.game.turn += 1
        self.assertFalse(self.game.spell_payable(self.a, relic))         # this turn only

    def test_instant_and_sorcery_each(self):
        self.lands(MOUNTAIN, 4)
        self.grant("The next instant spell and the next sorcery spell you cast this turn each have cascade.")
        self.a.library = [ISLAND] * 4 + [SHOCK, ISLAND, SHOCK]
        life = self.b.life
        self.a.hand = [DRAW, SHOCK]
        self.game.cast(self.a, DRAW)
        self.game.settle()
        self.assertEqual(self.b.life, life - 2)                           # sorcery cascaded
        self.game.cast(self.a, SHOCK, [self.b])
        self.game.settle()
        self.assertLessEqual(self.b.life, life - 4)                       # the instant too (cascade misses at 1)


class HeuristicUse(Base):
    def test_ai_uses_a_next_spell_convoke(self):
        self.game.step = "main2"
        self.a.battlefield = [Permanent(BEAR, self.a) for _ in range(4)]
        effects, _ = _parse_effects("The next spell you cast this turn has convoke.")
        self.game.stack.append(StackItem(self.a, effects, [None] * len(effects), name="grant", kind="ability"))
        self.game.resolve_top()
        self.a.hand = [GOLEM]
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn("Test Golem", [x.card.name for x in self.a.creatures])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Archway of Innovation", "Crackling Spellslinger", "Dark Apostle", "Sloppity Bilepiper",
                     "Storm, Force of Nature", "Flockchaser Phantom", "Wand of the Worldsoul", "Smoldering Stagecoach",
                     "Maelstrom Nexus", "Current Curriculum", "Peri Brown"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()

"""#633 SPELL-KW-GRANT: "<kind> spells you cast have convoke / cascade / storm / ..." (mtgsim.spell_grants)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

ENGINEER = card("Test Engineer", "{1}{U}", "Creature — Human Artificer", "Artifact spells you cast have convoke.", 1, 3)
IMOTI = card("Test Imoti", "{3}{G}{U}", "Legendary Creature — Naga Druid",
             "Spells you cast with mana value 6 or greater have cascade.", 6, 4)
QUANDRIX = card("Test Quandrix", "{4}", "Artifact", "Instant and sorcery spells you cast from your hand have cascade.")
PRISMARI = card("Test Prismari", "{4}", "Artifact", "Instant and sorcery spells you cast have storm.")
SAMUT = card("Test Samut", "{4}", "Artifact", "Instant and sorcery spells you control have split second.")
GOLEM = card("Test Golem", "{4}", "Artifact Creature — Golem", "", 3, 3)
BIG = card("Test Big", "{6}", "Creature — Giant", "", 6, 6)
SHOCK = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to any target.")
DRAW = card("Test Draw", "{1}", "Sorcery", "Draw a card.")


class Parsing(unittest.TestCase):
    def test_lines(self):
        for c in (ENGINEER, IMOTI, QUANDRIX, PRISMARI, SAMUT):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(IMOTI.advanced_rules["spell_grants"][0][2:], ((6, "greater"), ("cascade",)))
        self.assertTrue(QUANDRIX.advanced_rules["spell_grants"][0][1])

    def test_refusals(self):
        for text in ("The first spell you cast from exile each turn has cascade.",
                     "Creature spells you cast have demonstrate.",                   # not read from the spell
                     "Artifact spells you control have convoke.",
                     "Spells you cast that share a color have convoke.",
                     "Commander spells you cast have cascade.",
                     "Noncreature spells you cast from exile have convoke."):
            c = card("Test Refused", "{3}", "Artifact", text)
            self.assertTrue(c.unsupported, text)


class Engine(Base):
    def lands(self, land, n):
        for _ in range(n):
            self.perm(land, self.a)

    def test_convoke_pays_with_creatures(self):
        self.game.step = "main2"                                       # the engine convokes after combat
        self.perm(ENGINEER, self.a)
        for _ in range(2):
            self.perm(BEAR, self.a).sick = False
        self.lands(ISLAND, 1)
        self.a.hand = [GOLEM]
        self.assertTrue(self.game.spell_payable(self.a, GOLEM))       # 1 land + 3 creatures for {4}
        self.assertTrue(self.game.cast(self.a, GOLEM))
        self.assertIn("Test Golem", [x.card.name for x in self.a.creatures])
        self.assertTrue(all(x.tapped for x in self.a.creatures if x.card.name != "Test Golem"))

    def test_no_convoke_for_other_spells(self):
        self.game.step = "main2"
        self.perm(ENGINEER, self.a)
        for _ in range(4):
            self.perm(BEAR, self.a).sick = False
        self.assertFalse(self.game.spell_payable(self.a, BIG))

    def test_cascade_by_mana_value(self):
        self.perm(IMOTI, self.a)
        self.lands(MOUNTAIN, 6)
        self.a.library = [ISLAND] * 3 + [SHOCK, ISLAND]
        self.a.hand = [BIG]
        life = self.b.life
        self.assertTrue(self.game.cast(self.a, BIG))
        self.game.settle()
        self.assertEqual(self.b.life, life - 2)                         # cascaded into Shock
        self.assertIn("Test Big", [x.card.name for x in self.a.creatures])

    def test_cascade_only_from_hand(self):
        self.perm(QUANDRIX, self.a)
        self.lands(MOUNTAIN, 2)
        self.a.library = [SHOCK]
        flash = card("Test Flash", "{1}", "Sorcery", "Draw a card.\nFlashback {1}")
        self.a.graveyard = [flash]
        option = [c for c in self.game.spell_options(self.a) if c.name.startswith("Test Flash")][0]
        life = self.b.life
        self.assertTrue(self.game.cast(self.a, option))
        self.game.settle()
        self.assertEqual(self.b.life, life)                             # from the graveyard: no cascade

    def test_storm_counts_earlier_spells(self):
        self.perm(PRISMARI, self.a)
        self.lands(ISLAND, 3)
        self.a.library = [ISLAND] * 10
        self.a.hand = [DRAW, DRAW, DRAW]
        hand = len(self.a.hand)
        for c in list(self.a.hand):
            if c in self.a.hand:
                self.game.cast(self.a, c)
                self.game.settle()
        # Three Draws, the 2nd with 1 storm copy and the 3rd with 2: six cards drawn
        self.assertEqual(len(self.a.hand), hand - 3 + 6)

    def test_delve_exiles_graveyard_cards(self):
        teval = card("Test Teval", "{2}{B}", "Creature — Dragon", "Spells you cast have delve.", 2, 2)
        self.perm(teval, self.a)
        big_draw = card("Test Big Draw", "{4}", "Sorcery", "Draw a card.")
        self.a.hand = [big_draw]
        self.a.graveyard = [ISLAND] * 4
        self.assertTrue(self.game.spell_payable(self.a, big_draw))
        self.assertTrue(self.game.cast(self.a, big_draw))
        self.game.settle()
        self.assertEqual(len(self.a.exile), 4)

    def test_split_second_keyword(self):
        from mtgsim.spell_grants import apply
        self.perm(SAMUT, self.a)
        self.a.hand = [SHOCK]
        cast = apply(self.game, self.a, SHOCK, SHOCK, "")
        self.assertIn("split second", cast.keywords)
        self.assertNotIn("split second", SHOCK.keywords)                # the card itself is unchanged


class HeuristicUse(Base):
    def test_ai_convokes(self):
        self.a.battlefield = [Permanent(ENGINEER, self.a)] + [Permanent(BEAR, self.a) for _ in range(3)]
        for x in self.a.battlefield:
            x.sick = False
        self.a.hand = [GOLEM]
        self.game.step = "main2"
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn("Test Golem", [x.card.name for x in self.a.creatures])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Chief Engineer", "Imoti, Celebrant of Bounty", "Quandrix, the Proof", "Wildsear, Scouring Maw",
                     "The First Sliver", "Inspiring Statuary", "Ironheart, Clever Champion", "Teval, Arbiter of Virtue",
                     "Prismari, the Inspiration", "Samut, Tyrant of Naktamun", "Cast Through Time"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()

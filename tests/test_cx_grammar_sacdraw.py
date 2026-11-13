"""#337: "Sacrifice any number of <types>, then draw that many cards" with a conservative AI choice."""
import unittest

from mtgsim.cards import make_token
from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import StackItem

from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import BEAR, ISLAND, card

WITCHKITE = "Sacrifice any number of artifacts, enchantments, and/or tokens, then draw that many cards."
CARNAGE = "Sacrifice any number of permanents you control, then draw that many cards."
RELIC = card("Test Relic", "{1}", "Artifact", "")
AURA = card("Test Charm", "{1}", "Enchantment", "")


class Parsing(unittest.TestCase):
    def test_shapes(self):
        e = parse_sentence(WITCHKITE)[0]
        self.assertEqual([(x.kind, x.data["sac"]) for x in e.data["effects"]],
                         [("cx_away", {"types": ["artifact", "enchantment", "token"], "other": False})] * 1 +
                         [("cx_draw_that_many", {"types": ["artifact", "enchantment", "token"], "other": False})])
        e = parse_sentence("Sacrifice any number of other permanents, then draw that many cards.")[0]
        self.assertEqual(e.data["effects"][0].data["sac"], {"types": ["permanent"], "other": True})

    def test_refusals(self):
        for s in ("Sacrifice any number of creatures with power 2 or less, then draw that many cards.",
                  "Each player sacrifices any number of permanents, then draws that many cards.",
                  "Target player sacrifices any number of permanents, then draws that many cards.",
                  "Sacrifice any number of Goblins, then draw that many cards.",
                  "Sacrifice any number of permanents, then draws that many cards."):
            self.assertIsNone(parse_sentence(s), s)


class Behaviour(Base):
    def token(self, kind, owner):
        return self.perm(make_token("", 0, 0, kind=kind), owner)

    def resolve(self, text, source=None):
        c = self.spell(text, "Sorcery")
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [None] * len(c.spell_effects), card=c,
                                         name=c.name, source=source))
        self.game.resolve_top()

    def lands(self, n):
        for _ in range(n):
            self.perm(ISLAND, self.a)

    def test_only_clues_with_few_lands(self):
        self.lands(4)
        clues = [self.token("clue", self.a) for _ in range(2)]
        treasure = self.token("treasure", self.a)
        relic, charm = self.perm(RELIC, self.a), self.perm(AURA, self.a)
        self.resolve(WITCHKITE)
        on = self.a.battlefield
        self.assertTrue(all(c not in on for c in clues))
        self.assertTrue(all(x in on for x in (treasure, relic, charm)))
        self.assertEqual(len(self.a.hand), 2)

    def test_other_tokens_once_five_lands_are_out(self):
        self.lands(5)
        self.token("treasure", self.a)
        self.token("food", self.a)
        self.resolve(WITCHKITE)
        self.assertEqual((len(self.a.hand), sum(x.card.is_token for x in self.a.battlefield)), (2, 0))

    def test_never_creatures_and_only_lands_beyond_seven(self):
        self.lands(9)
        bear = self.perm(BEAR, self.a)
        self.resolve(CARNAGE)
        self.assertIn(bear, self.a.battlefield)
        self.assertEqual((sum(x.card.is_land for x in self.a.battlefield), len(self.a.hand)), (7, 2))

    def test_nothing_worth_giving_up_draws_nothing(self):
        self.lands(3)
        self.perm(BEAR, self.a)
        self.perm(RELIC, self.a)
        self.resolve(CARNAGE)
        self.assertEqual((len(self.a.battlefield), len(self.a.hand)), (5, 0))

    def test_types_and_other_limit_the_candidates(self):
        source = self.token("clue", self.a)
        mine = self.token("clue", self.a)
        bear = self.perm(BEAR, self.a)
        self.a.ai.choose_sac_any = lambda game, me, cands: list(cands)     # an AI that gives up everything it may
        self.resolve("Sacrifice any number of other permanents, then draw that many cards.", source=source)
        self.assertIn(source, self.a.battlefield)
        self.assertNotIn(mine, self.a.battlefield)
        self.assertNotIn(bear, self.a.battlefield)
        self.assertEqual(len(self.a.hand), 2)
        relic = self.perm(RELIC, self.a)
        land = self.perm(ISLAND, self.a)
        self.resolve(WITCHKITE)             # artifacts, enchantments and tokens only: the land stays
        self.assertNotIn(relic, self.a.battlefield)
        self.assertIn(land, self.a.battlefield)

    def test_opponents_permanents_are_never_sacrificed(self):
        theirs = self.token("clue", self.b)
        self.token("clue", self.a)
        self.resolve(WITCHKITE)
        self.assertIn(theirs, self.b.battlefield)
        self.assertEqual(len(self.a.hand), 1)


class DefaultAI(Base):
    def setUp(self):
        super().setUp()
        self.spell_card = card("Test Spell", "{B}", "Sorcery", CARNAGE)
        self.assertEqual(self.spell_card.unsupported, [])
        self.perm(card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)"), self.a)
        self.a.hand = [self.spell_card]
        self.game.step = "main2"

    def test_casts_with_clues_to_cash_in(self):
        for _ in range(3):
            self.perm(make_token("", 0, 0, kind="clue"), self.a)
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(self.spell_card, self.a.hand)
        self.assertEqual((len(self.a.hand), sum(x.card.is_token for x in self.a.battlefield)), (3, 0))

    def test_holds_it_with_nothing_to_give_up(self):
        self.perm(BEAR, self.a)
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn(self.spell_card, self.a.hand)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Malevolent Witchkite", "Pitiless Carnage"):
            self.assertEqual(card_coverage(db.get(name)).ignored, [], name)


if __name__ == "__main__":
    unittest.main()

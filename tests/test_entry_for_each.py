"""#630 ENTERS-WITH: "~ enters with a <kind> counter on it for each <thing>" (mtgsim.cx_counters.entry_for_each)."""
import unittest

from mtgsim.cards.clauses import _xq
from mtgsim.coverage import card_coverage
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

CAPTAIN = card("Test Captain", "{4}{W}", "Creature — Human Soldier",
               "~ enters with a +1/+1 counter on it for each other creature you control.", 2, 2)
TROLL = card("Test Troll", "{4}{G}", "Creature — Troll Skeleton",
             "~ enters with a +1/+1 counter on it for each creature card in your graveyard.", 0, 0)
VANGUARD = card("Test Vanguard", "{4}{W}", "Creature — Human Soldier",
                "~ enters with two +1/+1 counters on it for each other nontoken Human you control.", 0, 0)
AVATAR = card("Test Avatar", "{G}{G}", "Creature — Avatar",
              "~ enters with a +1/+1 counter on it for each other creature you control with a +1/+1 counter on it.",
              3, 2)
GATE = card("Test Gate", "", "Land — Gate", "")
GARGOYLE = card("Test Gargoyle", "{6}", "Artifact Creature — Gargoyle",
                "~ enters with a +1/+1 counter on it for each Gate you control.", 3, 3)
HUMAN = card("Test Human", "{W}", "Creature — Human", "", 1, 1)


class Parsing(unittest.TestCase):
    def test_lines(self):
        for c in (CAPTAIN, TROLL, VANGUARD, AVATAR, GARGOYLE):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(VANGUARD.entry_counter_quantity[2], 2)

    def test_refusals(self):
        for text in ("~ enters with a +1/+1 counter on it for each foo you bar.",
                     "~ enters with a +1/+1 counter on it for each different mana cost among nonland cards in your "
                     "graveyard.",
                     "~ enters with a +1/+1 counter on it for each other spell cast this turn and a card."):
            c = card("Test Refused", "{3}", "Creature — Beast", text, 1, 1)
            self.assertTrue(c.unsupported, text)

    def test_counter_kind_is_one_word(self):
        self.assertEqual(_xq("the number of charge counters on ~"), ("counters", "charge"))
        self.assertEqual(_xq("the number of acquired taste counters on ~"), ("counters", "acquired taste"))
        self.assertIsNone(_xq("the number of card they own in exile with a hit counter on it"))
        self.assertIsNone(_xq("the number of other creature you control with a +1/+1 counter on it"))


class Engine(Base):
    def enter(self, c):
        self.game.enter_battlefield(self.a, c)
        return next(x for x in self.a.battlefield if x.card.name == c.name)

    def test_other_creatures_not_itself_nor_theirs(self):
        self.perm(BEAR, self.a)
        self.perm(BEAR, self.a)
        self.perm(BEAR, self.b)
        self.assertEqual(self.enter(CAPTAIN).p1, 2)

    def test_graveyard_cards(self):
        self.a.graveyard = [BEAR, BEAR, GATE]
        self.b.graveyard = [BEAR]
        self.assertEqual(self.enter(TROLL).p1, 2)

    def test_two_per_thing(self):
        self.perm(HUMAN, self.a)
        token = card("Test Token", "", "Creature — Human", "", 1, 1)
        token.is_token = True
        self.perm(token, self.a)
        self.perm(BEAR, self.a)
        self.assertEqual(self.enter(VANGUARD).p1, 2)                   # one nontoken Human, twice

    def test_with_a_counter(self):
        self.perm(BEAR, self.a).counters["+1/+1"] = 2
        self.perm(BEAR, self.a)
        self.assertEqual(self.enter(AVATAR).p1, 1)

    def test_with_a_counter_means_any_kind(self):
        from mtgsim.permanent_templates import matches, selector
        spec = selector("creatures you control with a counter on them", plural=True)
        stunned = self.perm(BEAR, self.a)
        stunned.counters["stun"] = 1
        plain = self.perm(BEAR, self.a)
        self.assertTrue(matches(self.game, stunned, spec, self.a, None))
        self.assertFalse(matches(self.game, plain, spec, self.a, None))

    def test_lands_counted(self):
        self.perm(GATE, self.a)
        self.perm(GATE, self.a)
        self.assertEqual(self.enter(GARGOYLE).p1, 2)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Squad Captain", "Golgari Grave-Troll", "Golgari Raiders", "Bloodcrazed Paladin", "Grizzly Ghoul",
                     "Gatekeeper Gargoyle", "Diregraf Colossus", "Voracious Brood", "Luxknight Breacher",
                     "Avatar of the Resolute", "Hamlet Vanguard", "Sautekh Immortal"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()

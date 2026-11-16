"""#634 VOTE: will of the council and council's dilemma, the extra-vote statics, how each player votes, and the AI
casting vote spells."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


def vote_of(card_def):
    effects = list(card_def.spell_effects) + [e for t in card_def.triggers for e in t.effects] + \
        list(card_def.etb_effects)
    return next(e for e in effects if e.kind == "vote")


class Parse(unittest.TestCase):
    def test_majority_branches(self):
        effects, bad = _parse_effects(
            "Starting with you, each player votes for time or knowledge. If time gets more votes, take an extra turn "
            "after this one. If knowledge gets more votes or the vote is tied, draw three cards.")
        self.assertEqual(bad, [])
        self.assertEqual([e.kind for e in effects], ["vote"])
        branches = effects[0].data["branches"]
        self.assertEqual(branches["time"][0], False)
        self.assertEqual(branches["knowledge"][0], True)
        self.assertEqual([(e.kind, e.amount) for e in branches["knowledge"][1]], [("draw", 3)])

    def test_per_vote_compound_keeps_the_subject(self):
        effects, bad = _parse_effects(
            "Starting with you, each player votes for death or taxes. Each opponent sacrifices a creature for each "
            "death vote and discards a card for each taxes vote.")
        self.assertEqual(bad, [])
        per = effects[0].data["per_vote"]
        self.assertEqual([e.kind for e in per["death"]], ["edict"])
        self.assertEqual([e.kind for e in per["taxes"]], ["discard"])

    def test_twice_the_number_of_votes(self):
        per = vote_of(db("Emissary Green")).data["per_vote"]
        self.assertEqual([(e.kind, e.amount) for e in per["profit"]], [("token", 2)])
        self.assertEqual([e.kind for e in per["security"]], ["p1_counters"])

    def test_extra_vote_statics(self):
        for name in ("Brago's Representative", "Ballot Broker", "Tivit, Seller of Secrets"):
            self.assertEqual(db(name).advanced_rules.get("extra_votes"), 1, name)

    def test_refusals(self):
        for text in (
                # a real choice of target in an outcome
                "Starting with you, each player votes for fire or ice. If fire gets more votes, ~ deals 3 damage to "
                "target creature.",
                # an option the vote doesn't have
                "Starting with you, each player votes for fire or ice. If water gets more votes, draw a card.",
                # three options
                "Starting with you, each player votes for blue, black, or red. Draw a card.",
                # a branch without a vote
                "If fire gets more votes, draw a card."):
            with self.subTest(text=text):
                self.assertTrue(_parse_effects(text)[1], text)

    def test_real_cards_full(self):
        for name in ("Bite of the Black Rose", "Coercive Portal", "Plea for Power", "Tyrant's Choice",
                     "Capital Punishment", "Emissary Green", "Lieutenants of the Guard", "Orchard Elemental",
                     "Tivit, Seller of Secrets", "Travel Through Caradhras", "Brago's Representative", "Ballot Broker"):
            self.assertTrue(db(name).fully_supported, name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Game_(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def resolve(self, name):
        c = db(name)
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [None] * len(c.spell_effects), card=c,
                                         name=c.name))
        self.game.resolve_top()
        self.game.settle()

    def votes(self):
        return [e.split(": ", 1)[1] for e in self.game.events if "votes for" in e]

    def test_tyrants_choice_tie_goes_to_torture(self):
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.resolve("Tyrant's Choice")
        self.assertEqual(self.votes(), ["votes for death", "votes for torture"])    # each in their own interest
        self.assertEqual(self.b.life, 16)
        self.assertIn(bear, self.b.battlefield)

    def test_capital_punishment_each_vote_counts(self):
        bears = [self.game.enter_battlefield(self.b, BEAR) for _ in range(2)]
        self.b.hand = [ISLAND] * 3
        self.resolve("Capital Punishment")
        self.assertEqual(self.votes(), ["votes for death", "votes for taxes"])
        self.assertEqual(sum(x in self.b.battlefield for x in bears), 1)
        self.assertEqual(len(self.b.hand), 2)

    def test_extra_vote(self):
        self.game.enter_battlefield(self.a, db("Tivit, Seller of Secrets"))     # it votes twice itself
        self.game.settle()
        tokens = sorted(x.card.name for x in self.a.battlefield if x.card.is_token)
        self.assertEqual(len(tokens), 3)
        self.assertTrue(any("(2 votes)" in v for v in self.votes()))

    def test_coercive_portal_upkeep_vote(self):
        portal = self.game.enter_battlefield(self.a, db("Coercive Portal"))
        self.game.enter_battlefield(self.b, db("Serra Angel"))
        self.game.begin_upkeep(self.a)
        self.game.settle()
        # the controller votes carnage (their Angel is worth more than the Portal), the opponent homage: a tie draws
        self.assertEqual(self.votes(), ["votes for carnage", "votes for homage"])
        self.assertIn(portal, self.a.battlefield)
        self.assertEqual(len(self.a.hand), 1)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class AI(unittest.TestCase):
    def test_casts_a_vote_spell_at_the_opponent(self):
        a = Player("a", [], HeuristicAI())
        b = Player("b", [], HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 3, "main1"
        a.library = b.library = [ISLAND] * 20
        for _ in range(6):
            game.enter_battlefield(a, SWAMP)
        mine = game.enter_battlefield(a, BEAR)
        theirs = [game.enter_battlefield(b, BEAR) for _ in range(2)]
        b.hand = [ISLAND] * 3
        a.hand = [db("Capital Punishment")]
        a.ai.main_phase(game, a)
        game.settle()
        self.assertEqual(a.hand, [])
        self.assertIn(mine, a.battlefield)
        self.assertEqual(sum(x in b.battlefield for x in theirs), 1)
        self.assertEqual(len(b.hand), 2)


if __name__ == "__main__":
    unittest.main()

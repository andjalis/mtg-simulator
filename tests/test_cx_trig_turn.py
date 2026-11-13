"""Temporary triggers created by an effect: "Whenever <event> this turn, <effects>" (mtgsim.cx_trig_turn, #399)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cx_trig_turn import parse
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
MINOTAUR = card("Test Minotaur", "{1}{R}", "Creature — Minotaur", "", 2, 2)


def spell(text, name="Test Spell", cost="{R}", types="Instant"):
    c = card(name, cost, types, text)
    assert c.unsupported == [], (text, c.unsupported)
    return c


class Parsing(unittest.TestCase):
    def test_shapes(self):
        e = parse("Whenever a creature attacks this turn, put a +1/+1 counter on it.")[0]
        self.assertEqual((e.kind, e.data["head"], e.data["once"]), ("cx_turn_trigger", "Whenever a creature attacks",
                                                                    False))
        self.assertEqual([x.kind for x in e.data["effects"]], ["p1_counters"])
        e = parse("When a creature dies this turn, you gain 1 life.")[0]
        self.assertTrue(e.data["once"])
        self.assertIsNotNone(parse("Whenever you cast a creature spell this turn, draw a card."))

    def test_refusals(self):
        for s in ("When that creature dies this turn, its controller gets a poison counter.",     # back-reference
                  "When it dies under your control this turn, draw two cards.",
                  "Whenever a creature you control dealt damage this way dies this turn, add {R}.",
                  "Whenever ~ blocks this turn, ~ gets +2/+0 until end of turn.",
                  "Whenever a creature attacks this turn, ~ deals 1 damage to it.",                # "~" in the body
                  "Whenever you frobnicate this turn, draw a card.",                               # unknown head
                  "Whenever a creature attacks this turn, it frobs."):                             # unknown effect
            self.assertIsNone(parse(s), s)


class Behaviour(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 5, HeuristicAI())
        self.b = Player("b", [BEAR] * 5, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.a.library = [ISLAND] * 10
        self.b.library = [ISLAND] * 10

    def cast(self, c, by=None):
        effects = list(c.spell_effects)
        self.game.stack.append(StackItem(by or self.a, effects, [None] * len(effects), card=c, name=c.name))
        self.game.resolve_top()

    def settle(self):
        while self.game.pending or self.game.stack:
            self.game.flush_triggers()
            if self.game.stack:
                self.game.resolve_top()

    def test_it_is_the_attacking_creature_and_filters_hold(self):
        self.cast(spell("Whenever a Minotaur attacks this turn, it gets +2/+0 until end of turn."))
        mino, bear = Permanent(MINOTAUR, self.a), Permanent(BEAR, self.a)
        self.a.battlefield += [mino, bear]
        for x in (mino, bear):
            self.game.fire(self.a, "attacks", x)
        self.settle()
        self.assertEqual((mino.power, bear.power), (4, 2))

    def test_its_controller_is_the_blockers(self):
        self.cast(spell("Whenever a creature blocks this turn, its controller loses 1 life."))
        blocker, attacker = Permanent(BEAR, self.b), Permanent(MINOTAUR, self.a)
        self.b.battlefield.append(blocker)
        self.a.battlefield.append(attacker)
        self.game.fire(self.b, "blocks", blocker, context=attacker)
        self.settle()
        self.assertEqual((self.a.life, self.b.life), (20, 19))

    def test_expires_at_end_of_turn_and_when_triggers_once(self):
        self.cast(spell("Whenever you cast a creature spell this turn, draw a card.", types="Sorcery"))
        self.cast(spell("When a creature dies this turn, you gain 3 life."))
        self.a.battlefield += [Permanent(FOREST, self.a) for _ in range(4)]
        self.a.hand = [BEAR, BEAR]
        self.assertTrue(self.game.cast(self.a, self.a.hand[0]))
        self.settle()
        self.assertEqual(len(self.a.hand), 2)                       # cast one (-1), drew one (+1)
        for _ in range(2):
            victim = Permanent(BEAR, self.b)
            self.b.battlefield.append(victim)
            self.game.destroy(victim)
            self.settle()
        self.assertEqual(self.a.life, 23)                           # "When": once only
        self.game.turn += 1                                         # next turn: the watcher is gone
        self.a.battlefield = [Permanent(FOREST, self.a) for _ in range(4)]
        hand = len(self.a.hand)
        bear = next(c for c in self.a.hand if c.name == "Grizzly Bears")
        self.assertTrue(self.game.cast(self.a, bear))
        self.settle()
        self.assertEqual(len(self.a.hand), hand - 1)                # no draw any more
        self.assertEqual(self.game.__dict__.get("cx_turn_watchers"), [])

    def test_copy_of_that_creature(self):
        dup = spell("Whenever a nontoken creature an opponent controls enters this turn, create a token that's a copy "
                    "of that creature.", cost="{U}")
        self.cast(dup)
        self.game.enter_battlefield(self.b, MINOTAUR)
        self.settle()
        self.assertEqual([(x.card.name, x.card.is_token) for x in self.a.battlefield], [("Test Minotaur", True)])
        self.game.enter_battlefield(self.a, BEAR)                    # ours: not watched
        self.settle()
        self.assertEqual(len(self.a.battlefield), 2)

    def test_ai_casts_it(self):
        glimpse = spell("Whenever you cast a creature spell this turn, draw a card.", cost="{G}", types="Sorcery")
        self.a.battlefield = [Permanent(FOREST, self.a)]
        self.a.hand = [glimpse]
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn(glimpse, self.a.graveyard)
        self.assertEqual(len(self.game.cx_turn_watchers), 1)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_statuses(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Battle Cry", "Death Frenzy", "Glimpse of Nature", "Touch of the Horned God", "Rite of Harmony",
                     "Basri, Devoted Paladin"):
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)
        for name in ("Virulent Wound", "Desperate Measures", "Reckless Blaze"):
            self.assertEqual(card_coverage(db.get(name)).status, "partial", name)


if __name__ == "__main__":
    unittest.main()

"""#839: emblems with a triggered ability ("You get an emblem with "At the beginning of your end step, ...""), kept in
the owner's command zone (Player.command) and firing like a permanent's triggers, but never on the battlefield."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


def emblems(c):
    return [e for _, effs in c.loyalty_abilities for e in effs if e.kind == "emblem_obj"]


WALKER = ("Legendary Planeswalker — Test", "+1: You gain 1 life.\n−7: You get an emblem with \"{body}\"")


def walker(body):
    types, text = WALKER
    return card("Test Walker", "{3}{W}", types, text.replace("{body}", body))


class Parse(unittest.TestCase):
    def test_triggered_bodies(self):
        e, = emblems(walker("At the beginning of your end step, you gain 2 life."))
        self.assertEqual(e.data["who"], "you")
        self.assertEqual([t.event for t in e.data["triggers"]], ["end_step"])
        e, = emblems(walker("Whenever you cast a creature spell, draw a card."))
        self.assertEqual([t.event for t in e.data["triggers"]], ["cast_spell"])

    def test_this_emblem_is_the_source(self):
        e, = emblems(walker("Whenever you cast an instant or sorcery spell, this emblem deals 2 damage to any target."))
        self.assertEqual([x.kind for x in e.data["triggers"][0].effects], ["damage"])

    def test_opponent_gets_it(self):
        c = card("Test Walker", "{3}{B}", WALKER[0], "+1: You gain 1 life.\n−8: Target opponent gets an emblem with "
                 "\"Whenever a player draws a card, you lose 2 life.\"")
        e, = emblems(c)
        self.assertEqual(e.data["who"], "opponent")

    def test_refusals(self):
        # a body the readers don't match exactly, or a static ability outside anthems / keyword grants / hand size,
        # stays unparsed: the card is partial, not silently full
        for body in ("Instant and sorcery spells you cast have storm.", "Your opponents can't cast noncreature spells.",
                     "Creatures you control have base power and toughness 9/9.",
                     "At the beginning of your end step, do a little dance."):
            with self.subTest(body=body):
                c = walker(body)
                self.assertEqual(emblems(c), [])
                self.assertFalse(c.fully_supported)

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_real_cards(self):
        for name in ("Ajani, Adversary of Tyrants", "Garruk, Caller of Beasts", "Ob Nixilis Reignited",
                     "Koth, Fire of Resistance", "Huatli, Radiant Champion"):
            c = db(name)
            self.assertTrue(c.fully_supported, name)
            self.assertTrue(emblems(c), name)
        self.assertFalse(db("Narset Transcendent").fully_supported)            # a lock emblem: not read yet


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        self.turn(self.a)
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def turn(self, p):
        self.game.active_idx = self.game.players.index(p)
        for q in self.game.players:
            q.my_turn = q is p

    def put(self, p, c):
        x = self.game.enter_battlefield(p, db(c) if isinstance(c, str) else c)
        self.game.settle()
        return x

    def ultimate(self, name, loyalty=None):
        pw = self.put(self.a, name)
        idx = next(i for i, (_, effs) in enumerate(pw.card.loyalty_abilities) if any(e.kind == "emblem_obj" for e in effs))
        cost = pw.card.loyalty_abilities[idx][0]
        pw.counters["loyalty"] = -cost if loyalty is None else loyalty
        return pw, idx


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Play(Base):
    def test_ajani_loyalty_rules_and_end_step_cats(self):
        pw, idx = self.ultimate("Ajani, Adversary of Tyrants", loyalty=6)
        self.assertFalse(self.game.activate_loyalty(self.a, pw, idx))          # −7 with 6 loyalty: can't pay
        pw.counters["loyalty"] = 7
        self.game.step = "combat"
        self.assertFalse(self.game.activate_loyalty(self.a, pw, idx))          # sorcery speed only
        self.game.step = "main1"
        self.assertTrue(self.game.activate_loyalty(self.a, pw, idx))
        self.game.settle()
        self.assertNotIn(pw, self.a.battlefield)                               # 0 loyalty: it's gone
        self.assertEqual(len(self.a.command), 1)
        self.assertNotIn(self.a.command[0], self.a.battlefield)                # the emblem isn't a permanent
        self.game.begin_end_step(self.a)
        self.game.settle()
        cats = [x for x in self.a.creatures if x.card.is_token]
        self.assertEqual(len(cats), 3)
        self.assertTrue(all(x.has("lifelink") for x in cats))
        self.turn(self.b)
        self.game.begin_end_step(self.b)                                       # "your end step" only
        self.game.settle()
        self.assertEqual(len([x for x in self.a.creatures if x.card.is_token]), 3)

    def test_once_per_turn(self):
        pw = self.put(self.a, "Ajani, Adversary of Tyrants")
        self.put(self.a, BEAR)                     # +1: counters on "up to two" creatures; two, since a single one is
        self.put(self.a, BEAR)                     # refused today (both targets parse as required, a separate issue)
        pw.counters["loyalty"] = 10
        self.assertTrue(self.game.activate_loyalty(self.a, pw, 0))
        self.game.settle()
        self.assertFalse(self.game.activate_loyalty(self.a, pw, 2))           # one loyalty ability per turn

    def test_emblem_survives_a_wrath(self):
        pw, idx = self.ultimate("Ajani, Adversary of Tyrants")
        self.assertTrue(self.game.activate_loyalty(self.a, pw, idx))
        self.game.settle()
        wrath = card("Test Wrath", "{2}{W}{W}", "Sorcery", "Destroy all creatures.")
        from mtgsim.engine import StackItem
        self.game.stack.append(StackItem(self.a, list(wrath.spell_effects), [None] * len(wrath.spell_effects),
                                         card=wrath, name=wrath.name))
        self.game.resolve_top()
        self.game.settle()
        self.assertEqual(len(self.a.command), 1)
        self.game.begin_end_step(self.a)
        self.game.settle()
        self.assertEqual(len(self.a.creatures), 3)

    def test_opponents_emblem_hits_them_on_every_draw(self):
        pw, idx = self.ultimate("Ob Nixilis Reignited")
        self.assertTrue(self.game.activate_loyalty(self.a, pw, idx))
        self.game.settle()
        self.assertEqual((len(self.a.command), len(self.b.command)), (0, 1))
        self.game.draw(self.a)
        self.game.settle()
        self.game.draw(self.b)
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (20, 16))                # "whenever a player draws": both draws

    def test_cast_trigger_from_the_command_zone(self):
        pw, idx = self.ultimate("Garruk, Caller of Beasts")
        self.assertTrue(self.game.activate_loyalty(self.a, pw, idx))
        self.game.settle()
        self.a.library = [db("Craw Wurm")] + [ISLAND] * 5
        for _ in range(2):
            self.put(self.a, card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)"))
        self.a.hand = [db("Grizzly Bears")]
        self.assertTrue(self.game.cast(self.a, self.a.hand[0]))
        self.game.settle()
        self.assertEqual(sorted(x.card.name for x in self.a.creatures), ["Craw Wurm", "Grizzly Bears"])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class AI(Base):
    def test_ai_takes_the_emblem_ultimate(self):
        pw = self.put(self.a, "Ajani, Adversary of Tyrants")
        pw.counters["loyalty"] = 7
        self.put(self.a, BEAR)
        self.assertEqual(self.a.ai.choose_loyalty(self.game, self.a, pw), 2)

    def test_ai_values_an_emblem(self):
        from mtgsim.engine.policy import _mode_value
        e, = emblems(db("Ajani, Adversary of Tyrants"))
        self.assertGreater(_mode_value(self.game, self.a, [e]), 0)
        e, = emblems(db("Ob Nixilis Reignited"))
        self.assertGreaterEqual(_mode_value(self.game, self.a, [e]), 0)


if __name__ == "__main__":
    unittest.main()

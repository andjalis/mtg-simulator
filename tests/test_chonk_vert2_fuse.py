"""Fuse: the split-card cast path (chonk/vert batch 2) — parse, single halves, and fused casts."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import FOREST, PLAINS

import json
import sqlite3

DB = sqlite3.connect("mtgsim/data/cards.sqlite3")
RAW = {k: json.loads(d) for k, d in DB.execute("select key, data from cards")}


def real(name):
    from mtgsim import cards
    return cards.card_from_scryfall(RAW[name.lower()])


ALIVE = real("Alive // Well")


class ParseFuse(unittest.TestCase):
    def test_fuse_alt_cost_is_both_halves(self):
        fuse = next(a for a in ALIVE.alt_costs if a.kind == "fuse")
        self.assertEqual(fuse.cost, {"generic": 3, "W": 1, "G": 1})     # {1}{G} + {2}{W}
        self.assertEqual([e.kind for e in fuse.effects], ["token", "gain_life"])
        self.assertEqual(ALIVE.split_right.name, "Well")

    def test_split_half_still_castable(self):
        split = next(a for a in ALIVE.alt_costs if a.kind == "split")
        self.assertEqual(split.cost, {"generic": 0, "W": 1})            # Well's own cost {W}

    def test_fuse_cards_have_no_leftover_wording(self):
        for name in ("Alive // Well", "Beck // Call", "Breaking // Entering", "Turn // Burn",
                     "Ready // Willing", "Give // Take", "Armed // Dangerous"):
            c = real(name)
            self.assertFalse([u for u in c.unsupported if "Fuse" in u], (name, c.unsupported))


class FuseEngine(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(3))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [PLAINS] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None
        for _ in range(3):
            self.g.enter_battlefield(self.a, PLAINS)
            self.g.enter_battlefield(self.a, FOREST)
        self.g.settle()

    def option(self, kind):
        return next(o for o in self.g.spell_options(self.a) if self.g._origin(o)[1] == kind)

    def pick(self, kind):
        self.a.hand = [ALIVE]          # the physical card stays in hand; cast() moves it
        return self.option(kind)

    def test_fuse_variant_is_a_cast_option(self):
        self.a.hand = [ALIVE]
        names = [o.name for o in self.g.spell_options(self.a)]
        self.assertEqual(names, ["Alive", "Alive (Well)", "Alive (fuse)"])

    def test_fused_cast_resolves_both_halves(self):
        self.assertTrue(self.g.cast(self.a, self.pick("fuse")))
        self.g.settle()
        tokens = [x for x in self.a.battlefield if "Centaur" in x.card.subtypes]
        self.assertEqual(len(tokens), 1)                # Alive: the 3/3 Centaur
        self.assertEqual(self.a.life, 22)               # Well: 2 life for the one creature

    def test_right_half_alone(self):
        from tests.test_templates import BEAR
        bear = self.g.enter_battlefield(self.a, BEAR)
        bear.sick = False
        self.g.settle()
        self.assertTrue(self.g.cast(self.a, self.pick("split")))
        self.g.settle()
        self.assertEqual([x.card.name for x in self.a.battlefield if x.is_creature],
                         ["Grizzly Bears"])            # Well alone: no Centaur
        self.assertEqual(self.a.life, 22)              # 2 life for the one creature

    def test_left_half_alone(self):
        self.a.hand = [ALIVE]
        self.assertTrue(self.g.cast(self.a, ALIVE))
        self.g.settle()
        tokens = [x for x in self.a.battlefield if "Centaur" in x.card.subtypes]
        self.assertEqual(len(tokens), 1)
        self.assertEqual(self.a.life, 20)               # the Well half never happened


if __name__ == "__main__":
    unittest.main()

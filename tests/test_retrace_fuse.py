"""Retrace (cast from the graveyard by discarding a land) and split cards (the right half, and Fuse)."""
import random
import unittest

from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

LOOP = card("Test Loop", "{1}{U}", "Instant", "Draw a card.\nRetrace")


def split(left, right, fuse=False):
    def face(name, cost, types, text):
        return {"name": name, "mana_cost": cost, "type_line": types, "oracle_text": text}
    return card_from_scryfall({
        "name": f"{left[0]} // {right[0]}", "layout": "split", "type_line": f"{left[2]} // {right[2]}", "cmc": 2,
        "mana_cost": f"{left[1]} // {right[1]}",
        "card_faces": [face(*left[:3], left[3] + ("\nFuse" if fuse else "")),
                       face(*right[:3], right[3] + ("\nFuse" if fuse else ""))]})


ZAP_FREEZE = split(("Test Zap", "{R}", "Instant", "~ deals 2 damage to any target."),
                   ("Test Freeze", "{1}{U}", "Instant", "Tap target permanent.\nDraw a card."))
GROW_GLOW = split(("Test Grow", "{G}", "Instant", "Target creature gets +2/+2 until end of turn."),
                  ("Test Glow", "{W}", "Instant", "You gain 3 life."), fuse=True)


class RetraceFuse(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c, n=1):
        for _ in range(n):
            perm = self.game.enter_battlefield(who, c)
            perm.sick = False
        self.game.settle()
        return perm

    def option(self, kind):
        return next((o for o in self.game.spell_options(self.a) if self.game._origin(o)[1] == kind), None)

    def test_templates(self):
        for c in (LOOP, ZAP_FREEZE, GROW_GLOW):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(sorted(a.kind for a in GROW_GLOW.alt_costs), ["fuse", "split"])

    def test_retrace_discards_a_land_and_returns_to_the_graveyard(self):
        self.put(self.a, ISLAND, 2)
        self.a.graveyard.append(LOOP)
        self.a.hand[:] = [ISLAND]
        self.assertIsNone(self.option("retrace"))            # the only land is kept for the land drop
        self.a.land_played = True
        retrace = self.option("retrace")
        self.assertIsNotNone(retrace)
        self.assertTrue(self.game.cast(self.a, retrace))
        self.game.settle()
        self.assertIn(LOOP, self.a.graveyard)
        self.assertEqual([c.name for c in self.a.hand], ["Island"])   # the drawn card; the land was discarded
        self.assertEqual(sum(c.name == "Island" for c in self.a.graveyard), 1)

    def test_split_right_half(self):
        self.put(self.a, ISLAND, 2)
        bear = self.put(self.b, BEAR)
        self.a.hand[:] = [ZAP_FREEZE]
        freeze = self.option("split")
        self.assertTrue(self.game.cast(self.a, freeze, [bear, None]))
        self.game.settle()
        self.assertTrue(bear.tapped)
        self.assertIn(ZAP_FREEZE, self.a.graveyard)

    def test_fuse_casts_both_halves(self):
        self.put(self.a, card("Test Savannah", "", "Land", "{T}: Add {G} or {W}."), 2)
        bear = self.put(self.a, BEAR)
        self.a.hand[:] = [GROW_GLOW]
        fused = self.option("fuse")
        self.assertEqual(fused.mana_cost, {"generic": 0, "G": 1, "W": 1})
        self.assertTrue(self.game.cast(self.a, fused, [bear, None]))
        self.game.settle()
        self.assertEqual((bear.power, self.a.life), (4, 23))


if __name__ == "__main__":
    unittest.main()

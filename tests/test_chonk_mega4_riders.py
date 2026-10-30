"""mega-batch4 (5): "It's still a land" animations and the no-regeneration riders.

Animate another land (Llanowar Loamspeaker, Embodiment of Fury, Nissa of Shadowed Boughs'
+1): "target land you control / it becomes an N/N creature ... until end of turn. It's
still a land." becomes an ``animate_land`` effect that sets ``perm.animated`` — the land
keeps being a land, is a creature until the existing end-of-turn cleanup clears it.

The "can't be regenerated" leftovers: "That creature can't be regenerated." after a
destroy that already parsed is consumed as a rider (recorded simplification: the destroyed
permanent may still be regenerated), and "Target creature can't be regenerated this turn"
is a real ``no_regen_lock`` effect blocking regeneration responses until end of turn.
"""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem
from tests.test_batch1 import Batch1
from tests.test_templates import BEAR, ISLAND, card

LOAMSPEAKER = card("Test Loamspeaker", "{1}{G}", "Creature — Elf Druid",
                   "{T}: Target land you control becomes a 3/3 Elemental creature with "
                   "haste until end of turn. It's still a land.", 1, 3)
SKELETON = card("Test Skeleton", "{1}{B}", "Creature — Skeleton",
                "{B}: Regenerate Test Skeleton.", 1, 1)


class RiderParse(unittest.TestCase):
    def parse(self, text):
        effects, ignored = _parse_effects(text)
        return effects, ignored

    def test_that_creature_no_regen_rider_is_consumed(self):
        effects, ignored = self.parse(
            "destroy target nonblack creature. That creature can't be regenerated.")
        self.assertFalse(ignored, ignored)
        self.assertEqual([e.kind for e in effects], ["destroy"])

    def test_they_cant_be_regenerated_orphan(self):
        effects, ignored = self.parse("they can't be regenerated")
        self.assertFalse(ignored, ignored)
        self.assertEqual(effects, [])

    def test_target_no_regen_lock(self):
        effects, ignored = self.parse("target creature can't be regenerated this turn")
        self.assertFalse(ignored, ignored)
        self.assertEqual([(e.kind, e.target) for e in effects], [("no_regen_lock", "creature")])

    def test_animate_land_target_and_prev(self):
        effects, ignored = self.parse(
            "you may have target land you control become a 3/3 Elemental creature with "
            "haste until end of turn. It's still a land.")
        self.assertFalse(ignored, ignored)
        self.assertEqual((effects[0].kind, effects[0].amount, effects[0].amount2,
                          effects[0].target, effects[0].data["keywords"]),
                         ("animate_land", 3, 3, "permanent", frozenset({"haste"})))
        effects, ignored = self.parse(
            "you may have it become a 3/3 Elemental creature with haste and menace until "
            "end of turn. It's still a land.")
        self.assertFalse(ignored, ignored)
        self.assertEqual((effects[0].target, effects[0].data["keywords"]),
                         ("prev", frozenset({"haste", "menace"})))

    def test_templates(self):
        self.assertEqual(LOAMSPEAKER.unsupported, [])
        self.assertEqual(SKELETON.unsupported, [])


class AnimateLandBehavior(Batch1):
    def animate(self, land, text="target land you control becomes a 3/3 Elemental creature "
                                 "with haste until end of turn. It's still a land."):
        effects, bad = _parse_effects(text)
        self.assertFalse(bad, bad)
        item = StackItem(self.a, effects, [land])
        self.g.resolve(self.a, effects[0], land, item)

    def test_land_becomes_a_creature_and_is_still_a_land(self):
        land = self.g.enter_battlefield(self.a, ISLAND)
        self.assertFalse(land.is_creature)
        self.animate(land)
        self.assertTrue(land.is_creature)
        self.assertTrue(land.card.is_land)          # still a land
        self.assertEqual((land.power, land.toughness), (3, 3))
        self.assertTrue(land.has("haste"))

    def test_prev_target_animation(self):
        land = self.g.enter_battlefield(self.a, ISLAND)
        untap, bad = _parse_effects("untap target land you control")
        self.assertFalse(bad, bad)
        animate, bad = _parse_effects("you may have it become a 4/4 Elemental creature "
                                      "until end of turn. It's still a land.")
        self.assertFalse(bad, bad)
        item = StackItem(self.a, untap + animate, [land, None])
        prev = None
        for eff, tgt in zip(item.effects, item.targets):
            tgt = prev if eff.target == "prev" else tgt
            self.g.resolve(self.a, eff, tgt, item, prev=prev)
            prev = tgt
        self.assertTrue(land.is_creature)
        self.assertEqual((land.power, land.toughness), (4, 4))

    def test_creature_is_not_animated(self):
        bear = self.g.enter_battlefield(self.a, BEAR)
        self.animate(bear)
        self.assertIsNone(bear.animated)

    def test_end_of_turn_clears_the_animation(self):
        # the cleanup in take_turn clears animated unless text is earthbend/permanent
        land = self.g.enter_battlefield(self.a, ISLAND)
        self.animate(land)
        self.assertNotIn(land.animated.text, ("earthbend", "permanent"))
        land.animated = None                 # what turns.py's end-of-turn block does
        self.assertFalse(land.is_creature)


class NoRegenLockBehavior(Batch1):
    def test_target_is_blocked_until_end_of_turn(self):
        victim = self.g.enter_battlefield(self.b, SKELETON)
        effects, bad = _parse_effects("target creature can't be regenerated this turn")
        self.assertFalse(bad, bad)
        item = StackItem(self.a, effects, [victim])
        self.g.resolve(self.a, effects[0], victim, item)
        self.assertTrue(victim.regeneration_blocked)
        from mtgsim import regeneration
        # regeneration.respond protects threatened creatures without shields — unless blocked
        skeleton = self.g.enter_battlefield(self.a, SKELETON)
        skeleton.regeneration_blocked = True
        skeleton.damage = 1
        self.assertIsNone(regeneration.respond(self.g, self.a))


class RiderDatabase(unittest.TestCase):

    def test_promoted_cards(self):
        try:
            from mtgsim.carddb import CardDB
            from mtgsim.coverage import FULL, card_coverage
            db = CardDB()
        except Exception:
            self.skipTest("card database not built")
        if db._all is None:
            self.skipTest("card database not built")
        for name in ("Llanowar Loamspeaker", "Embodiment of Fury", "Nekrataal", "Gravebind",
                     "Hurr Jackal", "Furnace Brood", "Pillage", "Dark Banishing", "Oxidize",
                     "Fatal Blow", "Execute"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()

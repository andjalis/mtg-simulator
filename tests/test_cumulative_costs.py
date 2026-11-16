"""#646 slice 4: cumulative upkeep with non-mana costs (CR 702.24, mtgsim.cumulative_costs)."""
import unittest

from mtgsim.batch1_templates import on_upkeep
from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, ISLAND, PLAINS, card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")


def cu(text, p=3, t=3, types="Creature — Beast"):
    return card("Test Upkeeper", "{2}", types, f"Cumulative upkeep{text}", p, t)


NISHOBA = cu(" {G} or {W}", 6, 6)
KRAKEN = cu("—Sacrifice a land.", 11, 11)
SOULGORGER = cu("—Sacrifice a creature.", 8, 8)
SPHINX = cu("—Discard a card.", 4, 4)
ABOROTH = cu("—Put a -1/-1 counter on this creature.", 9, 9)
ANCIENT = cu("—Put a +1/+1 counter on a creature an opponent controls.", 5, 5)
SHARDS = cu("—An opponent gains 1 life.", 1, 8)
GRUNT = cu("—Put two cards from a single graveyard on the bottom of their owner's library.", 8, 8)
TOKEN = card("Spirit", "", "Token Creature — Spirit", "", 1, 1)


class Parsing(unittest.TestCase):
    def test_positives(self):
        for c, want in ((NISHOBA, ("or", ({"generic": 0, "G": 1}, {"generic": 0, "W": 1}))),
                        (KRAKEN, ("sac", "land")), (SOULGORGER, ("sac", "creature")), (SPHINX, ("discard", 1)),
                        (ABOROTH, ("self_m1", 1)), (ANCIENT, ("opp_p1", 1)), (SHARDS, ("opp_life", 1)),
                        (GRUNT, ("gy_bottom", 2))):
            self.assertEqual(c.unsupported, [], c.name)
            self.assertEqual(c.advanced_rules["cumulative_upkeep"], want)

    def test_refusals(self):
        for text in (" {G} or {G}", "—Sacrifice two lands.", "—Discard two cards.", "—Flip a coin.",
                     "—Put a +1/+1 counter on a creature you control.", "—Draw a card.",
                     "—Gain control of a land you don't control."):
            c = cu(text)
            self.assertTrue(c.unsupported, text)
            self.assertNotIn("cumulative_upkeep", c.advanced_rules, text)


class Engine(Base):
    def upkeep(self, perm):
        on_upkeep(self.game, self.a)
        self.game.settle()
        return perm in self.a.battlefield

    def test_or_cost_any_mix(self):
        """CR 702.24a-b: each age counter's "{G} or {W}" is chosen separately: G + W pays for two counters."""
        x = self.perm(NISHOBA, self.a)
        x.counters["age"] = 1
        forest, plains = Permanent(FOREST, self.a), Permanent(PLAINS, self.a)
        self.a.battlefield += [forest, plains]
        self.assertTrue(self.upkeep(x))
        self.assertEqual(x.counters["age"], 2)
        self.assertTrue(forest.tapped and plains.tapped)

    def test_unpaid_or_cost_sacrifices(self):
        x = self.perm(NISHOBA, self.a)
        self.a.battlefield.append(Permanent(ISLAND, self.a))
        self.assertFalse(self.upkeep(x))
        self.assertIn(NISHOBA, self.a.graveyard)

    def test_sacrifice_a_land_per_counter(self):
        """CR 702.24a: with two age counters, two lands; all of the cost or none of it."""
        x = self.perm(KRAKEN, self.a)
        x.counters["age"] = 1
        self.a.battlefield += [Permanent(ISLAND, self.a) for _ in range(7)]
        self.assertTrue(self.upkeep(x))
        self.assertEqual(sum(y.card.is_land for y in self.a.battlefield), 5)

    def test_sacrifice_a_creature_needs_enough(self):
        x = self.perm(SOULGORGER, self.a)
        x.counters["age"] = 1
        self.perm(TOKEN, self.a)                    # one creature for two counters: can't pay
        self.assertFalse(self.upkeep(x))
        self.assertEqual(len(self.a.battlefield), 1)    # the token stays: nothing of the cost was paid

    def test_discard(self):
        x = self.perm(SPHINX, self.a)
        self.a.hand = [BEAR, BEAR]
        self.assertTrue(self.upkeep(x))
        self.assertEqual(len(self.a.hand), 1)

    def test_minus_counters_on_itself(self):
        x = self.perm(ABOROTH, self.a)
        x.counters["age"] = 2
        self.assertTrue(self.upkeep(x))
        self.assertEqual((x.power, x.toughness), (6, 6))

    def test_counters_on_an_opponents_creature(self):
        """The cost can't be paid without a creature an opponent controls (CR 118.3)."""
        x = self.perm(ANCIENT, self.a)
        self.assertFalse(self.upkeep(x))
        x = self.perm(ANCIENT, self.a)
        bear = self.perm(BEAR, self.b)
        self.assertTrue(self.upkeep(x))
        self.assertEqual(bear.power, 3)

    def test_opponent_gains_life(self):
        x = self.perm(SHARDS, self.a)
        x.counters["age"] = 2
        self.assertTrue(self.upkeep(x))
        self.assertEqual(self.b.life, 23)

    def test_graveyard_cards_to_the_bottom(self):
        """Two cards from a single graveyard per counter; each counter may use a different graveyard."""
        x = self.perm(GRUNT, self.a)
        x.counters["age"] = 1
        self.b.graveyard = [BEAR, BEAR, ISLAND]
        self.a.graveyard = [PLAINS, ISLAND]
        self.assertTrue(self.upkeep(x))
        self.assertEqual(self.b.graveyard, [ISLAND])
        self.assertEqual(self.a.graveyard, [])
        self.assertEqual(self.b.library[:2], [BEAR, BEAR])       # the bottom of their owner's library
        self.assertEqual(sorted(c.name for c in self.a.library[:2]), ["Island", "Plains"])     # any order


class HeuristicUse(Base):
    def test_ai_stops_paying_when_it_gets_steep(self):
        """The default AI pays while it is cheap and lets the permanent go once the price outgrows it."""
        x = self.perm(SPHINX, self.a)
        self.a.hand = [BEAR] * 5
        for _ in range(2):
            on_upkeep(self.game, self.a)
        self.assertIn(x, self.a.battlefield)
        on_upkeep(self.game, self.a)                # third counter: three discards is too much
        self.assertNotIn(x, self.a.battlefield)
        self.assertEqual(len(self.a.hand), 2)

    def test_ai_pays_lands_only_with_lands_to_spare(self):
        x = self.perm(KRAKEN, self.a)
        self.a.battlefield += [Permanent(ISLAND, self.a) for _ in range(4)]
        on_upkeep(self.game, self.a)                # 4 lands, would go down to 3: let the Kraken go
        self.assertNotIn(x, self.a.battlefield)
        self.assertEqual(sum(y.card.is_land for y in self.a.battlefield), 4)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Aboroth", "Jötun Owl Keeper", "Jötun Grunt", "Sheltering Ancient", "Krovikan Whispers",
                     "Arctic Nishoba", "Wall of Shards", "Phyrexian Soulgorger", "Vexing Sphinx", "Polar Kraken",
                     "Earthen Goo"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))

    def test_near_misses(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Braid of Fire", "Toy Boat"):
            self.assertEqual(card_coverage(db.get(name)).status, "partial", name)


if __name__ == "__main__":
    unittest.main()

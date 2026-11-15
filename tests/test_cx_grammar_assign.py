"""#313: "assigns combat damage equal to its toughness / mana value rather than its power" (mtgsim.cx_grammar_assign)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
LINE = "assigns combat damage equal to its toughness rather than its power."


class Assigns(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "combat"
        self.a.library = self.b.library = [ISLAND] * 10

    def put(self, owner, text="", p=1, t=4, types="Creature — Wall", cost="{3}"):
        c = card("Test " + types.split()[-1], cost, types, text, p, t) if p is not None else \
            card("Test Enchantment", cost, types, text)
        self.assertEqual(c.unsupported, [], text)
        x = self.g.enter_battlefield(owner, c)
        x.sick = False
        return x

    def swing(self, attacker):
        self.g.combat_damage(self.a, self.b, [attacker], {}, lambda c: True)
        return 20 - self.b.life

    def test_self(self):
        wall = self.put(self.a, "~ " + LINE)
        self.assertEqual(self.swing(wall), 4)

    def test_group_with_toughness_greater_than_power(self):
        self.put(self.a, "Each creature you control with toughness greater than its power " + LINE, None, None,
                 "Enchantment")
        tall, wide = self.put(self.a, "", 1, 4), self.put(self.a, "", 3, 2)
        self.assertEqual(self.swing(tall), 4)
        self.b.life = 20
        self.assertEqual(self.swing(wide), 3)
        tall.pump_p = 4            # now 5/4: power again
        self.b.life = 20
        self.assertEqual(self.swing(tall), 5)

    def test_group_is_the_controllers(self):
        self.put(self.b, "Each creature you control " + LINE, None, None, "Enchantment")
        mine = self.put(self.a, "", 1, 4)
        self.assertEqual(self.swing(mine), 1)

    def test_blocked_creature_uses_toughness_against_the_blocker(self):
        wall = self.put(self.a, "~ " + LINE, 0, 3)
        blocker = self.put(self.b, "", 2, 3, "Creature — Bear")
        self.g.combat_damage(self.a, self.b, [wall], {wall: [blocker]}, lambda c: True)
        self.assertNotIn(blocker, self.b.battlefield)

    def test_until_end_of_turn_on_a_target(self):
        wall = self.put(self.a, "", 0, 5)
        c = card("Test Spell", "{G}", "Instant", "Until end of turn, target creature you control " + LINE)
        self.assertEqual(c.unsupported, [])
        self.g.stack.append(StackItem(self.a, list(c.spell_effects), [wall], card=c, name=c.name))
        self.g.resolve_top()
        self.assertEqual(self.swing(wall), 5)
        self.g.turn += 1
        self.b.life = 20
        self.assertEqual(self.swing(wall), 0)

    def test_aura_host(self):
        wall = self.put(self.a, "", 1, 2)
        aura = self.put(self.a, "Enchant creature\nEnchanted creature gets +0/+2 and " + LINE, None, None,
                        "Enchantment — Aura")
        aura.aura_host = wall
        wall.auras.append(aura)
        self.assertEqual(self.swing(wall), 4)

    def test_mana_value(self):
        self.put(self.a, "Each creature assigns combat damage equal to its mana value rather than its power.", None,
                 None, "Enchantment")
        big = self.put(self.a, "", 1, 1, "Creature — Giant", "{5}{G}")
        self.assertEqual(self.swing(big), 6)

    def test_power_conditioned_anthem_still_rejected(self):
        # a static P/T change conditioned on P/T would read itself: still not a grammar anthem
        c = card("Test Anthem", "{2}", "Enchantment",
                 "Creatures you control with toughness greater than their power get +1/+0.")
        self.assertNotEqual(c.unsupported, [])
        self.assertIsNone(parse_sentence("Target creature assigns combat damage equal to its toughness rather than "
                                         "its power."))      # no duration: not a one-shot it can honour


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in ("Arcades, the Strategist", "The Kingpin of Crime", "Ancient Lumberknot", "Narod, the Beige Flower",
                     "Bill the Pony", "Streetwise Negotiator", "Bedrock Tortoise", "Gauntlets of Light",
                     "Ghalta the Immovable", "Treefolk Umbra"):
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)


if __name__ == "__main__":
    unittest.main()

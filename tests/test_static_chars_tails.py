"""#517 tails: "loses all other abilities, card types, and creature types" with named types (Darksteel Mutation),
a host rule guarded by the host's printed subtype (Aerial / Siege Modification), and "named <Name>" in a static
type change (Witness Protection)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card

DRAGON = card("Test Dragon", "{4}{R}{R}", "Creature — Dragon", "Flying", 5, 5)
MUTATION = card("Test Mutation", "{1}{W}", "Enchantment — Aura", "Enchant creature\nEnchanted creature is an Insect "
                "artifact creature with base power and toughness 0/1 and has indestructible, and it loses all other "
                "abilities, card types, and creature types.")
MOD = card("Test Mod", "{2}{U}", "Enchantment — Aura", "Enchant creature or Vehicle\nAs long as enchanted permanent is a "
           "Vehicle, it's a creature in addition to its other types.\nEnchanted creature gets +2/+2 and has flying.")
WITNESS = card("Test Witness", "{U}", "Enchantment — Aura", "Enchant creature\nEnchanted creature loses all abilities "
               "and is a green and white Citizen creature with base power and toughness 1/1 named Legitimate "
               "Businessperson.")


def game():
    a, b = Player("a", [ISLAND] * 10, HeuristicAI()), Player("b", [ISLAND] * 10, HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    return g, a, b


def enchant(g, p, aura, host):
    g._aura_host = host
    x = g.enter_battlefield(p, aura)
    g._aura_host = None
    g.settle()
    return x


class Parse(unittest.TestCase):
    def test_full(self):
        for c in (MUTATION, MOD, WITNESS):
            self.assertEqual(c.unsupported, [], c.name)

    def test_refusals(self):
        for text in ("Enchanted creature has indestructible, and it loses all other abilities, card types, and creature "
                     "types.",                                  # nothing names the types it keeps
                     "As long as enchanted permanent is untapped, it's a creature in addition to its other types.",
                     "Creatures you control are Citizens in addition to their other types named Bob."):
            self.assertTrue(card("Test Aura", "{1}", "Enchantment — Aura", "Enchant creature\n" + text).unsupported,
                            text)


class Engine(unittest.TestCase):
    def test_darksteel_mutation(self):
        g, a, b = game()
        d = g.enter_battlefield(b, DRAGON)
        m = enchant(g, a, MUTATION, d)
        self.assertEqual((d.power, d.toughness), (0, 1))
        self.assertEqual((set(d.card.types), set(d.card.subtypes)), ({"Artifact", "Creature"}, {"Insect"}))
        self.assertTrue(d.has("indestructible"))
        self.assertFalse(d.has("flying"))
        g.leave_battlefield(m, "graveyard")
        g.settle()
        self.assertEqual((d.power, set(d.card.subtypes), d.has("flying")), (5, {"Dragon"}, True))

    def test_modification_only_on_vehicles(self):
        g, a, b = game()
        cart = g.enter_battlefield(a, card("Test Cart", "{2}", "Artifact — Vehicle", "Crew 1", 3, 3))
        g.settle()
        self.assertFalse(cart.is_creature)
        m = enchant(g, a, MOD, cart)
        self.assertTrue(cart.is_creature)
        self.assertEqual((cart.power, cart.toughness, cart.has("flying")), (5, 5, True))
        bear = g.enter_battlefield(a, card("Test Bear", "{1}{G}", "Creature — Bear", "", 2, 2))
        enchant(g, a, MOD, bear)
        self.assertEqual(set(bear.card.types), {"Creature"})
        self.assertEqual(bear.power, 4)
        g.leave_battlefield(m, "graveyard")
        g.settle()
        self.assertFalse(cart.is_creature)

    def test_witness_protection_name(self):
        g, a, b = game()
        d = g.enter_battlefield(b, DRAGON)
        w = enchant(g, a, WITNESS, d)
        self.assertEqual(d.card.name, "Legitimate Businessperson")
        self.assertEqual((d.power, d.toughness, d.card.colors), (1, 1, frozenset("GW")))
        self.assertEqual(set(d.card.subtypes), {"Citizen"})
        self.assertFalse(d.has("flying"))
        g.leave_battlefield(w, "graveyard")
        g.settle()
        self.assertEqual(d.card.name, DRAGON.name)


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class Cards(unittest.TestCase):
    def test_real(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Darksteel Mutation", "Aerial Modification", "Siege Modification", "Witness Protection"):
            self.assertEqual(db.get(name).unsupported, [], name)


if __name__ == "__main__":
    unittest.main()

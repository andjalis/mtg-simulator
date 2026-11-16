"""#343 slice: "for each Aura and Equipment attached to ~ / him / her" counts the card's own attachments (Kellan,
Heavenly Blademaster, Valduk, Kemba, Captain America, Shagrat). "attached to it" (a host or an event creature) is
not read here."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.clauses import _xq
from mtgsim.cards.parse import _parse_effects
from mtgsim.cx_attach import attach
from mtgsim.engine import Game, Player, StackItem
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card

SWORD = card("Test Sword", "{1}", "Artifact — Equipment", "Equipped creature gets +1/+0.\nEquip {1}")
AURA = card("Test Aura", "{W}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1.")
LORD = card("Test Lord", "{2}{W}", "Creature — Human Knight", "Other creatures you control get +1/+0 for each Aura and "
            "Equipment attached to ~.", 2, 2)
KEEPER = card("Test Keeper", "{1}{W}", "Legendary Creature — Cat", "At the beginning of your upkeep, create a 2/2 white "
              "Cat creature token for each Equipment attached to ~.", 2, 2)


def game():
    a, b = Player("a", [ISLAND] * 10, HeuristicAI()), Player("b", [ISLAND] * 10, HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    for p in (a, b):
        p.library = [ISLAND] * 20
    return g, a, b


class Parse(unittest.TestCase):
    def test_spec(self):
        self.assertEqual(_xq("the number of Auras and Equipment attached to ~"), ("attached", ("Aura", "Equipment")))
        self.assertEqual(_xq("the number of Equipment attached to him"), ("attached", ("Equipment",)))
        self.assertIsNone(_xq("the number of Equipment attached to it"))
        self.assertEqual(LORD.unsupported, [])
        self.assertEqual(KEEPER.unsupported, [])

    def test_it_is_refused(self):
        _, bad = _parse_effects("Draw a card for each Aura and Equipment attached to it.")
        self.assertTrue(bad)


class Engine(unittest.TestCase):
    def test_static_counts_both_kinds(self):
        g, a, b = game()
        lord = g.enter_battlefield(a, LORD)
        bear = g.enter_battlefield(a, card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2))
        s1, s2 = g.enter_battlefield(a, SWORD), g.enter_battlefield(a, SWORD)
        g.settle()
        self.assertEqual(bear.power, 2)
        attach(g, a, s1, lord)
        attach(g, a, s2, bear)                       # on another creature: not counted
        g._aura_host = lord
        g.enter_battlefield(a, AURA)
        g._aura_host = None
        g.settle()
        self.assertEqual(bear.power, 2 + 1 + 2)      # its own Sword, plus Aura and Sword on the Lord
        self.assertEqual(lord.power, 2 + 1 + 1)      # its own Aura and Sword, not "other"

    def test_trigger_counts_equipment_only(self):
        g, a, b = game()
        keeper = g.enter_battlefield(a, KEEPER)
        for _ in range(2):
            attach(g, a, g.enter_battlefield(a, SWORD), keeper)
        g._aura_host = keeper
        g.enter_battlefield(a, AURA)
        g._aura_host = None
        g.settle()
        trig = keeper.card.triggers[0]
        g.stack.append(StackItem(a, list(trig.effects), [None] * len(trig.effects), source=keeper))
        g.resolve_top()
        g.settle()
        self.assertEqual(sum(x.card.name.startswith("Cat") for x in a.battlefield), 2)


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class Cards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Valduk, Keeper of the Flame", "Kellan, the Fae-Blooded // Birthright Boon", "Heavenly Blademaster",
                     "Captain America, Liberator", "Kemba, Kha Regent", "Shagrat, Loot Bearer"):
            self.assertEqual(db.get(name).unsupported, [], name)
        self.assertTrue(db.get("Wyleth, Soul of Steel").unsupported)       # "attached to it": the attacker


if __name__ == "__main__":
    unittest.main()

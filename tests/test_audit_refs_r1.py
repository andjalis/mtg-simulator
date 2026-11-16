"""Fixes from the opus-refs behaviour audit, round 1 (2026-11-16):
#783 transform DFCs with a land back face, #784 "X plus Y" P/T definitions, #785 "one or more creature cards are put
into your graveyard from anywhere"."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
ELF = card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)
ZOMBIE = card("Test Zombie", "{B}", "Creature — Zombie", "", 1, 1)


def game(ai=HeuristicAI):
    a, b = Player("a", [], ai()), Player("b", [], ai())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library, b.library = [ISLAND] * 20, [ISLAND] * 20
    return g, a, b


def ready(g, p, c, n=1):
    out = []
    for _ in range(n):
        perm = g.enter_battlefield(p, c)
        perm.sick = False
        out.append(perm)
    g.settle()
    return out[0] if n == 1 else out


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Audit(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    # ---- #783
    def test_transform_card_with_a_land_back_is_not_a_modal_land(self):
        for name in ("Search for Azcanta // Azcanta, the Sunken Ruin", "Legion's Landing // Adanto, the First Fort",
                     "Sidequest: Catch a Fish // Cooking Campsite"):
            c = self.db.get(name)
            self.assertIsNotNone(c.back, name)
            self.assertIsNone(getattr(c, "land_face", None), name)
        g, a, b = game()
        a.hand = [self.db.get("Search for Azcanta // Azcanta, the Sunken Ruin")]
        a.ai.main_phase(g, a)
        self.assertEqual(len(a.hand), 1)                    # no mana: not played as its back land

    def test_sidequest_transforms_into_its_land(self):
        g, a, b = game()
        sq = g.enter_battlefield(a, self.db.get("Sidequest: Catch a Fish // Cooking Campsite"))
        g.settle()
        a.library = [ISLAND] * 5 + [BEAR]
        g.step = "upkeep"
        g.fire(a, "upkeep")
        g.settle()
        self.assertEqual(sq.card.name, "Cooking Campsite")
        self.assertTrue(sq.card.is_land)
        self.assertIn(BEAR, a.hand)

    def test_legions_landing_transforms_on_a_three_creature_attack(self):
        for n, flips in ((3, True), (2, False)):
            g, a, b = game(Scripted)
            ll = g.enter_battlefield(a, self.db.get("Legion's Landing // Adanto, the First Fort"))
            g.settle()
            a.ai.attack = [ready(g, a, BEAR) for _ in range(n)]
            b.ai.block = {}
            g.combat(a, b)
            g.settle()
            self.assertEqual(ll.card.is_land, flips, n)

    # ---- #784
    def test_x_plus_y_power_and_toughness(self):
        g, a, b = game()
        ready(g, a, ELF, 2)
        ready(g, b, ELF)
        a.graveyard = [ELF, BEAR]
        ab = g.enter_battlefield(a, self.db.get("Abomination of Llanowar"))
        g.settle()
        self.assertIn(ab, a.battlefield)
        self.assertEqual((ab.power, ab.toughness), (4, 4))     # 3 Elves I control (itself too) + 1 Elf card
        g, a, b = game()
        ready(g, a, ZOMBIE, 2)
        ready(g, b, ZOMBIE)
        a.graveyard, b.graveyard = [ZOMBIE], [ZOMBIE]
        so = g.enter_battlefield(a, self.db.get("Soulless One"))
        g.settle()
        self.assertEqual((so.power, so.toughness), (6, 6))     # 4 Zombies on the battlefield + 2 in all graveyards

    def test_domain_power_and_toughness(self):
        g, a, b = game()
        for land in ("Mountain", "Forest", "Plains"):
            ready(g, a, self.db.get(land))
        kavu = g.enter_battlefield(a, self.db.get("Territorial Kavu"))
        g.settle()
        self.assertEqual((kavu.power, kavu.toughness), (3, 3))   # was a garbled count: 0/0, died

    def test_cda_never_stores_a_garbled_count(self):
        for name in ("Abomination of Llanowar", "Dauntless Dourbark", "Soulless One", "Knight of the Widget",
                     "Territorial Kavu", "Matca Rioters", "Opulent Clomper"):
            self.assertFalse(any(w in self.db.get(name).pt_cda for w in (" plu ", " among ", " control")), name)

    # ---- #785
    def test_creature_cards_to_your_graveyard_is_not_any_creature_dying(self):
        g, a, b = game()
        g.enter_battlefield(a, self.db.get("Sefris of the Hidden Ways"))
        g.settle()
        g.destroy(ready(g, b, BEAR))
        g.settle()
        self.assertFalse([e for e in g.events if "Dungeon" in e])      # the opponent's creature: not my graveyard
        g.destroy(ready(g, a, BEAR))
        g.settle()
        self.assertEqual(len([e for e in g.events if e.endswith("enters Dungeon of the Mad Mage")]), 1)
        g.destroy(ready(g, a, BEAR))
        g.settle()
        self.assertEqual(len([e for e in g.events if e.endswith("enters Dungeon of the Mad Mage")]), 1)   # once a turn

    def test_that_many_on_a_batch_is_refused(self):
        from mtgsim.coverage import card_coverage
        brood = self.db.get("Voracious Brood")
        self.assertEqual(card_coverage(brood).status, "partial")
        self.assertTrue(any("that many" in u for u in brood.unsupported))


if __name__ == "__main__":
    unittest.main()

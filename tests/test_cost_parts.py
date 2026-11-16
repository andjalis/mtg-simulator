"""Activated-ability cost forms (#859): or-pair and token-subtype sacrifices, larger / "other" tap counts,
"{3}, {T} or {U}, {T}" split costs, and "Remove all <kind> counters from ~" with the amount removed."""
import dataclasses
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.coverage import card_coverage
from mtgsim.engine import Game, Player
from tests.test_templates import card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

NOW_FULL = ["Elite Headhunter", "Mold Folk", "Skophos Warleader", "Skullport Merchant", "Ice Cream Kitty",
            "Malevolent Noble", "Slaughter-Priest of Mogis", "Lathril, Blade of the Elves", "Saradoc, Master of Buckland",
            "Voyager Glidecar", "Falkenrath Forebear", "Restless Bloodseeker // Bloodsoaked Reveler",
            "Deathless Behemoth", "Crystal Shard", "Granite Shard", "Heartwood Shard", "Pearl Shard", "Skeleton Shard",
            "Geometric Nexus", "Relic Amulet", "Vish Kal, Blood Arbiter", "Geistflame Reservoir"]


def ability_text(c):
    return [a.text for a in c.activated]


class Refusals(unittest.TestCase):
    def check_ignored(self, line, types="Artifact"):
        c = card("Zork", "{2}", types, line)
        self.assertIn(line, c.unsupported, line)

    def test_near_misses_stay_ignored(self):
        for line in ("{1}, Sacrifice another creature or another artifact: Draw a card.",
                     "{1}, Sacrifice a creature or a widget: Draw a card.",
                     "{1}, Sacrifice two Widget tokens: Draw a card.",
                     "{1}, Sacrifice a Blood token or a Clue: Draw a card.",
                     "Tap two other untapped florbs you control: Draw a card.",
                     "{T}, Remove all charge counters from ~: You gain 2 life for each charge counter removed this way.",
                     "{3}, {T} or {U}, {T}: Gronk the blurf."):
            self.check_ignored(line)

    def test_or_cost_makes_two_abilities(self):
        c = card("Zork", "{2}", "Artifact", "{3}, {T} or {U}, {T}: Draw a card.")
        self.assertEqual(c.unsupported, [])
        self.assertEqual([(a.cost, a.extra_costs.get("tap")) for a in c.activated],
                         [({"generic": 3}, True), ({"generic": 0, "U": 1}, True)])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    @classmethod
    def tearDownClass(cls):
        cls.db._all.close()

    def test_cards_now_full(self):
        for name in NOW_FULL:
            self.assertEqual(card_coverage(self.db.get(name)).ignored, [], name)

    def test_costs(self):
        get = lambda n: self.db.get(n).activated[-1].extra_costs        # noqa: E731
        self.assertEqual(get("Elite Headhunter")["sacrifice"], "other creature or artifact")
        self.assertEqual(get("Malevolent Noble")["sacrifice"], "other artifact or creature")
        self.assertEqual(get("Lathril, Blade of the Elves")["cx_costs"], (("tap", 10, {"sub": ["Elf"]}),))
        self.assertEqual(get("Saradoc, Master of Buckland")["cx_costs"], (("tap", 2, {"sub": ["Halfling"], "other": True}),))
        self.assertEqual(get("Restless Bloodseeker // Bloodsoaked Reveler")["cx_costs"], (("sac_sub", 2, {"sub": "Blood"}),))
        self.assertEqual(get("Relic Amulet")["remove_counter_count"], "x")


def token(name, types, subs):
    pt = (1, 1) if types == "Creature" else (None, None)
    return dataclasses.replace(card(name, "", types + " — " + subs, "", *pt), is_token=True)


BLOOD = token("Blood", "Artifact", "Blood")


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Games(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g, self.a, self.b = Game(a, b, random.Random(0), log=True), a, b
        self.g.turn, self.g.step = 3, "main1"
        island = self.db.get("Island")
        a.library, b.library = [island] * 20, [island] * 20

    def put(self, p, c, n=1):
        if isinstance(c, str):
            c = self.db.get(c)
        out = [self.g.enter_battlefield(p, c) for _ in range(n)]
        for x in out:
            x.sick = False
        self.g.settle()
        return out[0]

    def names(self, p):
        return sorted(x.card.name for x in p.battlefield)

    def test_headhunter_sacrifices_an_artifact_not_itself(self):
        g, a, b = self.g, self.a, self.b
        self.put(a, "Swamp", 4)
        hunter = self.put(a, "Elite Headhunter")
        self.put(a, BLOOD)
        bear = self.put(b, "Grizzly Bears")
        idx = len(hunter.activated) - 1
        self.assertTrue(g.activate_ability(a, hunter, idx, [bear]))
        g.settle()
        self.assertNotIn("Blood", self.names(a))
        self.assertIn("Elite Headhunter", self.names(a))
        self.assertEqual(self.names(b), [])

    def test_headhunter_alone_cannot_pay(self):
        g, a, b = self.g, self.a, self.b
        self.put(a, "Swamp", 4)
        hunter = self.put(a, "Elite Headhunter")
        self.put(b, "Grizzly Bears")
        self.assertFalse(g.can_activate(a, hunter, len(hunter.activated) - 1))

    def test_skullport_merchant_sacrifices_its_treasure(self):
        from mtgsim.engine.policy import ability_worth
        g, a = self.g, self.a
        self.put(a, "Swamp", 2)
        merchant = self.put(a, "Skullport Merchant")         # its enters trigger makes a Treasure
        idx = len(merchant.activated) - 1
        self.assertTrue(ability_worth(g, a, merchant, idx))   # the AI would pay with the Treasure
        hand = len(a.hand)
        self.assertTrue(g.activate_ability(a, merchant, idx))
        g.settle()
        self.assertEqual(self.names(a), ["Skullport Merchant", "Swamp", "Swamp"])
        self.assertEqual(len(a.hand), hand + 1)

    def test_lathril_taps_ten_elves(self):
        g, a, b = self.g, self.a, self.b
        lathril = self.put(a, "Lathril, Blade of the Elves")
        elf = token("Elf Warrior", "Creature", "Elf Warrior")
        self.put(a, elf, 9)
        idx = len(lathril.activated) - 1
        self.assertFalse(g.can_activate(a, lathril, idx))   # Lathril taps itself for {T}: it isn't one of the ten
        self.put(a, elf)
        self.assertTrue(g.activate_ability(a, lathril, idx))
        g.settle()
        self.assertEqual((a.life, b.life), (30, 10))

    def test_saradoc_taps_two_other_halflings(self):
        g, a = self.g, self.a
        saradoc = self.put(a, "Saradoc, Master of Buckland")        # his enters trigger makes one Halfling
        hobbit = token("Halfling", "Creature", "Halfling")
        idx = len(saradoc.activated) - 1
        self.assertFalse(g.can_activate(a, saradoc, idx))    # he is a Halfling, but not an "other" one
        self.put(a, hobbit)
        self.assertTrue(g.activate_ability(a, saradoc, idx))
        g.settle()
        self.assertFalse(saradoc.tapped)
        self.assertTrue(saradoc.has("lifelink"))

    def test_falkenrath_forebear_returns_for_two_blood_tokens(self):
        g, a = self.g, self.a
        from mtgsim import graveyard
        self.put(a, "Swamp")
        self.put(a, BLOOD, 2)
        forebear = self.db.get("Falkenrath Forebear")
        a.graveyard.append(forebear)
        self.assertTrue(graveyard.activate(g, a, forebear, 0))
        g.settle()
        self.assertEqual(self.names(a), ["Falkenrath Forebear", "Swamp"])

    def test_crystal_shard_pays_with_blue(self):
        g, a, b = self.g, self.a, self.b
        self.put(a, "Island")
        shard = self.put(a, "Crystal Shard")
        self.put(b, "Grizzly Bears")
        self.assertFalse(g.can_activate(a, shard, 0))        # {3}, {T}: three mana missing
        self.assertTrue(g.activate_ability(a, shard, 1))
        g.settle()
        self.assertIn("Grizzly Bears", [c.name for c in b.hand])

    def test_relic_amulet_removes_all_charge_counters(self):
        g, a, b = self.g, self.a, self.b
        self.put(a, "Island", 2)
        amulet = self.put(a, "Relic Amulet")
        amulet.counters["charge"] = 3
        giant = self.put(b, "Hill Giant")
        self.assertTrue(g.activate_ability(a, amulet, len(amulet.activated) - 1, [giant]))
        g.settle()
        self.assertEqual(amulet.counters.get("charge", 0), 0)
        self.assertEqual(self.names(b), [])

    def test_vish_kal_shrinks_by_the_counters_removed(self):
        g, a, b = self.g, self.a, self.b
        vish = self.put(a, "Vish Kal, Blood Arbiter")
        vish.counters["+1/+1"] = 2
        giant = self.put(b, "Hill Giant")
        idx = next(i for i, x in enumerate(vish.activated) if x.extra_costs.get("remove_counter") == "+1/+1")
        self.assertTrue(g.activate_ability(a, vish, idx, [giant]))
        g.settle()
        self.assertEqual(vish.counters.get("+1/+1", 0), 0)
        self.assertEqual((giant.power, giant.toughness), (1, 1))


if __name__ == "__main__":
    unittest.main()

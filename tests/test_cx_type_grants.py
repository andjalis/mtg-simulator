"""Creature types added by static abilities (layer 4): host and group grants and when they change."""
import dataclasses
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")
HAT = card("Test Hat", "{1}", "Artifact — Equipment",
           "Equipped creature gets +1/+1 and is a Wizard in addition to its other types.\nEquip {1}")
LORD = card("Test Lord", "{2}", "Creature — Human Wizard", "Other Wizards you control get +1/+1.", power=1, toughness=1)
EARL = card("Test Earl", "{3}", "Creature — Squirrel",
            "Creature tokens you control are Squirrels in addition to their other creature types.", power=2, toughness=2)
TOKEN = dataclasses.replace(card("Test Soldier", "", "Token Creature — Soldier", "", power=1, toughness=1), is_token=True)


class Parsing(unittest.TestCase):
    def test_shapes(self):
        demon = card("Test Demon", "{2}{B}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +2/+2, has "
                     "flying, and is a Demon in addition to its other types.")
        knife = card("Test Knife", "{1}", "Artifact — Equipment", "Equipped creature gets +1/+1, has \"Whenever this "
                     "creature deals combat damage to a player, draw a card,\" and is a Rogue in addition to its other "
                     "types.\nEquip {2}")
        for c, subs in ((HAT, ("Wizard",)), (demon, ("Demon",)), (knife, ("Rogue",)), (EARL, ("Squirrel",))):
            with self.subTest(c.name):
                self.assertEqual((c.unsupported, c.approximations), ([], []))
                self.assertEqual(c.advanced_rules["type_grants"][0][1], subs)
        self.assertEqual((demon.equip_bonus, demon.equip_keywords), ((2, 2), frozenset({"flying"})))
        self.assertEqual(len(knife.trigger_grants), 1)

    def test_refusals(self):
        for text, types in (
                ("Equipped creature is an artifact in addition to its other types.\nEquip {1}", "Artifact — Equipment"),
                ("Lands you control are Swamps in addition to their other types.", "Enchantment"),     # land types
                ("Eldrazi you control are Slivers in addition to their other types.", "Enchantment"),  # reads types
                ("Equipped creature gets +1/+1 and frobs, and is a Wizard in addition to its other types.\nEquip {1}",
                 "Artifact — Equipment")):
            with self.subTest(text):
                self.assertTrue(card("Test Refusal", "{1}", types, text).unsupported)

    @unittest.skipUnless(os.path.exists(DB), "card database not built")
    def test_real_cards_are_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Inner Demon", "Thief's Knife", "Black Mage's Rod", "Sigiled Sword of Valeron", "Monk's Fist",
                     "Hivestone", "Mephidross Vampire", "Dismiss into Dream"):
            with self.subTest(name):
                self.assertEqual(card_coverage(db.get(name)).status, "full")


class Behaviour(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_host_grant_follows_the_equipment_and_feeds_a_lord(self):
        x, y = self.game.enter_battlefield(self.a, BEAR), self.game.enter_battlefield(self.a, BEAR)
        hat = self.game.enter_battlefield(self.a, HAT)
        self.game.enter_battlefield(self.a, LORD)
        hat.attached_to = x
        self.assertEqual((x.card.subtypes, x.power), (frozenset({"Bear", "Wizard"}), 4))     # +1 Hat, +1 Lord
        hat.attached_to = y
        self.assertEqual((x.card.subtypes, x.power, y.power), (frozenset({"Bear"}), 2, 4))
        self.game.leave_battlefield(hat, "graveyard")
        self.assertEqual((y.card.subtypes, y.power), (frozenset({"Bear"}), 2))

    def test_aura_grant_and_last_known_types(self):
        demon = card("Test Demon", "{2}{B}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +2/+2, has "
                     "flying, and is a Demon in addition to its other types.")
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game._aura_host = bear
        self.game.enter_battlefield(self.a, demon)
        self.game.settle()
        self.assertIn("Demon", bear.card.subtypes)
        self.game.destroy(bear)
        self.game.settle()
        self.assertIn("Demon", bear.card.subtypes)       # it died a Demon (last known information)

    def test_group_grant_membership(self):
        before = self.game.enter_battlefield(self.a, TOKEN)
        earl = self.game.enter_battlefield(self.a, EARL)
        after, theirs = self.game.enter_battlefield(self.a, TOKEN), self.game.enter_battlefield(self.b, TOKEN)
        nontoken = self.game.enter_battlefield(self.a, BEAR)
        self.assertEqual([("Squirrel" in x.card.subtypes) for x in (before, after, theirs, nontoken)],
                         [True, True, False, False])
        from mtgsim.counter_mechanics import add_control
        add_control(self.game, after, self.b, source=None)        # stolen: no longer "you control"
        self.assertNotIn("Squirrel", after.card.subtypes)
        self.game.leave_battlefield(earl, "graveyard")
        self.assertNotIn("Squirrel", before.card.subtypes)

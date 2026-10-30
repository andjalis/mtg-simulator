"""Venture into the dungeon and the initiative: parsing and engine behavior (chonk/vert)."""
import random
import unittest

from mtgsim import dungeon_mechanics
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

NADAAR = card("Nadaar, Selfless Paladin", "{2}{W}", "Legendary Creature — Dragon Knight",
              "Vigilance\nWhenever Nadaar enters or attacks, venture into the dungeon.", 2, 2)
WHITE_PLUME = card("White Plume Adventurer", "{2}{W}", "Creature — Orc Cleric",
                   "When this creature enters, you take the initiative.", 3, 2)
LOOT_DISPUTE = card("Loot Dispute", "{3}{R}", "Enchantment",
                    "When this enchantment enters, you take the initiative and create a Treasure token.\n"
                    "Whenever you complete a dungeon, create a 5/5 red Dragon creature token with flying.")
DUNGEON_MAP = card("Dungeon Map", "{3}", "Artifact",
                   "{3}, {T}: Venture into the dungeon. Activate only as a sorcery.")
PACK_TACTICS = card("Intrepid Outlander", "{1}{G}", "Creature — Orc Ranger",
                    "Reach\nPack tactics — Whenever this creature attacks, if you attacked with "
                    "creatures with total power 6 or greater this combat, venture into the dungeon.", 2, 3)
SEFRIS = card("Sefris of the Hidden Ways", "{W}{U}{B}", "Legendary Creature — Human Wizard",
              "Whenever one or more creature cards are put into your graveyard from anywhere, "
              "venture into the dungeon.\nWhenever you complete a dungeon, return target creature "
              "card from your graveyard to the battlefield.", 2, 3)


class ParseDungeon(unittest.TestCase):
    def test_venture_etb_and_attack_triggers(self):
        c = card("Test Paladin", "{2}{W}", "Creature", "Vigilance\n"
                 "Whenever Test Paladin enters or attacks, venture into the dungeon.", 2, 2)
        self.assertEqual([t.event for t in c.triggers], ["etb", "attacks"])
        self.assertEqual([e.kind for e in c.triggers[0].effects], ["venture"])

    def test_initiative_effect(self):
        c = card("Test Adventurer", "{2}{W}", "Creature",
                 "When this creature enters, you take the initiative.", 3, 2)
        self.assertEqual([e.kind for e in c.triggers[0].effects], ["take_initiative"])

    def test_initiative_with_rider(self):
        c = card("Test Dispute", "{3}{R}", "Enchantment",
                 "When this enchantment enters, you take the initiative and create a Treasure token.")
        self.assertEqual([e.kind for e in c.triggers[0].effects], ["take_initiative", "token"])

    def test_complete_dungeon_trigger(self):
        self.assertEqual([t.event for t in SEFRIS.triggers], ["creature_dies", "complete_dungeon"])
        self.assertEqual([e.kind for e in SEFRIS.triggers[1].effects], ["reanimate_one"])
        self.assertEqual([t.event for t in LOOT_DISPUTE.triggers], ["etb", "complete_dungeon"])

    def test_venture_activated_ability(self):
        act = DUNGEON_MAP.activated[0]
        self.assertEqual([e.kind for e in act.effects], ["venture"])

    def test_pack_tactics(self):
        self.assertEqual([(t.event, [e.kind for e in t.effects]) for t in PACK_TACTICS.triggers],
                         [("attacks", ["venture"])])

    def test_dungeon_reminder_lines_are_gone(self):
        c = card("Test Venture", "{1}{W}", "Sorcery",
                 "Venture into the dungeon. (Enter the first room or advance to the next room.)")
        self.assertEqual([e.kind for e in c.spell_effects], ["venture"])
        self.assertEqual(c.unsupported, [])

    def test_cant_venture_limiter_stays_partial(self):
        c = card("Test Sentry", "{1}{W}", "Creature",
                 "Each opponent can't venture into the dungeon more than once each turn.")
        self.assertTrue(c.unsupported)


class DungeonEngine(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(3))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def put(self, definition, p=None):
        perm = self.g.enter_battlefield(p or self.a, definition)
        perm.sick = False
        self.g.settle()
        return perm

    def apply(self, text, targets=()):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        targets = list(targets) + [None] * (len(effects) - len(targets))
        item = StackItem(self.a, effects, targets)
        prev = None
        for eff, target in zip(effects, targets):
            self.g.resolve(self.a, eff, target, item, prev=prev)
            prev = target

    def state(self, p=None):
        return dungeon_mechanics._state(self.g, p or self.a)

    def test_first_venture_enters_the_best_dungeon(self):
        # the AI picks the dungeon with the best average room value
        self.apply("Venture into the dungeon.")
        st = self.state()
        self.assertEqual(st["dungeon"], "Dungeon of the Mad Mage")
        self.assertEqual(st["room"], "Yawning Portal")
        self.assertEqual(self.a.life, 20 + 1)             # Yawning Portal: you gain 1 life

    def test_ventures_advance_and_complete(self):
        for _ in range(7):                     # Dungeon of the Mad Mage's best path has 7 rooms
            self.apply("Venture into the dungeon.")
        st = self.state()
        self.assertIsNone(st["room"])
        self.assertIn("Dungeon of the Mad Mage", st["completed"])

    def test_tomb_rooms_drain_both_players(self):
        st = self.state()
        st["dungeon"], st["room"] = "Tomb of Annihilation", "Trapped Entry"
        self.apply("Venture into the dungeon.")            # Veils of Fear: each player loses 2
        self.assertEqual(self.a.life, 18)
        self.assertEqual(self.b.life, 18)

    def test_initiative_ventures_and_sets_flag(self):
        self.apply("You take the initiative.")
        self.assertIs(self.g.initiative, self.a)
        self.assertEqual(self.state()["room"], "Yawning Portal")

    def test_initiative_upkeep_hook_ventures(self):
        dungeon_mechanics.take_initiative(self.g, self.a)
        room = self.state()["room"]
        dungeon_mechanics.initiative_upkeep(self.g, self.a)
        self.assertNotEqual(self.state()["room"], room)
        self.assertIsNone(dungeon_mechanics.initiative_upkeep(self.g, self.b))  # only the holder

    def test_initiative_combat_hook_passes_it(self):
        dungeon_mechanics.take_initiative(self.g, self.a)
        bear = self.put(BEAR, self.b)                    # b's creature damages a, who holds it
        dungeon_mechanics.initiative_combat(self.g, bear, self.a)
        self.assertIs(self.g.initiative, self.b)

    def test_complete_dungeon_trigger_fires(self):
        dispute = self.put(LOOT_DISPUTE)                   # etb: initiative + Treasure
        self.assertEqual(self.g.initiative, self.a)
        st = self.state()
        st["dungeon"], st["room"] = "Lost Mine of Phandelver", "Dark Pool"
        self.apply("Venture into the dungeon.")           # Temple of Dumathoin: draw + complete
        self.g.settle()
        self.assertIn("Lost Mine of Phandelver", st["completed"])
        dragons = [x for x in self.a.battlefield if "Dragon" in x.card.subtypes]
        self.assertEqual(len(dragons), 1)

    def test_venture_from_etb_trigger(self):
        self.put(NADAAR)
        self.assertEqual(self.state()["room"], "Yawning Portal")

    def test_initiative_from_etb(self):
        self.put(WHITE_PLUME)
        self.assertIs(self.g.initiative, self.a)

    def test_sefris_ventures_on_creature_death(self):
        sefris = self.put(SEFRIS)
        bear = self.put(BEAR)               # a's own creature card hits a's graveyard
        self.g.sacrifice(bear)
        self.g.settle()
        self.assertEqual(self.state()["room"], "Yawning Portal")
        self.assertIs(sefris.controller, self.a)

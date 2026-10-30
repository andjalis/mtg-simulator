"""Manifest: templates and engine behavior (chonk/vert batch 2)."""
import random
import unittest

from mtgsim import manifest as manifest_mod
from mtgsim.cards import Effect
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

import json
import sqlite3

DB = sqlite3.connect("mtgsim/data/cards.sqlite3")
RAW = {k: json.loads(d) for k, d in DB.execute("select key, data from cards")}


def real(name):
    from mtgsim import cards
    return cards.card_from_scryfall(RAW[name.lower()])


SOUL_SUMMONS = card("Test Summons", "{1}{W}", "Sorcery", "Manifest the top card of your library.")
EMISSARY = card("Test Emissary", "{1}{B}", "Creature — Zombie Warrior",
                "When this creature dies, manifest the top card of your library.", 1, 1)
INVOCATION = card("Test Invocation", "{4}{R}", "Sorcery",
                  "Manifest the top card of your library, then put two +1/+1 counters on it.")
PIPES = real("They Came from the Pipes")          # manifest dread twice
ANGEL = card("Test Angel", "{3}{W}{W}", "Creature — Angel", "Flying", 4, 4)
WITNESS = card("Test Witness", "{1}{W}", "Creature — Human", "When ~ enters, draw a card.", 1, 1)
SNEAKY = card("Test Sneaky", "{1}{B}", "Sorcery", "")   # a noncreature to manifest face down


class ParseManifest(unittest.TestCase):
    def test_manifest_top_card(self):
        self.assertEqual([(e.kind, e.amount) for e in SOUL_SUMMONS.spell_effects], [("manifest", 1)])
        self.assertEqual(SOUL_SUMMONS.unsupported, [])

    def test_manifest_dies_trigger(self):
        self.assertEqual([(t.event, t.effects[0].kind) for t in EMISSARY.triggers],
                         [("dies", "manifest")])

    def test_manifest_with_counters_rider(self):
        self.assertEqual([(e.kind, e.data.get("counters")) for e in INVOCATION.spell_effects],
                         [("manifest", ("+1/+1", 2))])

    def test_manifest_dread_twice(self):
        etb = next(t for t in PIPES.triggers if t.event == "etb")
        self.assertEqual([e.kind for e in etb.effects], ["manifest_dread_more"])

    def test_real_cards_promoted(self):
        for name in ("Soul Summons", "Sultai Emissary", "Innocuous Rat", "Fierce Invocation",
                     "Qarsi High Priest", "Sash and Waistcoat, Unmen", "Write into Being",
                     "Soul-Strike Technique", "Cryptic Pursuit", "Omarthis, Ghostfire Initiate"):
            c = real(name)
            self.assertFalse([u for u in c.unsupported if "anifest" in u], (name, c.unsupported))


class ManifestEngine(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(3))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def apply(self, effects, targets=(), source=None):
        targets = list(targets) + [None] * (len(effects) - len(targets))
        item = StackItem(self.a, effects, targets, source=source)
        for eff, target in zip(effects, targets):
            self.g.resolve(self.a, eff, target, item)

    def manifest(self, top):
        self.a.library.append(top)          # the list end is the top of the library
        perm = manifest_mod.manifest_one(self.g, self.a)
        self.g.settle()
        return perm

    def test_manifest_enters_face_down(self):
        perm = self.manifest(ANGEL)
        self.assertIn(perm, self.a.battlefield)
        self.assertEqual(perm.card.name, "Face-down creature")
        self.assertEqual((perm.power, perm.toughness), (2, 2))
        self.assertIs(perm.hidden.name, ANGEL.name)
        self.assertNotIn(ANGEL, self.a.library)

    def test_manifest_hides_the_real_abilities(self):
        perm = self.manifest(WITNESS)       # "when ~ enters, draw a card" must not fire
        self.assertEqual(len(self.a.hand), 0)
        self.assertEqual(perm.card.name, "Face-down creature")

    def test_creature_turns_face_up_for_its_cost(self):
        for _ in range(6):
            self.g.enter_battlefield(self.a, ISLAND)
        self.g.settle()
        perm = self.manifest(ANGEL)         # {3}{W}{W}: six Islands can't pay it
        self.g.turn_face_up(self.a)
        self.assertEqual(perm.card.name, "Face-down creature")
        for _ in range(3):
            self.g.enter_battlefield(self.a, card("Test Plains", types="Basic Land — Plains",
                                                  text="({T}: Add {W}.)"))
        self.g.settle()
        self.g.turn_face_up(self.a)
        self.assertEqual(perm.card.name, ANGEL.name)
        self.assertIsNone(perm.hidden)
        self.assertTrue(perm.has("flying"))

    def test_noncreature_stays_face_down(self):
        SNEAKY = card("Test Trick", "{2}{U}", "Instant", "~ deals 1 damage to any target.")
        perm = self.manifest(SNEAKY)
        for _ in range(9):
            self.g.enter_battlefield(self.a, ISLAND)
        self.g.settle()
        self.g.turn_face_up(self.a)
        self.assertEqual(perm.card.name, "Face-down creature")   # never turns up

    def test_manifest_effect_from_a_spell(self):
        self.a.library.append(ANGEL)
        self.apply([Effect("manifest", 1)])
        self.g.settle()
        self.assertEqual([x.card.name for x in self.a.battlefield], ["Face-down creature"])

    def test_manifest_counters_rider(self):
        perm = None
        self.a.library.append(ANGEL)
        self.apply([Effect("manifest", 1, data={"counters": ("+1/+1", 2)})])
        self.g.settle()
        perm = next(x for x in self.a.battlefield if x.card.name == "Face-down creature")
        self.assertEqual((perm.power, perm.toughness), (4, 4))    # the 2/2 grows into 4/4

    def test_manifest_dread_twice(self):
        top = [ANGEL, WITNESS, BEAR, card("Test Trick2", "{2}{U}", "Instant", ""), ISLAND, ISLAND]
        self.a.library += top
        self.apply([Effect("manifest_dread_more", 2)])
        self.g.settle()
        downs = [x for x in self.a.battlefield if x.card.name == "Face-down creature"]
        self.assertEqual(len(downs), 2)                     # two manifested
        self.assertEqual(len(self.a.graveyard), 2)          # two milled
        self.assertEqual(len(self.a.library), 20 + 6 - 4)

    def test_dies_trigger_manifests(self):
        emissary = self.g.enter_battlefield(self.a, EMISSARY)
        emissary.sick = False
        self.g.settle()
        self.a.library.append(ANGEL)
        self.g.sacrifice(emissary)
        self.g.settle()
        self.assertEqual([x.card.name for x in self.a.battlefield], ["Face-down creature"])

    def test_omarthis_manifests_for_its_counters(self):
        omarthis = real("Omarthis, Ghostfire Initiate")
        perm = self.g.enter_battlefield(self.a, omarthis, x=3)   # X +1/+1 counters: it survives
        self.a.library += [ANGEL, WITNESS, BEAR]
        self.apply([Effect("manifest", data={"counters_of_source": True})], source=perm)
        self.g.settle()
        downs = [x for x in self.a.battlefield if x.card.name == "Face-down creature"]
        self.assertEqual(len(downs), 3)


if __name__ == "__main__":
    unittest.main()

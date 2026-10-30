"""Manifest dread adoption, batch 3: the X-times single-dread wording rides my kind.

The bare "Manifest dread." still parses to the foundation kind (engine/kinds/permanents.py,
joined from cards/patterns.py — neither file is this module's); the wordings the
foundation's single-effect pattern can't express go through manifest_dread_more, which
delegates to manifest.manifest_dread here: creatures preferred, real card hidden under
the face-down body (it can turn face up), X repeats and "+1/+1 counters on each of those
creatures" applied.
"""
import json
import random
import sqlite3
import unittest

from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

DB = sqlite3.connect("mtgsim/data/cards.sqlite3")
RAW = {k: json.loads(d) for k, d in DB.execute("select key, data from cards")}


def real(name):
    from mtgsim import cards
    return cards.card_from_scryfall(RAW[name.lower()])


ONSLAUGHT = real("Valgavoth's Onslaught")
PIPING = real("They Came from the Pipes")            # "manifest dread twice" -> my kind


class ParseManifestBatch3(unittest.TestCase):
    def test_onslaught_x_times_rides_my_kind(self):
        self.assertEqual(ONSLAUGHT.unsupported, [])
        eff = ONSLAUGHT.spell_effects[0]
        self.assertEqual((eff.kind, eff.data["times"], eff.data["counters"]),
                         ("manifest_dread_more", "x", ("+1/+1", "x")))

    def test_double_dread_still_rides_my_kind(self):
        self.assertEqual(PIPING.unsupported, [])
        eff = PIPING.triggers[0].effects[0]
        self.assertEqual((eff.kind, eff.amount), ("manifest_dread_more", 2))


class ManifestEngineBatch3(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(3))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def test_onslaught_manifests_x_times_with_counters(self):
        # creatures on top get manifested (creatures preferred), the others milled
        self.a.library = [card(f"Beast {i}", f"{{{i}}}", "Creature — Beast", "", 2 + i, 2)
                          for i in range(1, 5)] + [ISLAND] * 6
        eff = ONSLAUGHT.spell_effects[0]
        item = StackItem(self.a, [eff], [])
        item.x = 2
        self.g.resolve(self.a, eff, None, item)
        self.g.settle()
        face_down = [x for x in self.a.battlefield if x.card.name == "Face-down creature"]
        self.assertEqual(len(face_down), 2)
        self.assertEqual([x.counters.get("+1/+1") for x in face_down], [2, 2])
        self.assertEqual(len(self.a.graveyard), 2)      # one milled card per dread

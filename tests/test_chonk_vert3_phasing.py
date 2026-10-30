"""Phasing residuals, batch 3: Mirage upkeep statics, the "unless you pay" choice,
Teferi's Veil's end-of-combat timing and Spectral Adversary's pay-N-times entry."""
import json
import random
import sqlite3
import unittest

from mtgsim import phasing
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

DB = sqlite3.connect("mtgsim/data/cards.sqlite3")
RAW = {k: json.loads(d) for k, d in DB.execute("select key, data from cards")}


def real(name):
    from mtgsim import cards
    return cards.card_from_scryfall(RAW[name.lower()])


ADVERSARY = real("Spectral Adversary")
EQUIPOISE = real("Equipoise")
REALM = real("Teferi's Realm")
DJINN = real("Vaporous Djinn")
VEIL = real("Teferi's Veil")


class ParsePhasingBatch3(unittest.TestCase):
    def test_spectral_adversary_promoted(self):
        self.assertEqual(ADVERSARY.unsupported, [])
        trig = ADVERSARY.triggers[0]
        self.assertEqual(trig.event, "etb")
        self.assertEqual([e.kind for e in trig.effects], ["pay_repeat", "phase_out_paid"])

    def test_equipoise_promoted(self):
        self.assertEqual(EQUIPOISE.unsupported, [])
        self.assertEqual(EQUIPOISE.triggers[0].event, "upkeep")
        self.assertEqual([e.kind for e in EQUIPOISE.triggers[0].effects],
                         ["phase_out_excess"] * 3)
        self.assertEqual([e.data["type"] for e in EQUIPOISE.triggers[0].effects],
                         ["land", "Artifact", "Creature"])

    def test_tefeis_realm_promoted(self):
        self.assertEqual(REALM.unsupported, [])
        self.assertEqual(REALM.triggers[0].event, "each_upkeep")
        self.assertEqual([e.kind for e in REALM.triggers[0].effects], ["phase_out_realm"])

    def test_unless_you_pay_carries_the_cost(self):
        self.assertEqual(DJINN.unsupported, [])
        upkeep = next(t for t in DJINN.triggers if t.event == "upkeep")
        eff = upkeep.effects[0]
        self.assertEqual((eff.kind, eff.target), ("phase_out", "self"))
        self.assertEqual(eff.data["unless"], {"generic": 0, "U": 2})

    def test_veil_queues_at_end_of_combat(self):
        attacks = next(t for t in VEIL.triggers if t.event == "creature_attacks")
        self.assertEqual([(e.kind, e.data["effects"][0].target) for e in attacks.effects],
                         [("end_of_combat", "prev")])   # the shared end-of-combat delay


class PhasingEngineBatch3(unittest.TestCase):
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

    def resolve(self, effects, source, targets=(), context=None):
        targets = list(targets) + [None] * (len(effects) - len(targets))
        item = StackItem(self.a, effects, targets, source=source, context=context)
        for eff, tgt in zip(effects, targets):
            self.g.resolve(self.a, eff, tgt, item)
        self.g.settle()
        return item

    def phased(self):
        return phasing.phased_out(self.g)

    def test_unless_you_pay_pays_when_able(self):
        djinn = self.put(DJINN)
        for _ in range(4):
            self.g.enter_battlefield(self.a, ISLAND)          # untapped Islands: {U}{U}
        upkeep = next(t for t in DJINN.triggers if t.event == "upkeep")
        self.resolve(upkeep.effects, djinn)
        self.assertIn(djinn, self.a.battlefield)               # paid, so it stays
        self.assertEqual(self.phased(), [])

    def test_unless_you_pay_phases_out_broke(self):
        djinn = self.put(DJINN)                                 # no Islands this time
        upkeep = next(t for t in DJINN.triggers if t.event == "upkeep")
        self.resolve(upkeep.effects, djinn)
        self.assertNotIn(djinn, self.a.battlefield)
        self.assertIn(djinn, self.phased())

    def test_veil_phases_out_at_end_of_combat(self):
        bear = self.put(BEAR)
        veil = self.put(VEIL)
        attacks = next(t for t in VEIL.triggers if t.event == "creature_attacks")
        self.g.queue_trigger(self.a, attacks.effects, veil, "veil", context=bear)
        self.g.settle()
        self.assertIn(bear, self.a.battlefield)                # still here mid-combat
        self.assertEqual(self.phased(), [])
        self.g.end_combat(self.a)
        self.g.settle()
        self.assertIn(bear, self.phased())                     # gone at combat's end
        self.assertIn(veil, self.a.battlefield)               # the Veil itself stays

    def test_equipoise_excess_phase_out(self):
        equipoise = self.put(EQUIPOISE)
        for _ in range(2):
            self.g.enter_battlefield(self.a, ISLAND)
        opps = [self.g.enter_battlefield(self.b, ISLAND) for _ in range(5)]
        upkeep = EQUIPOISE.triggers[0]
        self.resolve(upkeep.effects, equipoise)
        still = [x for x in opps if x in self.b.battlefield]
        self.assertEqual(len(still), 2)                        # five beyond two: three go
        self.assertEqual(len(self.phased()), 3)

    def test_tefeis_realm_picks_the_cheapest_slice(self):
        artifact = card("Test Engine", "{4}", "Artifact")
        realm = self.put(REALM, self.b)
        bear = self.put(BEAR, self.b)
        engine = self.put(artifact, self.b)
        land = self.g.enter_battlefield(self.b, ISLAND)
        trig = REALM.triggers[0]
        self.resolve(trig.effects, realm, context=self.b)       # b's own upkeep
        self.assertNotIn(land, self.b.battlefield)             # the land was the cheapest
        self.assertIn(bear, self.b.battlefield)
        self.assertIn(engine, self.b.battlefield)
        self.assertIn(realm, self.b.battlefield)               # the Realm itself stays

    def test_spectral_adversary_pays_and_phases(self):
        adversary = self.put(ADVERSARY)
        for _ in range(6):
            self.g.enter_battlefield(self.a, ISLAND)
        bears = [self.put(BEAR, self.b) for _ in range(3)]
        trig = ADVERSARY.triggers[0]
        self.resolve(trig.effects, adversary)
        self.assertEqual(adversary.counters.get("+1/+1", 0), 3)    # paid three times
        self.assertEqual([x for x in bears if x in self.b.battlefield], [])   # all phased

"""Phasing: templates and engine behavior (chonk/vert batch 2)."""
import random
import unittest

from mtgsim import phasing
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


PROTECTION = card("Test Protection", "{2}{W}", "Instant",
                  "All permanents you control phase out.\nExile ~.")
EFREET = card("Test Efreet", "{2}{U}", "Creature — Efreet", "Flying\nPhasing", 2, 2)
IMP = card("Test Imp", "{2}{U}", "Creature — Imp",
           "Flying\nPhasing\nWhenever ~ phases out, discard a card.\nWhenever ~ phases in, draw a card.", 1, 1)
TELEPORT_DOG = card("Test Dog", "{2}{W}", "Creature — Dog",
                    "Teleport — {3}{W}: ~ phases out.", 1, 1)
CHARM = card("Test Charm", "{U}", "Instant", "Choose one —\n"
              "• Target player draws a card.\n• Target creature an opponent controls phases out.")
FIGHTER = card("Test Fighter", "{2}{U}", "Creature — Human Soldier",
               "Whenever ~ blocks or becomes blocked by a creature, ~ and that creature phase out.", 2, 2)
TIDE = card("Test Tide", "{1}{U}", "Instant",
            "Simultaneously, all phased-out creatures phase in and all creatures with phasing phase out.")
OUBLIETTE = real("Oubliette")
OUT_OF_TIME = real("Out of Time")
SLIP = card("Test Slip", "{W}", "Instant", "Put a +1/+1 counter on target creature. It phases out.")
AURA = card("Test Turtle Aura", "{U}", "Enchantment — Aura",
            "Enchant creature\nEnchanted creature gets +0/+2.")


class ParsePhasing(unittest.TestCase):
    def test_phasing_keyword(self):
        self.assertEqual(EFREET.keywords, frozenset({"flying", "phasing"}))
        self.assertEqual(EFREET.unsupported, [])

    def test_activated_phase_out(self):
        self.assertEqual([(a.text, [e.kind for e in a.effects]) for a in TELEPORT_DOG.activated],
                         [("Teleport — {3}{W}: ~ phases out.", ["phase_out"])])
        self.assertEqual(TELEPORT_DOG.activated[0].effects[0].target, "self")

    def test_targeted_phase_out_modes(self):
        kinds = [(e.kind, e.target, e.filter) for effs in CHARM.modes for e in effs]
        self.assertIn(("phase_out", "creature", "opp"), kinds)

    def test_phase_triggers(self):
        self.assertEqual([(t.event, [e.kind for e in t.effects]) for t in IMP.triggers],
                         [("phases_out", ["discard"]), ("phases_in", ["draw"])])

    def test_dream_fighter_blocks_trigger(self):
        self.assertEqual([(t.event, [e.kind for e in t.effects]) for t in FIGHTER.triggers],
                         [("blocks", ["phase_out", "phase_out"]),
                          ("becomes_blocked", ["phase_out", "phase_out"])])

    def test_time_and_tide_spell(self):
        self.assertEqual([(e.kind, e.data) for e in TIDE.spell_effects],
                         [("phase_in_all", {}), ("phase_out", {"phasing": True})])

    def test_slip_out_the_back_prev_target(self):
        self.assertEqual([(e.kind, e.target) for e in SLIP.spell_effects],
                         [("p1_counters", "creature_mine"), ("phase_out", "prev")])

    def test_until_leaves_template(self):
        effects = OUBLIETTE.triggers[0].effects
        self.assertEqual([(e.kind, e.target, e.data["until_leaves"], e.data["tap_on_in"]) for e in effects],
                         [("phase_out", "creature", True, True)])

    def test_out_of_time_template(self):
        effects = OUT_OF_TIME.triggers[0].effects
        self.assertEqual([e.kind for e in effects], ["phase_out", "phase_out_count"])
        self.assertTrue(effects[0].data["until_leaves"] and effects[0].data["creatures"])

    def test_real_cards_promoted(self):
        for name in ("Teferi's Protection", "Taniwha", "Haystack", "Reality Ripple", "Sapphire Charm",
                     "Galadriel's Dismissal", "Time and Tide", "Blink Dog",
                     "Mist Dragon", "Teferi's Imp", "Warping Wurm"):
            c = real(name)
            self.assertFalse([u for u in c.unsupported if "phas" in u.lower()], (name, c.unsupported))

    def test_tap_on_phase_in_rider(self):
        effects = OUBLIETTE.triggers[0].effects
        self.assertTrue(effects[0].data["tap_on_in"])   # Oubliette taps its creature on return
        self.assertEqual([e.kind for e in effects], ["phase_out"])


class PhasingEngine(unittest.TestCase):
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

    def apply(self, effects, targets=(), p=None, source=None):
        p = p or self.a
        targets = list(targets) + [None] * (len(effects) - len(targets))
        item = StackItem(p, effects, targets, source=source)
        prev = None
        for eff, target in zip(effects, targets):
            self.g.resolve(p, eff, target, item, prev=prev)
            prev = target
        return item

    def test_phase_out_hides_the_permanent(self):
        bear = self.put(BEAR)
        phasing.phase_out(self.g, bear)
        self.assertNotIn(bear, self.a.battlefield)
        self.assertEqual(self.a.creatures, [])
        self.assertIn(bear, phasing.phased_out(self.g))
        self.assertTrue(bear.phased_out)

    def test_phase_in_returns_without_enter_triggers(self):
        etb = card("Test Witness", "{2}{U}", "Creature — Human",
                   "When ~ enters, draw a card.", 1, 1)
        perm = self.put(etb)
        drawn = len(self.a.hand)
        phasing.phase_out(self.g, perm)
        phasing.phase_in(self.g, perm)
        self.assertIn(perm, self.a.battlefield)
        self.assertEqual(len(self.a.hand), drawn)          # phasing in is not entering

    def test_attached_auras_phase_out_together(self):
        bear = self.put(BEAR)
        aura = self.put(AURA, self.b)
        aura.attached_to = bear
        phasing.phase_out(self.g, bear)
        self.assertNotIn(aura, self.b.battlefield)
        phasing.phase_in(self.g, bear)
        self.assertIn(aura, self.b.battlefield)             # attached, both back
        self.assertIs(aura.attached_to, bear)

    def test_untap_hook_alternates_a_phasing_creature(self):
        perm = self.put(EFREET)
        phasing.phasing_untap(self.g, self.a)
        self.assertNotIn(perm, self.a.battlefield)
        phasing.phasing_untap(self.g, self.a)
        self.assertIn(perm, self.a.battlefield)             # phased in, not straight back out
        phasing.phasing_untap(self.g, self.a)
        self.assertNotIn(perm, self.a.battlefield)

    def test_untap_hook_returns_opponents_permanents_to_their_controller(self):
        bear = self.put(BEAR, self.b)
        phasing.phase_out(self.g, bear)
        phasing.phasing_untap(self.g, self.a)               # a's untap does not return b's card
        self.assertNotIn(bear, self.b.battlefield)
        phasing.phasing_untap(self.g, self.b)
        self.assertIn(bear, self.b.battlefield)

    def test_single_target_phase_out_effect(self):
        bear = self.put(BEAR)
        self.apply([Effect("phase_out", target="creature")], [bear])
        self.assertNotIn(bear, self.a.battlefield)

    def test_all_yours_phase_out(self):
        self.put(BEAR)
        self.put(BEAR)
        self.put(BEAR, self.b)
        self.apply([Effect("phase_out", data={"mine": True})])
        self.assertEqual(self.a.battlefield, [])
        self.assertEqual(len(self.b.battlefield), 1)
        self.assertEqual(len(phasing.phased_out(self.g)), 2)   # a's two bears only

    def test_phase_out_effect_fires_the_trigger(self):
        imp = self.put(IMP)
        self.a.hand = [ISLAND, ISLAND, ISLAND]
        hand = len(self.a.hand)
        phasing.phase_out(self.g, imp)
        self.g.settle()
        self.assertEqual(len(self.a.hand), hand - 1)       # "whenever ~ phases out, discard"
        phasing.phase_in(self.g, imp)
        self.g.settle()
        self.assertEqual(len(self.a.hand), hand)            # "whenever ~ phases in, draw"

    def test_until_leaves_returns_when_the_anchor_dies(self):
        oubliette = self.put(OUBLIETTE)
        bear = self.put(BEAR, self.b)
        self.apply(OUBLIETTE.triggers[0].effects, [bear], p=self.a, source=oubliette)
        self.assertNotIn(bear, self.b.battlefield)
        self.g.sacrifice(oubliette)
        self.g.settle()
        self.assertIn(bear, self.b.battlefield)             # Oubliette left: the creature returns

    def test_out_of_time_phases_creatures_out_and_counts_them(self):
        oot = self.put(OUT_OF_TIME)
        self.put(BEAR)
        self.put(BEAR, self.b)
        self.apply(OUT_OF_TIME.triggers[0].effects, p=self.a, source=oot)
        phased = phasing.phased_out(self.g)
        self.assertEqual(len(phased), 2)                    # both players' creatures, not the saga
        self.assertNotIn(oot, phased)
        self.assertEqual(oot.counters.get("time"), 2)      # one per creature that phased out

    def test_time_and_tide_flips_everything(self):
        efreet = self.put(EFREET)
        bear = self.put(BEAR)
        phasing.phase_out(self.g, bear)
        self.apply(TIDE.spell_effects)
        self.assertIn(bear, self.a.battlefield)             # phased back in
        self.assertNotIn(efreet, self.a.battlefield)        # but the phasing creature phased out

    def test_frenetic_efreet_coin_flip(self):
        self.apply([Effect("phase_coin", target="self")])   # resolves without error either way
        outcomes = []
        for seed in range(12):
            self.g.rng = random.Random(seed)
            e2 = self.put(card(f"Test Frenetic{seed}", "{1}{U}", "Creature — Efreet", "", 2, 1))
            self.apply([Effect("phase_coin", target="self")], source=e2)
            outcomes.append(bool(getattr(e2, "phased_out", False)))   # True: flipped to phase out
        self.assertIn(True, outcomes)                      # some flips phase it out
        self.assertIn(False, outcomes)                     # some flips sacrifice it

    def test_king_phases_out_when_targeted(self):
        king = real("King of the Oathbreakers")
        perm = self.put(king)
        self.g.fire(self.a, "targeted_by_spell", perm, context=self.b)
        self.g.settle()
        self.assertNotIn(perm, self.a.battlefield)
        self.assertIn(perm, phasing.phased_out(self.g))
        spirits = [x for x in self.a.battlefield if "Spirit" in x.card.subtypes]
        self.assertEqual(spirits, [])                       # it phased out before its token trigger


class RippleEngine(unittest.TestCase):
    pass  # ripple tests live in test_chonk_vert2_ripple.py


if __name__ == "__main__":
    unittest.main()

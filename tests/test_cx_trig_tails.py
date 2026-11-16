"""#404 tails: tap-for-mana heads, 'an Aura becomes attached to', -1/-1 counter heads, 'you become the target of',
and 'snow' in the noun-phrase readers."""
import os
import random
import unittest

from mtgsim.carddb import CardDB

from mtgsim.cx_events import compile_head
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_combat_triggers import BEAR, Scripted
from tests.test_templates import ISLAND, MOUNTAIN, card

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None
SNOW_LAND = card("Test Snow Forest", "", "Basic Snow Land — Forest", "{T}: Add {G}.")


class Heads(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(compile_head("Whenever a player taps an Island for mana")[0], ("tapped_for_mana",))
        self.assertEqual(compile_head("Whenever you tap ~ for mana")[1]["kind"], "tap_self")
        self.assertEqual(compile_head("Whenever an Aura becomes attached to ~")[0], ("aura_attached",))
        self.assertEqual(compile_head("Whenever you put one or more -1/-1 counters on a creature")[0], ("m1_added",))
        self.assertEqual(compile_head("Whenever you become the target of a spell")[0], ("player_targeted",))

    def test_refusals(self):
        for head in ("Whenever a player taps a creature for mana",      # not a land word
                     "Whenever ~ becomes attached to a creature",       # not this grammar: cx_trig_attach (#538)
                     "Whenever you put one or more frob counters on a creature",
                     "Whenever you become the target of a frob"):
            self.assertIsNone(compile_head(head), head)
        for name in ("Groundchuck & Dirtbag", "Amulet of Safekeeping"):
            if DB is not None:
                self.assertTrue(DB.get(name).unsupported, name)     # mana payoff / ability counter
        if DB is not None:                                          # the Equipment head is read by cx_trig_attach
            self.assertFalse(DB.get("Enormous Energy Blade").unsupported)   # (#538)


@unittest.skipUnless(HAVE_DB, "card database not built")
class Games(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 2, "main1", 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def test_full(self):
        for n in ("Manabarbs", "Scald", "Sanctimony", "Burning Earth", "Zhur-Taa Druid", "Vorinclex, Voice of Hunger",
                  "Forbidden Orchard", "Savage Firecat", "Bramble Elemental", "Siona, Captain of the Pyleas",
                  "Obelisk Spider", "Defiant Greatmaw", "Wickersmith's Tools", "Casey Jones, Back Alley Brute",
                  "Dormant Gomazoa", "Ronom Serpent", "Iceberg Cancrix"):
            self.assertEqual(DB.get(n).unsupported, [], n)

    def test_scald_hurts_whoever_taps_an_island(self):
        self.put(self.a, DB.get("Scald"))
        self.put(self.b, ISLAND)
        self.put(self.b, MOUNTAIN)
        self.game.pay(self.b, {"R": 1})
        self.game.settle()
        self.assertEqual(self.b.life, 20)
        self.game.pay(self.b, {"U": 1})
        self.game.settle()
        self.assertEqual(self.b.life, 19)

    def test_vorinclex_freezes_that_land(self):
        self.put(self.a, DB.get("Vorinclex, Voice of Hunger"))
        land = self.put(self.b, MOUNTAIN)
        self.game.pay(self.b, {"R": 1})
        self.game.settle()
        self.assertTrue(land.tapped)
        self.game.untap_step(self.b)
        self.assertTrue(land.tapped)                        # doesn't untap during its controller's next untap step

    def test_aura_attached_to_self(self):
        bramble = self.put(self.a, DB.get("Bramble Elemental"))
        aura = self.put(self.a, card("Test Aura", "{G}", "Enchantment — Aura", "Enchant creature\nEnchanted creature "
                                     "gets +1/+1.", 0, 0))
        tokens = len([x for x in self.a.battlefield if x.card.is_token])
        from mtgsim import auras
        auras.attach(self.game, aura, bramble)
        self.game.settle()
        self.assertEqual(len([x for x in self.a.battlefield if x.card.is_token]), tokens + 2)

    def test_minus_counters_you_put(self):
        self.put(self.a, DB.get("Obelisk Spider"))
        bear = self.put(self.b, BEAR)
        shrink = card("Test Shrink", "{B}", "Instant", "Put a -1/-1 counter on target creature.")
        self.game.stack.append(StackItem(self.a, shrink.spell_effects, [bear], card=shrink, kind="spell"))
        self.game.settle()                                  # a's spell puts it on b's creature
        self.assertEqual((self.a.life, self.b.life), (21, 19))

    def test_you_become_the_target_of_a_spell(self):
        gom = self.put(self.a, DB.get("Dormant Gomazoa"))
        gom.tapped = True
        self.a.ai = type("Yes", (Scripted,), {"choose_yes": lambda *a, **k: True})()
        bolt = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 1 damage to any target.")
        self.game.check_ward(StackItem(self.b, bolt.spell_effects, [self.b], card=bolt, kind="spell"))
        self.game.settle()
        self.assertTrue(gom.tapped)                         # the opponent targeted itself
        self.game.check_ward(StackItem(self.b, bolt.spell_effects, [self.a], card=bolt, kind="spell"))
        self.game.settle()
        self.assertFalse(gom.tapped)

    def test_snow_lands_state_trigger(self):
        serpent = self.put(self.a, DB.get("Ronom Serpent"))
        self.game.state_based_actions()
        self.assertNotIn(serpent, self.a.battlefield)
        self.put(self.a, SNOW_LAND)
        serpent = self.put(self.a, DB.get("Ronom Serpent"))
        self.game.state_based_actions()
        self.assertIn(serpent, self.a.battlefield)


if __name__ == "__main__":
    unittest.main()

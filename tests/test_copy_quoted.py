"""Copy exceptions that grant a quoted ability: 'except it has "{T}: Add {U}."' (#340 slice 5, copies.quoted_grant).
The quoted ability becomes a copiable value of the copy (rule 707.9a)."""
import dataclasses
import os
import random
import unittest

from mtgsim import copies
from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

LEGEND = card("Test Legend", "{3}{G}", "Legendary Creature — Elf Warrior", "Trample", 5, 4)
BEAR = card("Test Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
LORD = card("Test Lord", "{2}{G}", "Creature — Elf", "When ~ enters, you gain 2 life.", 3, 3)
BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 1 damage to target creature.")


class Parse(unittest.TestCase):
    def test_grants(self):
        mods = copies.parse_except('it has haste and "At the beginning of the end step, exile ~."')
        self.assertEqual(mods["keywords"], frozenset({"haste"}))
        self.assertEqual([t.event for t in mods["grant"]["triggers"]], ["each_end_step"])
        mods = copies.parse_except('it\'s an artifact and it has "{T}: Add {U}."')
        self.assertEqual(mods["set_types"], frozenset({"Artifact"}))
        self.assertEqual(mods["grant"], {"produces": frozenset({"U"})})
        mods = copies.parse_except('it has "{2}{U}{U}: Return ~ to its owner\'s hand."')
        self.assertEqual(len(mods["grant"]["activated"]), 1)

    def test_refusals(self):
        for text in ('it has "Other creatures with the same name as ~ are goaded."',      # quote not parsed
                     'it has "{U}{B}, {T}: Destroy target creature with the same name as ~."',
                     'it has "~ is the best creature."',
                     'it has haste and "flurble"',
                     'it has "{T}: Add {U}." and it wobbles'):
            self.assertIsNone(copies.parse_except(text), text)

    def test_clone_lines_ending_in_a_quote(self):
        line = 'You may have ~ enter as a copy of any creature on the battlefield, except it has "Whenever ~ attacks, it connives."'
        spec = copies.parse_line(line)["clone"]
        self.assertEqual([t.event for t in spec["mods"]["grant"]["triggers"]], ["attacks"])
        self.assertIsNone(copies.parse_line(line[:-2] + ' and flurbles."'))


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class Games(unittest.TestCase):
    FULL = ("Progenitor Mimic", "Phantasmal Image", "Mercurial Pretender", "Copycrook", "Machine God's Effigy", "Sakashima the Impostor",
            "Colossal Clone Master", "Heat Shimmer", "Cephalid Facetaker", "Aggressive Biomancy")
    STILL_PARTIAL = ("Evil Twin", "Mocking Doppelganger", "Gigantoplasm")

    def setUp(self):
        self.db = CardDB(offline=True)
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def test_status(self):
        for name in self.FULL:
            self.assertEqual(self.db.get(name).unsupported, [], name)
        for name in self.STILL_PARTIAL:
            self.assertTrue(self.db.get(name).unsupported, name)

    def clone(self, name, who=None):
        perm = self.g.enter_battlefield(who or self.a, self.db.get(name))
        self.g.settle()
        return perm

    def test_nontoken_upkeep_grant_is_inherited_but_does_not_trigger_on_tokens(self):
        self.g.enter_battlefield(self.b, BEAR)
        mimic = self.clone("Progenitor Mimic")
        self.g.fire(self.a, "upkeep", source=mimic)
        self.g.settle()
        tokens = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual(len(tokens), 1)
        token = tokens[0]
        self.assertEqual(token.card.name, BEAR.name)
        self.assertTrue(any(t.intervening_if for t in token.card.triggers))
        self.g.fire(self.a, "upkeep", source=token)
        self.assertFalse(self.g.pending)
        self.assertEqual(len([x for x in self.a.battlefield if x.card.is_token]), 1)

    def test_nontoken_upkeep_condition_is_rechecked_on_resolution(self):
        self.g.enter_battlefield(self.b, BEAR)
        mimic = self.clone("Progenitor Mimic")
        self.g.fire(self.a, "upkeep", source=mimic)
        self.g.flush_triggers()
        self.assertTrue(self.g.stack)
        mimic.card = dataclasses.replace(mimic.card, is_token=True)
        self.g.settle()
        self.assertEqual(len(self.a.battlefield), 1)

    def test_phantasmal_image_is_an_illusion_and_dies_when_targeted(self):
        self.g.enter_battlefield(self.b, LEGEND)
        image = self.clone("Phantasmal Image")
        self.assertEqual((image.card.name, image.power, image.toughness), ("Test Legend", 5, 4))
        self.assertIn("Illusion", image.card.subtypes)
        self.assertIn("Elf", image.card.subtypes)
        self.assertIn("trample", image.card.keywords)
        self.b.hand = [BOLT]
        self.g.enter_battlefield(self.b, card("Mountain", types="Basic Land — Mountain",
                                              text="({T}: Add {R}.)")).sick = False
        self.assertTrue(self.g.cast(self.b, BOLT, [image]))
        self.g.settle()
        self.assertNotIn(image, self.a.battlefield)
        self.assertIn("Phantasmal Image", [c.name for c in self.a.graveyard])     # it dies as itself

    def test_mercurial_pretender_can_return_itself(self):
        self.g.enter_battlefield(self.a, LORD)
        pretender = self.clone("Mercurial Pretender")
        self.assertEqual(pretender.card.name, "Test Lord")
        self.assertEqual(self.a.life, 24)                       # the copied ETB fired
        for _ in range(4):
            self.g.enter_battlefield(self.a, ISLAND).sick = False
        idx = next(i for i, act in enumerate(pretender.activated) if "Return ~" in act.text)
        self.assertTrue(self.g.activate_ability(self.a, pretender, idx))
        self.g.settle()
        self.assertIn("Mercurial Pretender", [c.name for c in self.a.hand])

    def test_machine_gods_effigy_is_a_mana_artifact_not_a_creature(self):
        self.g.enter_battlefield(self.b, LEGEND)
        effigy = self.clone("Machine God's Effigy")
        self.assertEqual(effigy.card.name, "Test Legend")
        self.assertFalse(effigy.is_creature)
        self.assertEqual(effigy.card.types, frozenset({"Artifact"}))
        self.assertIn("U", effigy.card.produces)
        effigy.sick = False
        self.assertIn(effigy, self.g.mana_sources(self.a))

    def test_colossal_clone_master_counts_differently_named_lands(self):
        self.g.enter_battlefield(self.b, LEGEND)
        for land in (ISLAND, ISLAND, card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")):
            self.g.enter_battlefield(self.a, land)
        master = self.clone("Colossal Clone Master")
        self.assertEqual(master.card.name, "Test Legend")
        self.assertFalse(master.card.legendary)
        self.assertIn("trample", master.card.keywords)
        self.assertEqual((master.power, master.toughness), (2, 2))      # not the copied 5/4
        self.g.enter_battlefield(self.a, card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)"))
        self.assertEqual((master.power, master.toughness), (3, 3))

    def test_awakened_amalgam_counts_names_not_lands(self):
        """cx_cda: "differently named lands" counted every land as unknown (0) before; it counts distinct names."""
        for land in (ISLAND, ISLAND, card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")):
            self.g.enter_battlefield(self.a, land)
        amalgam = self.clone("Awakened Amalgam")
        self.assertIn(amalgam, self.a.battlefield)
        self.assertEqual((amalgam.power, amalgam.toughness), (2, 2))

    def test_copycrook_connives_on_attack(self):
        self.g.enter_battlefield(self.a, BEAR)
        crook = self.clone("Copycrook")
        crook.sick = False
        self.a.hand = [card("Test Spell", "{1}", "Sorcery", "Draw a card.")]
        self.a.ai.attack = (crook,)
        self.g.step = "main1"
        self.g.combat(self.a, self.b)
        self.g.settle()
        self.assertEqual(crook.counters.get("+1/+1", 0), 1)      # discarded a nonland card

    def test_heat_shimmer_token_hastes_then_exiles(self):
        bear = self.g.enter_battlefield(self.a, LORD)
        for _ in range(3):
            self.g.enter_battlefield(self.a, card("Mountain", types="Basic Land — Mountain",
                                                  text="({T}: Add {R}.)")).sick = False
        shimmer = self.db.get("Heat Shimmer")
        self.a.hand = [shimmer]
        self.assertTrue(self.g.cast(self.a, shimmer, [bear]))
        self.g.settle()
        token = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertTrue(token.has("haste"))
        self.g.begin_end_step(self.a)
        self.g.settle()
        self.assertNotIn(token, self.a.battlefield)
        self.assertIn(bear, self.a.battlefield)

    def test_ai_casts_a_quoted_clone(self):
        self.a.ai = HeuristicAI()
        for _ in range(4):
            self.g.enter_battlefield(self.a, ISLAND).sick = False
        self.g.enter_battlefield(self.b, LEGEND)
        self.a.hand = [self.db.get("Phantasmal Image")]
        self.a.ai.main_phase(self.g, self.a)
        self.g.settle()
        image = next(x for x in self.a.battlefield if not x.card.is_land)
        self.assertEqual(image.card.name, "Test Legend")
        self.assertIn("Illusion", image.card.subtypes)


if __name__ == "__main__":
    unittest.main()

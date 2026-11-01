"""Mixed sentences, basic land type statics and "damage prevented this way" riders."""
import random
import unittest

from mtgsim.engine import Game, Player
from mtgsim.engine.state import can_block
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

HEROISM = card("Test Heroism", "{1}{W}", "Instant",
               "Untap target creature. It gets +2/+2 until end of turn and can block an additional creature this turn.")
CARAPACE = card("Test Carapace", "{1}", "Artifact — Equipment", "Equipped creature gets +2/+2 and can't block.\nEquip {3}")
IMP = card("Test Imp", "{B}", "Creature — Imp",
           "Flying\nThreshold — As long as there are seven or more cards in your graveyard, ~ gets +1/+1 and can't block.", 1, 1)
DRYAD = card("Test Dryad", "{1}{G}", "Creature — Dryad",
             "Lands you control are every basic land type in addition to their other types.", 2, 1)
GROUND = card("Test Ground", "{2}{B}", "Enchantment — Aura", "Enchant land\nEnchanted land is a Swamp.")
CHANT = card("Test Chant", "{6}{W}{W}", "Instant",
             "Prevent all damage that would be dealt by creatures this turn. You gain life equal to the damage prevented this way.")
HYDRA = card("Test Hydra", "{3}{W}", "Creature — Phyrexian Hydra",
             "If damage would be dealt to ~, prevent that damage. Put a -1/-1 counter on ~ for each 1 damage prevented this way.", 5, 5)


class Mixed(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_parse(self):
        for c in (HEROISM, CARAPACE, IMP, DRYAD, GROUND, CHANT, HYDRA):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual([e.kind for e in HEROISM.spell_effects][-2:], ["pump", "grant"])

    def test_equipment_and_threshold(self):
        bear = self.game.enter_battlefield(self.a, BEAR)
        gear = self.game.enter_battlefield(self.a, CARAPACE)
        gear.attached_to = bear
        bear.equipment.append(gear)
        self.assertEqual(bear.power, 4)
        self.assertTrue(bear.has("cant_block_now"))
        imp = self.game.enter_battlefield(self.a, IMP)
        attacker = self.game.enter_battlefield(self.b, BEAR)
        self.assertTrue(can_block(imp, attacker) or imp.has("flying"))
        self.a.graveyard = [ISLAND] * 7
        self.assertEqual(imp.power, 2)
        self.assertFalse(can_block(imp, attacker))

    def test_land_types(self):
        land = self.game.enter_battlefield(self.a, MOUNTAIN)
        self.game.enter_battlefield(self.a, DRYAD)
        self.game.state_based_actions()
        self.assertEqual(land.card.produces, {"W", "U", "B", "R", "G"})
        self.assertIn("Forest", land.card.subtypes)
        theirs = self.game.enter_battlefield(self.b, MOUNTAIN)
        aura = self.game.enter_battlefield(self.a, GROUND)
        aura.aura_host = theirs
        theirs.auras.append(aura)
        self.game.state_based_actions()
        self.assertEqual(theirs.card.produces, {"B"})
        self.assertNotIn("Mountain", theirs.card.subtypes)

    def test_riders(self):
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.game.resolve(self.a, CHANT.spell_effects[0], None)
        self.game.resolve(self.a, CHANT.spell_effects[1], None)
        self.game.deal_damage(self.a, 2, self.b, source=bear, combat=True)
        self.assertEqual(self.a.life, 22)
        hydra = self.game.enter_battlefield(self.a, HYDRA)
        self.game.deal_damage(hydra, 2, self.b)
        self.assertEqual((hydra.damage, hydra.counters.get("-1/-1")), (0, 2))


if __name__ == "__main__":
    unittest.main()


TEMPER = card("Test Temper", "{X}{1}{W}", "Instant",
              "Prevent the next X damage that would be dealt to target creature this turn. "
              "For each 1 damage prevented this way, put a +1/+1 counter on that creature.")
INKSHIELD = card("Test Inkshield", "{3}{W}{B}", "Instant",
                 "Prevent all combat damage that would be dealt to you this turn. "
                 "For each 1 damage prevented this way, create a 2/1 white and black Inkling creature token with flying.")
JORAGA = card("Test Joraga", "{4}{G}{G}", "Sorcery",
              "Each creature you control gets +3/+3 until end of turn and must be blocked this turn if able.")
SCARHIDE = card("Test Scarhide", "{B}", "Enchantment Creature — Satyr",
                "Bestow {1}{B}\nEnchanted creature gets +2/+1 and can't block.", 2, 1)


class MoreMixed(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def test_parse(self):
        for c in (TEMPER, INKSHIELD, JORAGA, SCARHIDE):
            self.assertEqual(c.unsupported, [], c.name)

    def test_temper_pool_and_counters(self):
        from mtgsim.engine.state import StackItem
        bear = self.game.enter_battlefield(self.a, BEAR)
        item = StackItem(self.a, TEMPER.spell_effects, [bear], card=TEMPER)
        item.x = 2
        for eff in TEMPER.spell_effects:
            self.game.resolve(self.a, eff, bear, item=item)
        self.game.deal_damage(bear, 3, self.b)
        self.assertEqual((bear.damage, bear.counters.get("+1/+1")), (1, 2))

    def test_inkshield_tokens(self):
        attacker = self.game.enter_battlefield(self.b, BEAR)
        for eff in INKSHIELD.spell_effects:
            self.game.resolve(self.a, eff, None)
        self.game.deal_damage(self.a, 2, self.b, source=attacker, combat=True)
        self.assertEqual(self.a.life, 20)
        self.assertEqual(len([x for x in self.a.battlefield if x.card.is_token]), 2)

    def test_group_must_be_blocked(self):
        bears = [self.game.enter_battlefield(self.a, BEAR) for _ in range(2)]
        for eff in JORAGA.spell_effects:
            self.game.resolve(self.a, eff, None)
        self.assertTrue(all(b.has("must_be_blocked_now") and b.power == 5 for b in bears))

    def test_bestow_restriction(self):
        from mtgsim.batch1_templates import bestow_face
        face = bestow_face(SCARHIDE, {"generic": 1, "B": 1})
        self.assertIn("cant_block_now", face.equip_keywords)

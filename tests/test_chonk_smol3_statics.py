"""smol-chonk-3 batch 4: static lines — spell-kind cast bans, restricted Equip, ability-word
prefixes, opponent-only "can't block this turn", and the no-creatures-on-the-battlefield trigger
condition.

Engine sides: advanced_rules["no_cast"] (le-chonk-3, 54ee364), equip_restriction (e5e1a68),
cant_block_all data["theirs"] (54ee364). The "if no creatures are on the battlefield" condition
is parsed to cond "no_creatures_bf"; the engine's check_cond still needs that branch (cross-area
queue) — the tests here pin the parse shape, not the runtime gate.
"""
import random
import unittest

from mtgsim.engine import Game, Permanent, Player, can_block
from mtgsim.engine.policy import equip_matches
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, MOUNTAIN, card

STORM = card("Aether Storm", "{2}{U}{U}", "Enchantment",
             "Creature spells can't be cast.\nPay 4 life: Destroy Aether Storm. It can't be "
             "regenerated. Any player may activate this ability.")
SWORD = card("Test Sword", "{2}", "Artifact — Equipment",
             "Equipped creature gets +1/+1.\nEquip Soldier {2}")
BAT = card("Ace's Baseball Bat", "{2}", "Artifact — Equipment",
           "Equipped creature gets +3/+0.\nEquip legendary creature {1}")
WARDEN = card("Royal Warden", "{3}{B}", "Creature — Necron Warrior",
              "Phalanx Commander — When Royal Warden enters, create two tapped 2/2 black Necron "
              "Warrior artifact creature tokens.", 2, 3)
WAVE = card("Cosmotronic Wave", "{3}{R}", "Sorcery",
            "Cosmotronic Wave deals 1 damage to each creature your opponents control. Creatures "
            "your opponents control can't block this turn.")
PESTILENCE = card("Pestilence", "{2}{B}{B}", "Enchantment",
                  "At the beginning of the end step, if no creatures are on the battlefield, "
                  "sacrifice this enchantment.\n{B}: This enchantment deals 1 damage to each "
                  "creature and each player.")
LEGEND = card("Test Legend", "{1}{W}", "Legendary Creature — Human", "", 2, 2)
SOLDIER = card("Test Soldier", "{1}{W}", "Creature — Human Soldier", "", 2, 2)


class StaticLines(unittest.TestCase):
    def test_spell_kind_cast_ban(self):
        self.assertEqual(STORM.unsupported, [])              # the destroy line parses too
        self.assertEqual(STORM.advanced_rules["no_cast"], ("creature",))
        self.assertTrue(STORM.activated[0].any_player)

    def test_no_cast_stops_creature_spells(self):
        a, b = Player("a", [BEAR] * 20, Scripted()), Player("b", [], Scripted())
        game = Game(a, b, random.Random(0))
        game.turn, game.step, game.active_idx = 2, "main1", 0
        storm = Permanent(STORM, a)
        storm.sick = False
        a.battlefield.append(storm)
        for _ in range(4):
            land = Permanent(MOUNTAIN, a)
            land.sick = False
            a.battlefield.append(land)
        redbear = card("Test Red Bear", "{1}{R}", "Creature — Bear", "", 2, 2)
        a.hand = [redbear]
        self.assertFalse(game.can_cast_now(a, redbear))      # creature spells banned
        a.battlefield.remove(storm)
        self.assertTrue(game.can_cast_now(a, redbear))

    def test_equip_restriction_parse(self):
        self.assertEqual(SWORD.unsupported, [])
        self.assertEqual(SWORD.advanced_rules["equip_restriction"], "Soldier")
        self.assertEqual(BAT.advanced_rules["equip_restriction"], "legendary")

    def test_equip_restriction_matches(self):
        self.assertTrue(equip_matches(Permanent(SOLDIER, None), "Soldier"))
        self.assertFalse(equip_matches(Permanent(BEAR, None), "Soldier"))
        self.assertTrue(equip_matches(Permanent(LEGEND, None), "legendary"))
        self.assertFalse(equip_matches(Permanent(SOLDIER, None), "legendary"))

    def test_ability_word_prefix_before_when(self):
        self.assertEqual(WARDEN.unsupported, [])
        etb = [t for t in WARDEN.triggers if t.event == "etb"]
        self.assertEqual(len(etb), 1)
        self.assertEqual(etb[0].effects[0].kind, "token")
        self.assertEqual((etb[0].effects[0].data["power"], etb[0].effects[0].data["toughness"]), (2, 2))

    def test_opponents_cant_block_parse_and_end_to_end(self):
        self.assertEqual(WAVE.unsupported, [])
        kinds = [e.kind for e in WAVE.spell_effects]
        self.assertEqual(WAVE.unsupported, [])
        self.assertIn("damage_group", kinds)
        self.assertIn("cant_block_all", kinds)
        cant = [e for e in WAVE.spell_effects if e.kind == "cant_block_all"][0]
        self.assertTrue(cant.data["theirs"])
        a, b = Player("a", [BEAR] * 20, Scripted()), Player("b", [], Scripted())
        game = Game(a, b, random.Random(0))
        game.turn, game.step, game.active_idx = 2, "main1", 0
        for _ in range(5):
            land = Permanent(MOUNTAIN, a)
            land.sick = False
            a.battlefield.append(land)
        a.hand = [WAVE]
        mine = Permanent(BEAR, a)
        mine.sick = False
        theirs = Permanent(BEAR, b)
        theirs.sick = False
        a.battlefield.append(mine)
        b.battlefield.append(theirs)
        self.assertTrue(game.cast(a, WAVE, targets=[]))
        game.settle()
        self.assertFalse(can_block(theirs, mine))            # only the opponent's creatures can't block
        self.assertTrue(can_block(mine, theirs))
        self.assertEqual(theirs.damage, 1)

    def test_no_creatures_condition_parse(self):
        self.assertEqual(PESTILENCE.unsupported, [])
        end_step = [t for t in PESTILENCE.triggers if t.event in ("end_step", "each_end_step")][0]
        self.assertEqual(end_step.intervening_if, "no_creatures_bf")
        self.assertEqual(end_step.effects[0].kind, "sacrifice_self")
        self.assertEqual(end_step.effects[0].cond, "no_creatures_bf")
        ping = PESTILENCE.activated[0]
        self.assertEqual([(e.kind, e.target, e.filter) for e in ping.effects],
                         [("damage", "each_creature", ""), ("damage_each_player", "none", "")])


if __name__ == "__main__":
    unittest.main()

"""Rank-pool card gaps: colored counterspells, typed attack triggers, discard counters, "~ gains ... Tap it.",
Auras with ward, a choice of keywords, kicked damage to that creature, graveyard-cast draws, artifact and creature
wipes, and exiling a card from a hand until ~ leaves."""
import random
import unittest

from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

FLASHFREEZE = card("Test Flashfreeze", "{1}{U}", "Instant", "Counter target red or green spell.")
ZORALINE = card("Test Zoraline", "{2}{W}{B}", "Legendary Creature — Bat Cleric",
                "Flying\nWhenever a Bat you control attacks, you gain 1 life.", 3, 3)
ATARKA = card("Test Atarka", "{5}{R}{R}", "Legendary Creature — Dragon",
              "Flying\nWhenever a Dragon you control attacks, it gains double strike until end of turn.", 6, 4)
BAT = card("Test Bat", "{1}{B}", "Creature — Bat", "Flying", 1, 1)
MAKO = card("Test Mako", "{U}{R}", "Creature — Shark",
            "Whenever you discard one or more cards, put that many +1/+1 counters on ~.", 1, 1)
ELF = card("Test Iron-Shield Elf", "{1}{B}", "Creature — Elf Warrior",
           "Discard a card: ~ gains indestructible until end of turn. Tap it.", 3, 1)
SHELTER = card("Test Shelter", "{1}{W}", "Enchantment — Aura",
               "Enchant creature you control\nEnchanted creature gets +1/+0 and has lifelink and ward {2}.")
SERAPH = card("Test Seraph", "{4}", "Artifact Creature — Construct",
              "At the beginning of combat on your turn, target creature you control gains your choice of flying, "
              "vigilance, or lifelink until end of turn.", 4, 4)
LESSON = card("Test Lesson", "{R}", "Sorcery", "Kicker {4}\n~ deals 2 damage to target creature. If this spell was "
                                               "kicked, it deals 5 damage to that creature instead.")
PLUNDER = card("Test Plunder", "{1}{U}", "Sorcery", "Draw a card. If this spell was cast from a graveyard, draw two "
                                                    "cards instead.\nFlashback {3}{U}")
ULTIMA = card("Test Wipe", "{3}{W}{W}", "Sorcery", "Destroy all artifacts and creatures.")
FREEBOOTER = card("Test Freebooter", "{1}", "Artifact Creature — Pirate", "Flying\nWhen ~ enters, target opponent "
                  "reveals their hand. You choose a noncreature, nonland card from it. Exile that card until ~ leaves "
                  "the battlefield.", 1, 1)
SHOCK = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to any target.")
GROWTH = card("Test Growth", "{G}", "Instant", "Target creature gets +3/+3 until end of turn.")
DOOM = card("Test Doom", "{1}{B}", "Instant", "Destroy target creature.")


class PoolGaps(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def test_templates(self):
        for c in (FLASHFREEZE, ATARKA, ZORALINE, MAKO, ELF, SHELTER, SERAPH, LESSON, PLUNDER, ULTIMA, FREEBOOTER):
            self.assertEqual(c.unsupported, [], c.name)

    def test_colored_counterspell(self):
        eff = FLASHFREEZE.spell_effects[0]
        red = StackItem(self.b, list(SHOCK.spell_effects), [self.a], card=SHOCK, kind="spell")
        blue = StackItem(self.b, list(PLUNDER.spell_effects), [], card=PLUNDER, kind="spell")
        self.game.stack.extend([red, blue])
        self.assertTrue(self.game.can_counter(eff, red, self.a))
        self.assertFalse(self.game.can_counter(eff, blue, self.a))

    def test_typed_attack_trigger(self):
        self.put(self.a, ZORALINE)
        bat, bear = self.put(self.a, BAT), self.put(self.a, BEAR)
        self.a.ai.attack = [bat, bear]
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(self.a.life, 21)                   # the Bat attacked; the Bear didn't count

    def test_typed_attack_trigger_targets_the_attacker(self):
        atarka = self.put(self.a, ATARKA)
        self.a.ai.attack = [atarka]
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(self.b.life, 8)                    # double strike: 6 twice

    def test_discard_puts_counters(self):
        mako = self.put(self.a, MAKO)
        self.a.hand[:] = [ISLAND, ISLAND]
        for c in list(self.a.hand):
            self.game.discard_card(self.a, c)
        self.game.settle()
        self.assertEqual(mako.p1, 2)

    def test_gains_indestructible_then_taps(self):
        elf = self.put(self.a, ELF)
        self.a.hand[:] = [ISLAND]
        self.assertTrue(self.game.activate_ability(self.a, elf, 0))
        self.game.settle()
        self.assertTrue(elf.has("indestructible"))
        self.assertTrue(elf.tapped)

    def test_aura_grants_ward(self):
        self.assertEqual((SHELTER.equip_bonus, SHELTER.equip_ward), ((1, 0), 2))
        self.assertIn("lifelink", SHELTER.equip_keywords)

    def test_choice_of_keywords(self):
        bear = self.put(self.a, BEAR)
        self.game.resolve(self.a, SERAPH.triggers[0].effects[0], bear)
        self.assertTrue(bear.has("flying"))
        flier = self.put(self.a, BAT)
        self.game.resolve(self.a, SERAPH.triggers[0].effects[0], flier)
        self.assertTrue(flier.has("lifelink"))

    def test_kicked_damage(self):
        kicked = next(a for a in LESSON.alt_costs if a.kind == "kicker")
        self.assertEqual([e.amount for e in kicked.effects if e.kind == "damage"], [5])

    def test_graveyard_cast_draws_more(self):
        fb = next(a for a in PLUNDER.alt_costs if a.kind == "flashback")
        self.assertEqual([e.amount for e in fb.effects if e.kind == "draw"], [2])
        self.assertEqual([e.amount for e in PLUNDER.spell_effects if e.kind == "draw"], [1])

    def test_wipe_artifacts_and_creatures(self):
        self.put(self.b, BEAR)
        self.put(self.b, FREEBOOTER)
        for e in ULTIMA.spell_effects:
            self.game.resolve(self.a, e, None)
        self.game.settle()
        self.assertEqual(self.b.battlefield, [])

    def test_hand_exile_returns_when_it_leaves(self):
        self.b.hand[:] = [GROWTH, DOOM, BEAR, ISLAND]
        free = self.game.enter_battlefield(self.a, FREEBOOTER)
        self.game.settle()
        self.assertIn(DOOM, self.b.exile)
        self.assertNotIn(DOOM, self.b.hand)
        self.game.destroy(free)
        self.game.settle()
        self.assertIn(DOOM, self.b.hand)


if __name__ == "__main__":
    unittest.main()

"""Block triggers, bushido, flanking, toxic, untap restrictions, werewolves, Illusions, Spawn mana, bounce lands,
attack restrictions, Fog, conditional tapped lands, "you may" effects and spells that exile themselves."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player, StackItem
from mtgsim.carddb import ALL_CARDS as DB
from tests.test_templates import FOREST, ISLAND, MOUNTAIN, card


class Scripted(HeuristicAI):
    """Attacks and blocks exactly as told."""
    attack = ()
    block = {}

    def choose_attackers(self, game, me, opp):
        return [a for a in self.attack if a in me.battlefield]

    def choose_blocks(self, game, me, opp, attackers):
        return {a: list(bl) for a, bl in self.block.items() if a in attackers}


BEAR = card("Test Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
WALL = card("Test Wall", "{1}{W}", "Creature — Wall", "", 0, 5)
SAMURAI = card("Test Samurai", "{1}{W}", "Creature — Human Samurai", "Bushido 2", 1, 1)
LANCER = card("Test Lancer", "{1}{R}", "Creature — Human Knight", "Flanking", 2, 2)
RAPTOR = card("Test Raptor", "{1}{B}", "Creature — Phyrexian Bird", "Flying\nToxic 2", 1, 1)
STINGER = card("Test Stinger", "{1}{B}", "Creature — Insect",
               "Whenever ~ blocks or becomes blocked, ~ deals 1 damage to that creature.", 1, 1)
BASILISK = card("Test Basilisk", "{2}{G}", "Creature — Basilisk",
                "Whenever ~ blocks or becomes blocked by a creature, destroy that creature at end of combat.", 1, 1)
FREEZER = card("Test Freezer", "{1}{U}", "Creature — Human",
               "Whenever ~ blocks, that creature doesn't untap during its controller's next untap step.", 1, 3)
COLOSSUS = card("Test Colossus", "{9}", "Artifact Creature — Golem", "Trample\n~ doesn't untap during your untap step.", 9, 9)
WEREWOLF = card("Test Rider", "{2}{R}", "Creature — Human Werewolf",
                "At the beginning of each upkeep, if no spells were cast last turn, transform ~.", 3, 3)
ILLUSION = card("Test Illusion", "{U}", "Creature — Illusion",
                "When ~ becomes the target of a spell or ability, sacrifice it.", 3, 3)
DRONE = card("Test Drone", "{1}{C}", "Creature — Eldrazi Drone",
             'When ~ enters, create two 0/1 colorless Eldrazi Spawn creature tokens. They have "Sacrifice this '
             'creature: Add {C}."', 1, 1)
CHANCERY = card("Test Chancery", "", "Land", "~ enters tapped.\nWhen ~ enters, return a land you control to its "
                                             "owner's hand.\n{T}: Add {G}{U}.")
SHARK = card("Test Shark", "{5}{U}", "Creature — Shark", "~ can't attack unless defending player controls an Island.",
             5, 5)
FOG = card("Test Fog", "{G}", "Instant", "Prevent all combat damage that would be dealt this turn.")
FEN = card("Test Fen", "", "Land — Swamp Forest", "~ enters tapped unless you control two or more basic lands.")
SPRINGS = card("Test Springs", "", "Land", "~ enters tapped unless you have two or more opponents.\n{T}: Add {G} or {U}.")
ELDER = card("Test Elder", "{1}{U}", "Creature — Human Monk",
             "Whenever ~ deals combat damage to a player, you may draw a card. If you do, discard a card.", 2, 2)
INSIGHT = card("Test Insight", "{2}{U}", "Sorcery", "Draw two cards. Exile ~.")
BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")


class CombatTriggers(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def fight(self, attackers, blocks=None):
        self.a.ai.attack = attackers
        self.b.ai.block = blocks or {}
        self.game.combat(self.a, self.b)
        self.game.settle()

    def test_templates(self):
        for c in (SAMURAI, LANCER, RAPTOR, STINGER, FREEZER, COLOSSUS, WEREWOLF, ILLUSION, DRONE, CHANCERY, SHARK,
                  FOG, FEN, SPRINGS, ELDER, INSIGHT):
            self.assertEqual(c.unsupported, [], c.name)

    def test_bushido_pumps_when_blocking(self):
        samurai, bear = self.put(self.b, SAMURAI), self.put(self.a, BEAR)
        self.fight([bear], {bear: [samurai]})
        self.assertIn(samurai, self.b.battlefield)      # 3/3 until end of turn
        self.assertNotIn(bear, self.a.battlefield)

    def test_flanking_shrinks_blocker(self):
        lancer, bear = self.put(self.a, LANCER), self.put(self.b, BEAR)
        self.fight([lancer], {lancer: [bear]})
        self.assertNotIn(bear, self.b.battlefield)      # 1/1 against 2 damage
        self.assertIn(lancer, self.a.battlefield)       # took 1

    def test_toxic_gives_poison(self):
        raptor = self.put(self.a, RAPTOR)
        self.fight([raptor])
        self.assertEqual(self.b.counters.get("poison"), 2)
        self.assertEqual(self.b.life, 19)

    def test_that_creature_is_the_other_combatant(self):
        stinger, wall = self.put(self.a, STINGER), self.put(self.b, WALL)
        self.fight([stinger], {stinger: [wall]})
        self.assertEqual(wall.damage, 1 + 1)            # trigger, then combat damage

    def test_destroy_at_end_of_combat(self):
        basilisk, wall = self.put(self.a, BASILISK), self.put(self.b, WALL)
        self.fight([basilisk], {basilisk: [wall]})
        self.assertNotIn(wall, self.b.battlefield)

    def test_freeze_blocked_attacker(self):
        freezer, bear = self.put(self.b, FREEZER), self.put(self.a, BEAR)
        self.fight([bear], {bear: [freezer]})
        self.assertTrue(bear.tapped)
        self.game.take_turn(self.a)
        self.assertTrue(bear.tapped)

    def test_no_untap_self(self):
        colossus = self.put(self.a, COLOSSUS)
        colossus.tapped = True
        self.game.take_turn(self.a)
        self.assertTrue(colossus.tapped)

    @unittest.skipUnless(DB.exists(), "card database not built")
    def test_werewolf_transforms_both_ways(self):
        wolf = self.put(self.a, CardDB().get("Breakneck Rider"))
        self.game.last_turn_spells = {"a": 1}
        self.game.begin_upkeep(self.a)
        self.game.settle()
        self.assertEqual(wolf.card.name, "Breakneck Rider")
        self.game.last_turn_spells = {}
        self.game.begin_upkeep(self.a)
        self.game.settle()
        self.assertEqual(wolf.card.name, "Neck Breaker")
        self.game.last_turn_spells = {"a": 1, "b": 2}
        self.game.begin_upkeep(self.b)
        self.game.settle()
        self.assertEqual(wolf.card.name, "Breakneck Rider")

    def test_illusion_sacrificed_when_targeted(self):
        illusion = self.put(self.b, ILLUSION)
        self.put(self.a, MOUNTAIN)
        self.a.hand.append(BOLT)
        self.assertTrue(self.game.cast(self.a, BOLT, [illusion]))
        self.game.settle()
        self.assertNotIn(illusion, self.b.battlefield)

    def test_spawn_tokens_sacrifice_for_mana(self):
        self.put(self.a, DRONE)
        spawn = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual(len(spawn), 2)
        self.assertEqual(len(self.game.mana_sources(self.a)), 2)    # summoning sick, still usable
        self.assertIsNotNone(self.game.pay(self.a, {"generic": 2}))
        self.assertFalse(any(x.card.is_token for x in self.a.battlefield))

    def test_bounce_land_returns_a_tapped_land(self):
        forest = self.put(self.a, FOREST)
        forest.tapped = True
        chancery = self.put(self.a, CHANCERY)
        self.assertIn(chancery, self.a.battlefield)
        self.assertNotIn(forest, self.a.battlefield)
        self.assertIn(FOREST, self.a.hand)

    def test_attack_restriction(self):
        shark = self.put(self.a, SHARK)
        self.fight([shark])
        self.assertEqual(self.b.life, 20)
        self.put(self.b, ISLAND)
        self.fight([shark])
        self.assertEqual(self.b.life, 15)

    def test_fog_prevents_combat_damage(self):
        bear = self.put(self.a, BEAR)
        self.put(self.b, FOREST)
        stack_fog = StackItem(self.b, list(FOG.spell_effects), [None], card=FOG)
        self.game.stack.append(stack_fog)
        self.game.settle()
        self.fight([bear])
        self.assertEqual(self.b.life, 20)

    def test_conditional_tapped_lands(self):
        self.assertTrue(self.game.enter_battlefield(self.a, SPRINGS).tapped)
        self.assertTrue(self.game.enter_battlefield(self.a, FEN).tapped)
        self.put(self.a, FOREST)
        self.put(self.a, FOREST)
        self.assertFalse(self.game.enter_battlefield(self.a, FEN).tapped)

    def test_may_draw_then_discard(self):
        elder = self.put(self.a, ELDER)
        self.a.hand.extend([ISLAND, ISLAND])
        self.fight([elder])
        self.assertEqual(len(self.a.hand), 2)
        self.assertEqual(len(self.a.graveyard), 1)

    def test_spell_exiles_itself(self):
        for _ in range(3):
            self.put(self.a, ISLAND)
        self.a.hand.append(INSIGHT)
        self.assertTrue(self.game.cast(self.a, INSIGHT))
        self.game.settle()
        self.assertIn(INSIGHT, self.a.exile)
        self.assertNotIn(INSIGHT, self.a.graveyard)


if __name__ == "__main__":
    unittest.main()

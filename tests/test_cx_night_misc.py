"""Wheel-for-seven wording and the Ali from Cairo life floor."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, MOUNTAIN, card

TECHNIQUE = card("Test Technique", "{2}{R}", "Sorcery", "Each player may discard their hand and draw seven cards.")
ALI = card("Test Ali", "{4}", "Artifact Creature", "Damage that would reduce your life total to less than 1 reduces it to 1 instead.",
           power=0, toughness=4)


def _game():
    a = Player("a", [BEAR] * 20, HeuristicAI())
    b = Player("b", [BEAR] * 20, HeuristicAI())
    game = Game(a, b, random.Random(0), log=False)
    a.library = list(a.deck)
    b.library = list(b.deck)
    return game, a, b


class Misc(unittest.TestCase):
    def test_parse(self):
        self.assertEqual((TECHNIQUE.unsupported, ALI.unsupported), ([], []))

    def test_wheel(self):
        game, a, b = _game()
        a.hand, b.hand = [BEAR] * 2, [BEAR] * 5
        game.resolve(a, TECHNIQUE.spell_effects[0], None, None)
        self.assertEqual((len(a.hand), len(b.hand), len(a.graveyard), len(b.graveyard)), (7, 7, 2, 5))

    def test_life_floor(self):
        game, a, b = _game()
        game.enter_battlefield(a, ALI)
        a.life = 3
        game.deal_damage(a, 10, by=b)
        game.state_based_actions()
        self.assertEqual((a.life, a.lost), (1, False))
        game.deal_damage(a, 5, by=b)
        game.state_based_actions()
        self.assertEqual((a.life, a.lost), (1, False))

    def test_other_life_loss_and_the_opponent_are_unaffected(self):
        game, a, b = _game()
        game.enter_battlefield(a, ALI)
        b.life = 3
        game.deal_damage(b, 10, by=a)
        game.state_based_actions()
        self.assertTrue(b.lost)


if __name__ == "__main__":
    unittest.main()


SHAMAN = card("Test Shaman", "{2}{R}", "Creature",
              "Whenever ~ deals combat damage to a player, destroy target artifact or enchantment that player controls.",
              power=3, toughness=2)


class DestroyThatPlayers(unittest.TestCase):
    def test_parses_into_a_combat_damage_trigger(self):
        self.assertEqual(SHAMAN.unsupported, [])
        effect = SHAMAN.triggers[0].effects[0]
        self.assertEqual((SHAMAN.triggers[0].event, effect.kind, effect.target, effect.filter),
                         ("combat_damage_player", "destroy", "artifact_enchantment", "opp"))


BURST = card("Test Burst", "{1}{R}", "Instant",
             "As an additional cost to cast this spell, discard a card at random.\n~ deals 4 damage to any target.")


class DiscardAtRandom(unittest.TestCase):
    def test_parse_and_cast(self):
        self.assertEqual(BURST.unsupported, [])
        self.assertEqual(BURST.extra_discard, 1)
        self.assertTrue(BURST.advanced_rules.get("discard_random"))

    def test_casting_discards_one_card_from_hand(self):
        game, a, b = _game()
        game.turn, game.step = 1, "main1"
        for _ in range(2):
            game.enter_battlefield(a, MOUNTAIN)
        a.hand = [BURST, BEAR, BEAR]
        before = len(a.hand)
        self.assertTrue(game.cast(a, BURST, [b]))
        self.assertEqual(len(a.hand), before - 2)       # the spell and one random card left the hand
        self.assertGreaterEqual(len(a.graveyard), 1)


DECOMPOSE = card("Test Decompose", "{B}", "Sorcery", "Exile up to three target cards from a single graveyard.")
DWELL = card("Test Dwell", "{U}", "Sorcery", "Target player shuffles up to four target cards from their graveyard into their library.")


class GraveyardPicks(unittest.TestCase):
    def test_parse(self):
        self.assertEqual((DECOMPOSE.unsupported, DWELL.unsupported), ([], []))

    def test_exile_up_to_three_prefers_creatures(self):
        game, a, b = _game()
        b.graveyard = [MOUNTAIN, MOUNTAIN, BEAR, BEAR, MOUNTAIN]
        game.resolve(a, DECOMPOSE.spell_effects[0], None, None)
        self.assertEqual(([c.name for c in b.exile].count(BEAR.name), len(b.exile), len(b.graveyard)), (2, 3, 2))

    def test_shuffle_up_to_four_into_library(self):
        game, a, b = _game()
        a.graveyard = [BEAR] * 6
        n = len(a.library)
        game.resolve(a, DWELL.spell_effects[0], a, None)
        self.assertEqual((len(a.graveyard), len(a.library)), (2, n + 4))


DORAN = card("Test Doran", "{1}{G}", "Enchantment",
             "Each creature you control assigns combat damage equal to its toughness rather than its power.")
WALL = card("Test Wall", "{1}", "Creature", "Defender", power=0, toughness=5)


class ToughnessDamage(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(DORAN.unsupported, [])

    def test_only_my_creatures_assign_toughness(self):
        from mtgsim.cx_night_aura import dmg_stat
        game, a, b = _game()
        game.enter_battlefield(a, DORAN)
        game.enter_battlefield(a, WALL)
        game.enter_battlefield(b, WALL)
        mine = next(x for x in a.battlefield if x.card.name == WALL.name)
        theirs = b.battlefield[-1]
        self.assertEqual((dmg_stat(game, mine), dmg_stat(game, theirs)), (5, 0))

    def test_combat_damage_uses_toughness(self):
        game, a, b = _game()
        game.enter_battlefield(a, DORAN)
        game.enter_battlefield(a, ROCK)
        rock = a.battlefield[-1]
        b.life = 20
        game.attack_targets = {rock: b}
        game.combat_damage(a, b, [rock], {}, lambda c: True)
        self.assertEqual(b.life, 15)


ROCK = card("Test Rock", "{1}", "Creature", "", power=0, toughness=5)


DRAKE = card("Test Drake", "{3}{U}", "Creature",
             "When ~ enters, shuffle the cards from your hand into your library, then draw that many cards.", power=2, toughness=2)
ARJUN = card("Test Arjun", "{3}{U}", "Creature",
             "Whenever you cast a spell, put the cards in your hand on the bottom of your library in any order, then draw that many cards.",
             power=2, toughness=2)
HOT = card("Test Springs", "{1}{W}", "Enchantment — Aura", "Enchant land you control\nEnchanted land has \"{T}: Add {W}.\"")


class HandCycle(unittest.TestCase):
    def test_parse(self):
        self.assertEqual((DRAKE.unsupported, ARJUN.unsupported, HOT.unsupported), ([], [], []))
        self.assertEqual(HOT.aura, "land you control")

    def test_hand_is_replaced_by_as_many_cards(self):
        game, a, b = _game()
        a.hand = [BEAR] * 3
        n = len(a.library)
        game.resolve(a, DRAKE.triggers[0].effects[0], None, None)
        self.assertEqual((len(a.hand), len(a.library)), (3, n))

    def test_bottom_variant(self):
        game, a, b = _game()
        a.hand = [MOUNTAIN, BEAR]
        n = len(a.library)
        game.resolve(a, ARJUN.triggers[0].effects[0], None, None)
        self.assertEqual((len(a.hand), len(a.library)), (2, n))

    def test_aura_goes_on_my_land_only(self):
        from mtgsim import auras
        game, a, b = _game()
        game.enter_battlefield(a, MOUNTAIN)
        game.enter_battlefield(b, MOUNTAIN)
        self.assertEqual([x.controller for x in auras.hosts(game, a, HOT)], [a])


MARAUDER = card("Test Marauder", "{2}{B}", "Creature", "When ~ enters, each player sacrifices a nontoken creature.",
                power=3, toughness=2)
IMP = card("Test Imp", "{2}{B}", "Creature", "Flying\nWhen ~ dies, target opponent puts a card from their hand on top of their library.",
           power=1, toughness=1)


MANEUVER = card("Test Maneuver", "{1}{W}", "Instant", "Target player sacrifices an attacking creature.")
FOGWALKER = card("Test Fogwalker", "{1}{U}", "Creature", "Whenever ~ attacks, target creature an opponent controls doesn't untap during its controller's next untap step.", power=1, toughness=1)


class SmallEdicts(unittest.TestCase):
    def test_parse(self):
        self.assertEqual((MARAUDER.unsupported, IMP.unsupported), ([], []))

    def test_each_player_sacrifices_a_nontoken(self):
        game, a, b = _game()
        game.enter_battlefield(a, BEAR)
        game.enter_battlefield(b, BEAR)
        game.resolve(a, MARAUDER.triggers[0].effects[0], None, None)
        self.assertEqual((len(a.creatures), len(b.creatures)), (0, 0))

    def test_opponent_returns_a_card_to_the_top(self):
        game, a, b = _game()
        b.hand = [MOUNTAIN, BEAR]
        n = len(b.library)
        game.resolve(a, IMP.triggers[0].effects[0], b, None)
        self.assertEqual((len(b.hand), len(b.library)), (1, n + 1))
        self.assertEqual(b.library[-1].name, MOUNTAIN.name)


class AttackingEdictAndFreeze(unittest.TestCase):
    def test_parse(self):
        self.assertEqual((MANEUVER.unsupported, FOGWALKER.unsupported), ([], []))

    def test_sacrifices_an_attacker(self):
        game, a, b = _game()
        c = game.enter_battlefield(b, BEAR)
        game.attackers = [c]
        game.resolve(a, MANEUVER.spell_effects[0], b, None)
        self.assertEqual(len(b.creatures), 0)

    def test_untouched_when_not_attacking(self):
        game, a, b = _game()
        game.enter_battlefield(b, BEAR)
        game.attackers = []
        game.resolve(a, MANEUVER.spell_effects[0], b, None)
        self.assertEqual(len(b.creatures), 1)

    def test_freeze(self):
        game, a, b = _game()
        c = game.enter_battlefield(b, BEAR)
        game.resolve(a, FOGWALKER.triggers[0].effects[0], c, None)
        self.assertEqual(c.skip_untap, 1)

"""Static-condition batch: capitalised 'Protection from X and from Y' lines."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import ISLAND, MOUNTAIN, card


class ProtectionAndFrom(unittest.TestCase):
    def test_capitalised_double_protection(self):
        c = card("Test Crusader", "{3}", "Creature — Human", "Protection from black and from red", 2, 2)
        self.assertEqual(c.unsupported, [])
        self.assertEqual(set(c.keywords), {"protection from black", "protection from red"})


WHISKER = card("Test Whisker", "{1}{U}", "Creature — Human",
               "Threshold — As long as there are seven or more cards in your graveyard, creatures your opponents control get -1/-0.", 1, 1)
BEAR = card("Test Bear", "{2}", "Creature — Bear", "", 2, 2)


class OpponentThresholdDebuff(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 10, HeuristicAI())
        self.b = Player("b", [ISLAND] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.whisker = self._put(self.a, WHISKER)
        self.mine = self._put(self.a, BEAR)
        self.theirs = self._put(self.b, BEAR)

    def _put(self, player, c):
        p = Permanent(c, player)
        player.battlefield.append(p)
        return p

    def test_parses(self):
        self.assertEqual(WHISKER.unsupported, [])

    def test_threshold_gates_and_scope(self):
        self.a.graveyard[:] = [ISLAND] * 6
        self.assertEqual(self.theirs.power, 2)
        self.a.graveyard.append(ISLAND)
        self.assertEqual(self.theirs.power, 1)
        self.assertEqual(self.theirs.toughness, 2)
        self.assertEqual(self.mine.power, 2)       # own creatures are untouched
        self.assertEqual(self.whisker.power, 1)


FIRE = card("Test Fire", "{2}{R}", "Instant", "~ deals 3 damage to any target. If at least three red mana was spent to cast ~, it deals 4 damage instead.")
DRAW = card("Test Insight", "{2}{U}", "Sorcery", "Draw a card. If at least three blue mana was spent to cast ~, draw two cards instead.")
PEEK = card("Test Peek", "{1}{G}", "Instant", "~ deals 1 damage to any target. If four or more mana was spent to cast ~, it deals 2 damage instead.")
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")


class ManaSpentColour(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 10, HeuristicAI())
        self.b = Player("b", [ISLAND] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"

    def lands(self, *cards):
        for c in cards:
            p = Permanent(c, self.a)
            self.a.battlefield.append(p)

    def fire_at_face(self, spell, *lands):
        self.lands(*lands)
        self.b.life = 20
        self.a.hand[:] = [spell]
        self.assertTrue(self.game.cast(self.a, spell, [self.b]))
        self.game.settle()
        return 20 - self.b.life

    def test_templates(self):
        for c in (FIRE, DRAW, PEEK):
            self.assertEqual(c.unsupported, [], c.name)

    def test_three_red_mana_upgrades(self):
        self.assertEqual(self.fire_at_face(FIRE, MOUNTAIN, MOUNTAIN, MOUNTAIN), 4)

    def test_two_red_mana_does_not(self):
        self.assertEqual(self.fire_at_face(FIRE, MOUNTAIN, MOUNTAIN, ISLAND), 3)

    def test_total_mana_count(self):
        self.assertEqual(self.fire_at_face(PEEK, FOREST, FOREST), 1)

    def test_total_mana_count_met(self):
        peek4 = card("Test Peek Four", "{3}{G}", "Instant", PEEK.oracle_text if hasattr(PEEK, "oracle_text") else
                     "~ deals 1 damage to any target. If four or more mana was spent to cast ~, it deals 2 damage instead.")
        self.assertEqual(self.fire_at_face(peek4, FOREST, FOREST, FOREST, FOREST), 2)


PALADIN = card("Test Paladin", "{2}{R}", "Creature — Human Knight",
               "Adamant — If at least three red mana was spent to cast this spell, this creature enters with a +1/+1 counter on it.", 2, 2)


class AdamantEntry(unittest.TestCase):
    def cast_with(self, *lands):
        a = Player("a", [ISLAND] * 10, HeuristicAI())
        b = Player("b", [ISLAND] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 1, "main1"
        for c in lands:
            a.battlefield.append(Permanent(c, a))
        a.hand[:] = [PALADIN]
        self_ok = game.cast(a, PALADIN, [])
        game.settle()
        self.assertTrue(self_ok)
        return next(x for x in a.battlefield if x.card is PALADIN or x.card.name == PALADIN.name)

    def test_templates(self):
        self.assertEqual(PALADIN.unsupported, [])

    def test_adamant(self):
        self.assertEqual(self.cast_with(MOUNTAIN, MOUNTAIN, MOUNTAIN).counters.get("+1/+1", 0), 1)
        self.assertEqual(self.cast_with(MOUNTAIN, MOUNTAIN, ISLAND).counters.get("+1/+1", 0), 0)


SANDSWIMMER = card("Test Sandswimmer", "{1}{R}", "Creature — Viashino",
                   "{R}: Flip a coin. If you win the flip, return ~ to its owner's hand. If you lose the flip, sacrifice ~.", 2, 1)


class _Coin(random.Random):
    """The game's seeded RNG with the next coin forced."""
    def __init__(self, heads):
        super().__init__(0)
        self.heads = heads

    def random(self):
        return 0.0 if self.heads else 0.99


class CoinFlipBothSides(unittest.TestCase):
    def activate(self, win):
        a = Player("a", [ISLAND] * 10, HeuristicAI())
        b = Player("b", [ISLAND] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 1, "main1"
        game.rng = _Coin(win)
        a.battlefield.append(Permanent(MOUNTAIN, a))
        perm = Permanent(SANDSWIMMER, a)
        perm.sick = False
        a.battlefield.append(perm)
        self.assertTrue(game.activate_ability(a, perm, 0))
        game.settle()
        return a, perm

    def test_template(self):
        self.assertEqual(SANDSWIMMER.unsupported, [])

    def test_win_bounces(self):
        a, perm = self.activate(True)
        self.assertNotIn(perm, a.battlefield)
        self.assertIn(SANDSWIMMER, a.hand)

    def test_lose_sacrifices(self):
        a, perm = self.activate(False)
        self.assertNotIn(perm, a.battlefield)
        self.assertNotIn(SANDSWIMMER, a.hand)
        self.assertEqual([c.name for c in a.graveyard], [SANDSWIMMER.name])


MINING = card("Test Mining", "{2}{R}", "Enchantment", "You can't play lands.")
WORMS = card("Test Dispute", "{2}{R}", "Enchantment", "Players can't play lands.")
QUAKE = card("Test Wound", "{1}{R}", "Sorcery", "Target player can't play lands this turn.")


class CantPlayLands(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 10, HeuristicAI())
        self.b = Player("b", [ISLAND] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"

    def test_templates(self):
        for c in (MINING, WORMS, QUAKE):
            self.assertEqual(c.unsupported, [], c.name)

    def test_own_lock_only_binds_its_controller(self):
        self.a.battlefield.append(Permanent(MINING, self.a))
        self.assertTrue(self.a.land_played)
        self.assertFalse(self.b.land_played)

    def test_players_lock_binds_everyone(self):
        self.a.battlefield.append(Permanent(WORMS, self.a))
        self.assertTrue(self.a.land_played)
        self.assertTrue(self.b.land_played)

    def test_target_player_this_turn_only(self):
        for land in (MOUNTAIN, MOUNTAIN):
            self.a.battlefield.append(Permanent(land, self.a))
        self.a.hand[:] = [QUAKE]
        self.assertTrue(self.game.cast(self.a, QUAKE, [self.b]))
        self.game.settle()
        self.assertTrue(self.b.land_played)
        self.assertFalse(self.a.land_played)
        self.game.turn += 1
        self.assertFalse(self.b.land_played)


RESEARCH = card("Test Research", "{1}{G}", "Enchantment",
                "At the beginning of your end step, if a card left your graveyard this turn, draw a card.")


class GraveyardDeparture(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 10, HeuristicAI())
        self.b = Player("b", [ISLAND] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.a.library = [ISLAND] * 5
        self.a.battlefield.append(Permanent(RESEARCH, self.a))
        self.a.graveyard.append(ISLAND)

    def end_step_draw(self):
        before = len(self.a.hand)
        self.game.fire(self.a, "end_step")
        self.game.flush_triggers()
        while self.game.stack:
            self.game.resolve_top()
        return len(self.a.hand) - before

    def test_template(self):
        self.assertEqual(RESEARCH.unsupported, [])

    def test_no_departure_no_draw(self):
        self.assertEqual(self.end_step_draw(), 0)

    def test_departure_draws(self):
        self.a.graveyard.remove(ISLAND)
        self.assertEqual(self.end_step_draw(), 1)

    def test_counter_resets_on_a_new_turn(self):
        self.a.graveyard.remove(ISLAND)
        self.a.graveyard.left_turn = 0          # what turn start does
        self.assertEqual(self.end_step_draw(), 0)


WHELP = card("Test Whelp", "{2}{R}{R}", "Creature — Dragon",
             "Flying\n{R}: ~ gets +1/+0 until end of turn. If this ability has been activated four or more times this turn, "
             "sacrifice ~ at the beginning of the next end step.", 2, 3)


class ActivatedManyTimes(unittest.TestCase):
    def run_whelp(self, times):
        a = Player("a", [ISLAND] * 10, HeuristicAI())
        b = Player("b", [ISLAND] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 1, "main1"
        for _ in range(4):
            a.battlefield.append(Permanent(MOUNTAIN, a))
        whelp = Permanent(WHELP, a)
        whelp.sick = False
        a.battlefield.append(whelp)
        for _ in range(times):
            self.assertTrue(game.activate_ability(a, whelp, 0))
            game.settle()
        game.begin_end_step(a)
        game.flush_triggers()
        while game.stack:
            game.resolve_top()
        return a, whelp

    def test_template(self):
        self.assertEqual(WHELP.unsupported, [])

    def test_three_activations_survive(self):
        a, whelp = self.run_whelp(3)
        self.assertIn(whelp, a.battlefield)
        self.assertEqual(whelp.power, 5)

    def test_four_activations_sacrifice_at_end_step(self):
        a, whelp = self.run_whelp(4)
        self.assertNotIn(whelp, a.battlefield)


VERDICT = card("Test Verdict", "{2}{R}{R}", "Sorcery", "Flip a coin. If you win the flip, destroy all creatures with power 2 or less. "
               "If you lose the flip, destroy all creatures with power 3 or greater.")
OGRE = card("Test Ogre", "{3}", "Creature — Ogre", "", 3, 3)


class CoinSpellBothSides(unittest.TestCase):
    def cast(self, win):
        a = Player("a", [ISLAND] * 10, HeuristicAI())
        b = Player("b", [ISLAND] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 1, "main1"
        game.rng = _Coin(win)
        for _ in range(4):
            a.battlefield.append(Permanent(MOUNTAIN, a))
        small = Permanent(BEAR, b)
        big = Permanent(OGRE, b)
        b.battlefield.extend([small, big])
        a.hand[:] = [VERDICT]
        self.assertTrue(game.cast(a, VERDICT, []))
        game.settle()
        return small in b.battlefield, big in b.battlefield

    def test_win_destroys_small(self):
        self.assertEqual(self.cast(True), (False, True))

    def test_lose_destroys_big(self):
        self.assertEqual(self.cast(False), (True, False))


if __name__ == "__main__":
    unittest.main()

"""A batch of cheap single-line templates: amass, Mutagen, team keywords, discounts, conditional statics."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card


class CheapLines(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, who=None):
        p = Permanent(c, who or self.a)
        p.sick = False
        p.controller.battlefield.append(p)
        return p

    def test_parse_clean(self):
        for c in (card("Amasser", "{1}{B}", "Sorcery", "Amass Orcs 2.\nYou draw a card and lose 1 life."),
                  card("Crystal", "{3}", "Artifact", "Creatures you control have haste.\nRed spells you cast cost {1} less to cast."),
                  card("Guard", "{1}{W}", "Creature — Human", "During your turn, ~ has first strike.", "2", "2"),
                  card("Muse", "{1}{B}", "Instant", "Target opponent sacrifices a creature of their choice."),
                  card("Grow", "{1}{G}", "Creature — Elf", "~ enters with a +1/+1 counter on it if a creature died this turn.", "2", "2")):
            self.assertEqual(c.unsupported, [], c.name)

    def test_amass_reuses_army(self):
        spell = card("Amasser", "{R}", "Sorcery", "Amass Orcs 2.")
        for _ in range(2):
            self.perm(MOUNTAIN)
            self.a.hand.append(spell)
            self.assertTrue(self.game.cast(self.a, spell, []))
            self.game.settle()
        armies = [x for x in self.a.battlefield if "Army" in x.card.subtypes]
        self.assertEqual(len(armies), 1)
        self.assertEqual(armies[0].p1, 4)

    def test_team_haste_and_discount(self):
        crystal = card("Crystal", "{3}", "Artifact", "Creatures you control have haste.\nRed spells you cast cost {1} less to cast.")
        self.perm(crystal)
        bear = self.perm(BEAR)
        self.assertTrue(bear.has("haste"))
        bolt = card("Bolt", "{1}{R}", "Instant", "~ deals 3 damage to any target.")
        self.assertEqual(self.game.cost_of(self.a, bolt).get("generic", 0), 0)
        other = card("Cancel", "{1}{U}", "Instant", "Draw a card.")
        self.assertEqual(self.game.cost_of(self.a, other).get("generic", 0), 1)

    def test_first_strike_only_on_my_turn(self):
        guard = self.perm(card("Guard", "{1}{W}", "Creature — Human", "During your turn, ~ has first strike.", "2", "2"))
        self.a.my_turn = True
        self.assertTrue(guard.has("first strike"))
        self.a.my_turn = False
        self.assertFalse(guard.has("first strike"))

    def test_threshold_pump(self):
        t = self.perm(card("Hound", "{1}{R}", "Creature — Dog", "Threshold — ~ gets +2/+1 as long as there are seven or more cards in your graveyard.", "2", "2"))
        base = t.power
        self.a.graveyard.extend([MOUNTAIN] * 7)
        self.assertEqual(t.power, base + 2)

    def test_voice_blocks_opponent_spells(self):
        self.perm(card("Voice", "{1}{W}", "Creature — Human", "Your opponents can't cast spells during your turn.", "2", "2"))
        self.b.hand.append(card("Zap", "{R}", "Instant", "~ deals 1 damage to any target."))
        self.perm(MOUNTAIN, self.b)
        self.assertFalse(self.game.can_cast_now(self.b, self.b.hand[0]))

    def test_enters_with_counter_if_creature_died(self):
        grow = card("Grow", "{G}", "Creature — Elf", "~ enters with a +1/+1 counter on it if a creature died this turn.", "2", "2")
        plain = self.game.enter_battlefield(self.a, grow)
        self.assertEqual(plain.p1, 0)
        self.game.creature_died_turn = True
        bigger = self.game.enter_battlefield(self.a, grow)
        self.assertEqual(bigger.p1, 1)

    def test_mutagen_token_has_sacrifice_ability(self):
        from mtgsim.cards import make_token
        tok = make_token("", 0, 0, kind="mutagen")
        self.assertEqual(len(tok.activated), 1)
        self.assertEqual(tok.activated[0].cost.get("generic"), 1)


if __name__ == "__main__":
    unittest.main()

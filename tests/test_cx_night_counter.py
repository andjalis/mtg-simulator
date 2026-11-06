"""Counterspell taxes: type filters and "{1} for each ..." scaling."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem
from mtgsim.engine.kinds.other import counter
from tests.test_templates import BEAR, card

REBUFF = card("Test Rebuff", "{1}{U}", "Instant", "Counter target nonartifact spell unless its controller pays {2}.")
REJECT = card("Test Reject", "{1}{U}", "Instant",
              "Counter target creature or planeswalker spell unless its controller pays {3}.")
WINDS = card("Test Winds", "{U}", "Instant", "Counter target spell unless its controller pays {1} for each card in your graveyard.")
ROCK = card("Test Rock", "{1}", "Artifact", "")


class CounterTaxes(unittest.TestCase):
    def test_filters_parse(self):
        self.assertEqual((REBUFF.unsupported, REBUFF.spell_effects[0].filter, REBUFF.spell_effects[0].amount),
                         ([], "nonartifact", 2))
        self.assertEqual((REJECT.unsupported, REJECT.spell_effects[0].filter),
                         ([], "types:Creature,Planeswalker"))
        self.assertEqual(WINDS.unsupported, [])
        self.assertEqual(WINDS.spell_effects[0].data, {"per": "graveyard", "mult": 1, "base": 0})

    def _game(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        game.turn, game.step = 1, "main1"
        return game, a, b

    def test_can_counter_respects_the_filters(self):
        game, a, b = self._game()
        bear = StackItem(card=BEAR, controller=b, effects=[], targets=[])
        rock = StackItem(card=ROCK, controller=b, effects=[], targets=[])
        game.stack.extend([bear, rock])
        self.assertTrue(game.can_counter(REBUFF.spell_effects[0], bear, by=a))
        self.assertFalse(game.can_counter(REBUFF.spell_effects[0], rock, by=a))
        self.assertTrue(game.can_counter(REJECT.spell_effects[0], bear, by=a))
        self.assertFalse(game.can_counter(REJECT.spell_effects[0], rock, by=a))

    def test_a_zero_tax_keeps_the_spell(self):
        game, a, b = self._game()
        spell = StackItem(card=BEAR, controller=b, effects=[], targets=[])
        game.stack.append(spell)
        counter(game, a, WINDS.spell_effects[0], spell, None)        # empty graveyard: they pay {0} and keep the spell
        self.assertIn(spell, game.stack)

    def test_more_counts_parse(self):
        for text, per, mult, base in (
                ("Counter target spell unless its controller pays {X}, where X is its mana value.", "mv", 1, 0),
                ("Counter target spell unless its controller pays {2} for each Wizard on the battlefield.",
                 "all:Wizard", 2, 0),
                ("Counter target spell unless its controller pays {2} plus an additional {1} for each Faerie you control.",
                 "mine:Faerie", 1, 2),
                ("Counter target spell unless its controller pays {1} for each blue permanent you control.",
                 "color:U", 1, 0)):
            c = card("Test Tax", "{U}", "Instant", text)
            self.assertEqual((c.unsupported, c.spell_effects[0].data), ([], {"per": per, "mult": mult, "base": base}), text)

    def test_count_per_new_kinds(self):
        from mtgsim.cx_night_counter import count_per
        game, a, b = self._game()
        wiz = card("Test Wizard", "{U}", "Creature — Human Wizard", "", power="1", toughness="1")
        a.battlefield.extend([Permanent(wiz, a), Permanent(wiz, a)])
        b.battlefield.append(Permanent(wiz, b))
        spell = StackItem(card=card("Test Five", "{4}{U}", "Sorcery", ""), controller=b, effects=[], targets=[])
        self.assertEqual((count_per(game, a, "all:Wizard"), count_per(game, a, "mine:Wizard"),
                          count_per(game, a, "color:U"), count_per(game, a, "mv", spell)), (3, 2, 2, 5))

    def test_count_per(self):
        from mtgsim.cx_night_counter import count_per
        game, a, b = self._game()
        a.graveyard.extend([BEAR, BEAR])
        a.hand.append(BEAR)
        a.battlefield.extend([Permanent(BEAR, a), Permanent(ROCK, a)])
        self.assertEqual([count_per(game, a, k) for k in ("graveyard", "hand", "creatures", "artifacts")],
                         [2, 1, 1, 1])


if __name__ == "__main__":
    unittest.main()


TURN_ASIDE = card("Test Aside", "{U}", "Instant", "Counter target spell that targets a permanent you control.")


class TargetsMine(unittest.TestCase):
    def test_only_spells_aimed_at_my_permanents(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        game.turn, game.step = 1, "main1"
        self.assertEqual(TURN_ASIDE.unsupported, [])
        game.enter_battlefield(a, BEAR)
        game.enter_battlefield(b, BEAR)
        mine, theirs = a.battlefield[-1], b.battlefield[-1]
        aimed = StackItem(card=BEAR, controller=b, effects=[], targets=[mine])
        elsewhere = StackItem(card=BEAR, controller=b, effects=[], targets=[theirs])
        untargeted = StackItem(card=BEAR, controller=b, effects=[], targets=[])
        game.stack.extend([aimed, elsewhere, untargeted])
        eff = TURN_ASIDE.spell_effects[0]
        self.assertEqual([game.can_counter(eff, i, by=a) for i in (aimed, elsewhere, untargeted)],
                         [True, False, False])

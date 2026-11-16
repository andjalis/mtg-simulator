"""#625 slice 4: "as though it/they had flash" for filtered spell groups, this turn, and ~ under a condition."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player
from tests.test_templates import BEAR, card

SPIRIT_LORD = card("Test Lord", "{2}", "Creature — Spirit", "You may cast Spirit spells as though they had flash.",
                   power="1", toughness="1")
SPIRIT = card("Test Spirit", "{1}", "Creature — Spirit", "", power="1", toughness="1")
GOLEM = card("Test Golem", "{1}", "Artifact Creature — Golem", "", power="1", toughness="1")
MULTI = card("Test Multi", "{2}", "Artifact", "You may cast artifact, creature, and enchantment spells as though they had flash.")
CANYONS = card("Test Canyons", "", "Land", "{2}, {T}: You may cast creature spells this turn as though they had flash.")
FAERIE_AURA = card("Test Spinners", "{1}{U}", "Sorcery", "You may cast ~ as though it had flash if you control a Faerie.\nDraw a card.")
GROVE = card("Test Grip", "{1}", "Sorcery", "Ferocious — If you control a creature with power 4 or greater, you may cast ~ "
             "as though it had flash. (You may cast it any time you could cast an instant.)\nDraw a card.")
FAERIE = card("Test Faerie", "{1}", "Creature — Faerie", "", power="1", toughness="1")
BIG = card("Test Big", "{4}", "Creature — Beast", "", power="4", toughness="4")


def setup():
    a = Player("a", [BEAR] * 10, HeuristicAI())
    b = Player("b", [BEAR] * 10, HeuristicAI())
    game = Game(a, b, random.Random(0), log=False)
    game.turn, game.step = 1, "combat"
    game.active_idx = 1                                   # not a's turn
    for _ in range(3):
        a.battlefield.append(Permanent(card("Test Island", "", "Basic Land — Island", ""), a))
    return game, a


class FlashPerm(unittest.TestCase):
    def test_parse(self):
        for c in (SPIRIT_LORD, MULTI, CANYONS, FAERIE_AURA, GROVE):
            self.assertEqual(c.unsupported, [], c.name)

    def test_filtered_static(self):
        game, a = setup()
        a.hand += [SPIRIT, GOLEM]
        self.assertFalse(game.can_cast_now(a, SPIRIT))
        a.battlefield.append(Permanent(SPIRIT_LORD, a))
        self.assertTrue(game.can_cast_now(a, SPIRIT))
        self.assertFalse(game.can_cast_now(a, GOLEM))           # not a Spirit

    def test_artifact_creature_enchantment_list(self):
        game, a = setup()
        a.hand.append(GOLEM)
        a.battlefield.append(Permanent(MULTI, a))
        self.assertTrue(game.can_cast_now(a, GOLEM))

    def test_gated_self(self):
        game, a = setup()
        a.hand.append(FAERIE_AURA)
        self.assertFalse(game.can_cast_now(a, FAERIE_AURA))
        a.battlefield.append(Permanent(FAERIE, a))
        self.assertTrue(game.can_cast_now(a, FAERIE_AURA))

    def test_gated_self_with_ability_word(self):
        game, a = setup()
        a.hand.append(GROVE)
        self.assertFalse(game.can_cast_now(a, GROVE))
        a.battlefield.append(Permanent(BIG, a))
        self.assertTrue(game.can_cast_now(a, GROVE))

    def test_this_turn_effect(self):
        from mtgsim.engine import StackItem
        game, a = setup()
        spell = card("Test Rush", "{U}", "Instant", "You may cast creature spells this turn as though they had flash.")
        self.assertEqual(spell.unsupported, [])
        a.hand += [SPIRIT, GROVE]
        self.assertFalse(game.can_cast_now(a, SPIRIT))
        game.stack.append(StackItem(a, list(spell.spell_effects), [None], card=spell, name=spell.name))
        game.resolve_top()
        self.assertTrue(game.can_cast_now(a, SPIRIT))
        self.assertFalse(game.can_cast_now(a, GROVE))           # a sorcery: creature spells only
        game.turn += 1
        self.assertFalse(game.can_cast_now(a, SPIRIT))            # only this turn

    def test_refusals(self):
        for line in ("You may cast Aura spells with enchant creature as though they had flash.",
                     "You may cast ~ as though it had flash if it targets a commander."):
            c = card("Test Refuse", "{1}", "Enchantment", line)
            self.assertTrue(c.unsupported, line)


if __name__ == "__main__":
    unittest.main()

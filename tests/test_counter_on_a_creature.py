"""#360: "put a counter on a creature/planeswalker you control" is a choice on resolution, not a target: the spell
can be cast without one (its other effects still happen), and that choice doesn't keep the spell from fizzling."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")

SETTLE = card("Test Settle", "{2}{B}{B}", "Sorcery",
              "Exile target creature. Put two loyalty counters on a planeswalker you control.")
CURDLE = card("Test Curdle", "{3}{B}", "Sorcery",
              "Destroy target creature. Put a menace counter on a creature you control.")
GROWTH = card("Test Growth", "{1}{B}", "Sorcery", "Put a +1/+1 counter on target creature.")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [SWAMP] * 10
    for _ in range(5):
        g.enter_battlefield(a, SWAMP).sick = False
    foe = g.enter_battlefield(b, card("Foe", "{3}", "Creature — Ogre", "", 4, 4))
    g.settle()
    return g, a, b, foe


class CounterOnAChosenPermanent(unittest.TestCase):
    def test_parse(self):
        place = SETTLE.spell_effects[1]
        self.assertTrue(place.data.get("optional_target") and place.data.get("chosen"))
        self.assertFalse(GROWTH.spell_effects[0].data.get("chosen"))        # "target creature" stays a target

    def test_castable_without_a_planeswalker(self):
        g, a, b, foe = game()
        a.hand.append(SETTLE)
        self.assertTrue(g.cast(a, SETTLE, targets=[foe, None]))
        g.settle()
        self.assertNotIn(foe, b.battlefield)

    def test_ai_casts_it_without_a_creature(self):
        g, a, b, foe = game()
        a.hand.append(CURDLE)
        g.main_phase(a)
        g.settle()
        self.assertNotIn(foe, b.battlefield)

    def test_counter_still_placed_when_there_is_one(self):
        g, a, b, foe = game()
        mine = g.enter_battlefield(a, card("Mine", "{1}", "Creature — Human", "", 2, 2))
        g.settle()
        a.hand.append(CURDLE)
        g.main_phase(a)
        g.settle()
        self.assertNotIn(foe, b.battlefield)
        self.assertEqual(mine.counters.get("menace"), 1)

    def test_fizzles_when_its_only_target_is_gone(self):
        g, a, b, foe = game()
        mine = g.enter_battlefield(a, card("Mine", "{1}", "Creature — Human", "", 2, 2))
        g.settle()
        from mtgsim.engine.state import StackItem
        item = StackItem(a, list(CURDLE.spell_effects), [foe, mine], card=CURDLE)
        b.battlefield.remove(foe)              # the target left before resolution
        g.stack.append(item)
        g.settle()
        self.assertFalse(mine.counters.get("menace"))

    def test_a_choice_triggers_no_heroic_or_illusion(self):
        # sim-review on #367: the chosen slot is not a target, so "becomes the target" abilities don't trigger
        hero = card("Test Hero", "{1}{W}", "Creature — Human",
                    "Heroic — Whenever you cast a spell that targets this creature, you gain 3 life.", 2, 2)
        illusion = card("Test Illusion", "{1}{U}", "Creature — Illusion",
                        "When this creature becomes the target of a spell or ability, sacrifice it.", 2, 2)
        for creature in (hero, illusion):
            g, a, b, foe = game()
            mine = g.enter_battlefield(a, creature)
            g.settle()
            life = a.life
            a.hand.append(CURDLE)
            self.assertTrue(g.cast(a, CURDLE, targets=[foe, mine]))
            g.settle()
            self.assertIn(mine, a.battlefield)
            self.assertEqual(mine.counters.get("menace"), 1)
            self.assertEqual(a.life, life)

    def test_each_listed_types_are_not_single_targets(self):
        # Blech, Loafing Pest was read as a Pest group without "you control" plus one *target* Bat, Insect and Snake;
        # without an article the object list is a group, never "target <noun>"
        from mtgsim.cards.parse import _parse_effects
        effects, _ = _parse_effects("Put a +1/+1 counter on each Pest, Bat, Insect, Snake, and Spider you control.")
        self.assertFalse(any(e.target == "permanent" for e in effects))


if __name__ == "__main__":
    unittest.main()

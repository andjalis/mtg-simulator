"""#643 slice 4: "can't be the target(s) of ... this turn" (target_bans.target_ban_temp)."""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent, StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, SHOCK, card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
VINES = card("Test Vines", "{G}", "Instant", "Target creature can't be the target of spells or abilities your "
             "opponents control this turn.")
DISPLAY = card("Test Display", "{1}{G}", "Instant", "Permanents you control can't be the targets of blue or black "
               "spells your opponents control this turn.")
DOOM = card("Test Doom Blade", "{1}{B}", "Instant", "Destroy target creature.")
GROWTH = card("Test Growth", "{G}", "Instant", "Target creature gets +3/+3 until end of turn.")


class Parsing(unittest.TestCase):
    def test_positives(self):
        effects, bad = _parse_effects("Target creature can't be the target of spells or abilities your opponents "
                                      "control this turn.")
        self.assertEqual(bad, [])
        self.assertEqual((effects[0].kind, effects[0].target), ("target_ban_temp", "creature"))
        self.assertEqual(DISPLAY.spell_effects[0].data["group"], "permanents")
        self.assertEqual(DISPLAY.spell_effects[0].data["clauses"][0]["colors"], ("U", "B"))

    def test_refusals(self):
        for text in ("Target creature can't be the target of purple spells this turn.",
                     "Creatures your opponents control can't be the targets of spells this turn.",
                     "Target creature can't be the target of spells or abilities your opponents control."):
            effects, bad = _parse_effects(text)
            self.assertTrue(bad, text)


class Engine(Base):
    def cast(self, c, targets, by):
        item = StackItem(by, list(c.spell_effects), list(targets), card=c, name=c.name)
        self.game.stack.append(item)
        self.game.resolve_top()

    def spell(self, c, by):
        return StackItem(by, list(c.spell_effects), [None], card=c, name=c.name)

    def test_vines_until_end_of_turn(self):
        """The opponent can't target it this turn; its controller still can; next turn the ban is gone."""
        bear = self.perm(BEAR, self.a)
        self.cast(VINES, [bear], self.a)
        self.assertFalse(self.game.targetable(bear, self.b, self.spell(DOOM, self.b)))
        self.assertTrue(self.game.targetable(bear, self.a, self.spell(GROWTH, self.a)))
        self.game.turn += 1
        self.assertTrue(self.game.targetable(bear, self.b, self.spell(DOOM, self.b)))

    def test_removal_in_response_fizzles(self):
        """Removal aimed before Vines resolved finds an illegal target and does nothing (CR 608.2b)."""
        bear = self.perm(BEAR, self.a)
        doom = StackItem(self.b, list(DOOM.spell_effects), [bear], card=DOOM, name="Doom")
        self.game.stack.append(doom)
        self.cast(VINES, [bear], self.a)
        self.game.resolve_top()
        self.assertIn(bear, self.a.battlefield)

    def test_group_colours_only_at_resolution(self):
        """CR 611.2c: the permanents it affects are fixed as it resolves; only blue or black spells are stopped."""
        bear = self.perm(BEAR, self.a)
        self.cast(DISPLAY, [None], self.a)
        later = self.perm(BEAR, self.a)
        self.assertFalse(self.game.targetable(bear, self.b, self.spell(DOOM, self.b)))
        self.assertTrue(self.game.targetable(bear, self.b, self.spell(SHOCK, self.b)))
        self.assertTrue(self.game.targetable(later, self.b, self.spell(DOOM, self.b)))


class HeuristicUse(Base):
    def test_ai_answers_removal_with_vines(self):
        bear = Permanent(card("Test Big", "{3}{G}", "Creature — Beast", "", 4, 4), self.a)
        self.a.battlefield = [bear, Permanent(FOREST, self.a)]
        self.a.hand = [VINES]
        doom = StackItem(self.b, list(DOOM.spell_effects), [bear], card=DOOM, name="Doom")
        self.game.stack.append(doom)
        answer = self.a.ai.save_creature(self.game, self.a, doom, [VINES])
        self.assertIsNotNone(answer)
        self.assertIs(answer[0], VINES)
        self.assertIn(bear, answer[1])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Vines of Vastwood", "Veilstone Amulet", "Display of Dominance"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))
        self.assertEqual(card_coverage(db.get("Autumn's Veil")).status, "partial")


if __name__ == "__main__":
    unittest.main()

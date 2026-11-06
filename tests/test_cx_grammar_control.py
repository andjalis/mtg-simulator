"""The control verb family (mtgsim.cx_grammar_control)."""
import unittest

from mtgsim import counter_mechanics
from mtgsim.cx_grammar import parse_sentence

from tests.test_cx_grammar import DB_FILE, WOLF, Base
from tests.test_templates import BEAR, card


class Resolving(Base):
    def test_until_end_of_turn(self):
        wolf = self.perm(WOLF, self.b)
        self.cast(self.spell("Gain control of target creature until end of turn."), [wolf])
        self.assertIs(wolf.controller, self.a)
        counter_mechanics.expire_source_control(self.game, cleanup=True)
        self.assertIs(wolf.controller, self.b)

    def test_for_good(self):
        wolf = self.perm(WOLF, self.b)
        self.cast(self.spell("Gain control of target creature."), [wolf])
        counter_mechanics.expire_source_control(self.game, cleanup=True)
        self.assertIs(wolf.controller, self.a)

    def test_untap_and_steal(self):
        wolf = self.perm(WOLF, self.b)
        wolf.tapped = True
        self.cast(self.spell("Untap target creature and gain control of it until end of turn."), [wolf])
        self.assertIs(wolf.controller, self.a)
        self.assertFalse(wolf.tapped)

    def test_target_opponent_gains_control_of_it(self):
        c = card("Test Gift", "{1}", "Creature — Dog", "When ~ enters, target opponent gains control of ~.", 3, 3)
        self.assertEqual(c.unsupported, [])
        dog = self.perm(c, self.a)
        from mtgsim.engine import StackItem
        effs = c.triggers[0].effects
        self.game.stack.append(StackItem(self.a, list(effs), [self.b], source=dog, kind="trigger"))
        self.game.resolve_top()
        self.assertIs(dog.controller, self.b)

    def test_rejects(self):
        for s in ("Gain control of target creature for as long as you control ~.",
                  "Gain control of target creature this turn."):
            self.assertIsNone(parse_sentence(s), s)


class AIUse(Base):
    def test_ai_steals_the_best_creature_before_combat(self):
        giant = self.perm(card("Test Giant", "{4}", "Creature — Giant", "", 5, 5), self.b)
        self.perm(BEAR, self.b)
        self.perm(BEAR, self.a)
        spell = self.spell("Gain control of target creature until end of turn.", types="Sorcery")
        plan = self.a.ai.plan_spell(self.game, self.a, spell, precombat=True)
        self.assertIsNotNone(plan)
        self.assertIs(plan[1][0], giant)
        self.assertIsNone(self.a.ai.plan_spell(self.game, self.a, spell, precombat=False))

    def test_ai_takes_their_permanent_for_good(self):
        wolf = self.perm(WOLF, self.b)
        self.perm(BEAR, self.a)
        spell = self.spell("Gain control of target creature.", types="Sorcery")
        plan = self.a.ai.plan_spell(self.game, self.a, spell, precombat=False)
        self.assertIsNotNone(plan)
        self.assertIs(plan[1][0], wolf)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Word of Seizing", "Hijack"):
            row = card_coverage(db.get(name))
            self.assertIn(row.status, (FULL,), (name, row.ignored))


if __name__ == "__main__":
    unittest.main()

"""The tap verb family (mtgsim.cx_grammar_tap)."""
import unittest

from mtgsim.cx_grammar import parse_sentence

from tests.test_cx_grammar import DB_FILE, GOBLIN, WOLF, Base
from tests.test_templates import BEAR, ISLAND, card


class Resolving(Base):
    def test_tap_a_group(self):
        white = card("Test Knight", "{W}", "Creature — Knight", "", 2, 2)
        k, g = self.perm(white, self.b), self.perm(GOBLIN, self.b)
        self.cast(self.spell("Tap all nonwhite creatures."))
        self.assertEqual((k.tapped, g.tapped), (False, True))

    def test_next_untap_step_is_skipped(self):
        bear = self.perm(BEAR, self.b)
        self.cast(self.spell("Tap target creature. It doesn't untap during its controller's next untap step."),
                  [bear, None])
        self.game.untap_step(self.b)
        self.assertTrue(bear.tapped)
        self.game.untap_step(self.b)
        self.assertFalse(bear.tapped)

    def test_static_no_untap(self):
        lock = card("Test Lock", "{U}", "Enchantment", "Islands don't untap during their controllers' untap steps.")
        self.assertEqual(lock.unsupported, [])
        self.perm(lock, self.a)
        island, bear = self.perm(ISLAND, self.b), self.perm(BEAR, self.b)
        island.tapped = bear.tapped = True
        self.game.untap_step(self.b)
        self.assertEqual((island.tapped, bear.tapped), (True, False))

    def test_tap_or_untap(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        mine.tapped = True
        effs = parse_sentence("Tap or untap target creature.")
        self.game.resolve(self.a, effs[0], mine)
        self.game.resolve(self.a, effs[0], theirs)
        self.assertEqual((mine.tapped, theirs.tapped), (False, True))

    def test_rejects(self):
        for s in ("Tap target creature that player controls.", "Tap target creature until end of turn.",
                  "Islands don't untap during your untap step."):
            self.assertIsNone(parse_sentence(s), s)


class AIUse(Base):
    def test_ai_taps_their_blockers_before_attacking(self):
        spell = card("Test Tap", "{U}", "Sorcery", "Tap all creatures your opponents control.")
        self.assertEqual(spell.unsupported, [])
        blockers = [self.perm(WOLF, self.b) for _ in range(3)]
        for _ in range(2):
            self.perm(BEAR, self.a).sick = False
        self.perm(ISLAND, self.a)
        self.a.hand = [spell]
        self.game.step = "main1"
        plan = self.a.ai.plan_spell(self.game, self.a, spell, precombat=True)
        self.assertIsNotNone(plan)
        self.cast(spell)
        self.assertTrue(all(b.tapped for b in blockers))

    def test_ai_aims_a_freeze_at_the_opponent(self):
        self.perm(BEAR, self.a)
        theirs = self.perm(WOLF, self.b)
        spell = self.spell("Tap target creature.")
        eff = parse_sentence("Target creature doesn't untap during its controller's next untap step.")[0]  # grammar's reading
        self.assertEqual(eff.kind, "cx_skip_untap")
        with self.game.targeting(spell):
            self.assertIs(self.a.ai.choose_target(self.game, self.a, eff, spell), theirs)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Jolt", "Twiddle"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()

"""mega-batch4 (5): self-suspend — "Exile ~ with three time counters on it."

Inspiring Refrain and friends (Reality Strobe, Arc Blade, Rousing Refrain, Festering
March, Chronomantic Escape, Venture Forth, Charnel Serenade) resolve, then exile
themselves with N time counters instead of going to the graveyard, re-entering the
existing suspend machinery (``Player.suspended`` + the upkeep tick in alt_casts). The
``self_suspend`` kind marks the resolving spell (item.self_suspend, the shuffle_self
pattern); the stack hook that actually moves the card is pending from the foundation
agent, so these tests fire it manually, exactly like the Beacon cycle's tests did.
"""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem
from tests.test_batch1 import Batch1
from tests.test_templates import card

REFRAIN = card("Test Refrain", "{4}{U}{2}", "Sorcery",
               "Draw two cards. Exile Test Refrain with three time counters on it.")


class SelfSuspendParse(unittest.TestCase):
    def test_wordings(self):
        for n, word in ((1, "a"), (2, "two"), (3, "three"), (5, "five"), (4, "4")):
            effects, bad = _parse_effects(
                f"~ deals 1 damage to any target. Exile ~ with {word} time counter"
                f"{'s' if n > 1 else ''} on it.")
            self.assertFalse(bad, bad)
            self.assertEqual((effects[-1].kind, effects[-1].amount), ("self_suspend", n))

    def test_template(self):
        self.assertEqual(REFRAIN.unsupported, [])
        self.assertEqual([e.kind for e in REFRAIN.spell_effects], ["draw", "self_suspend"])


class SelfSuspendBehavior(Batch1):
    def resolve_refrain(self):
        effects, bad = _parse_effects("Draw two cards. Exile ~ with three time counters on it.")
        self.assertFalse(bad, bad)
        item = StackItem(self.a, effects, [], card=REFRAIN, kind="spell")
        item.resolved = True
        for eff, tgt in zip(effects, [None, None]):
            self.g.resolve(self.a, eff, tgt, item)
        return item

    def test_spell_marks_itself(self):
        item = self.resolve_refrain()
        self.assertEqual(item.self_suspend, 3)
        self.assertEqual(len(self.a.hand), 2)       # the draw still resolved

    def test_pending_hook_suspends_the_card(self):
        item = self.resolve_refrain()
        # The pending stack hook (to be added to Game.to_graveyard_after_resolving, next
        # to the shuffle_self branch):
        #   elif getattr(item, "self_suspend", 0):
        #       owner.exile.append(base)
        #       owner.suspended.append([base, item.self_suspend])
        base, _, _ = self.g._origin(item.card)
        if getattr(item, "self_suspend", 0):
            self.a.exile.append(base)
            self.a.suspended.append([base, item.self_suspend])
        self.assertIn(base, self.a.exile)
        self.assertIn([base, 3], self.a.suspended)
        self.assertNotIn(base, self.a.graveyard)

    def test_upkeep_tick_recasts_it(self):
        n = len(self.a.hand)
        item = self.resolve_refrain()
        self.assertEqual(len(self.a.hand), n + 2)   # the first cast drew its cards
        base, _, _ = self.g._origin(item.card)
        # the direct resolve() here bypasses the stack, so the hook is fired by hand
        self.a.exile.append(base)
        self.a.suspended.append([base, item.self_suspend])
        from mtgsim import alt_casts
        self.g.turn, self.g.step, self.g.active_idx = 3, "upkeep", 0
        alt_casts.upkeep(self.g, self.a)
        self.assertEqual(self.a.suspended, [[base, 2]])
        alt_casts.upkeep(self.g, self.a)
        self.assertEqual(self.a.suspended, [[base, 1]])
        alt_casts.upkeep(self.g, self.a)
        # cast() outside a priority loop resolves before returning: the recast drew two
        # more cards, and the real stack hook re-suspended it for another three counters
        self.assertEqual(len(self.a.hand), n + 4)
        self.assertEqual(self.a.suspended, [[base, 3]])


class SelfSuspendDatabase(unittest.TestCase):

    def test_self_suspend_cards_resolve_fully(self):
        try:
            from mtgsim.carddb import CardDB
            from mtgsim.coverage import FULL, card_coverage
            db = CardDB()
        except Exception:
            self.skipTest("card database not built")
        if db._all is None:
            self.skipTest("card database not built")
        for name in ("Inspiring Refrain", "Reality Strobe", "Arc Blade", "Festering March",
                     "Charnel Serenade"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()

"""#629: "exchange life totals with target opponent" (#760's life_total) and "[you may have] two target players exchange
life totals" (life_total, extended here), plus the AI's window for "Activate only during your upkeep" abilities
(cx_upkeep_acts)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Axis of Mortality", "Magus of the Mirror", "Mirror Universe", "Soul Conduit")
SWAP = card("Test Swap", "{2}{B}", "Sorcery", "Exchange life totals with target opponent.")
BOTH = card("Test Both", "{2}{B}", "Sorcery", "Two target players exchange life totals.")
AXIS = card("Test Axis", "{4}{W}", "Enchantment",
            "At the beginning of your upkeep, you may have two target players exchange life totals.")
FAN = card("Test Fan", "{1}", "Creature — Human", "Whenever you gain life, put a +1/+1 counter on ~.", 1, 1)
SHROUD = card("Test Mask", "{2}{W}{W}", "Enchantment", "You have shroud.")


def game(mine=20, theirs=20):
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    a.life, b.life = mine, theirs
    return g, a, b


def cast(g, p, c, targets=None):
    effects = list(c.spell_effects)
    targets = g.auto_targets(p, effects, None) if targets is None else targets
    g.stack.append(StackItem(p, effects, targets, card=c, name=c.name))
    g.resolve_top()
    g.settle()
    return targets


class Parse(unittest.TestCase):
    def test_shapes(self):
        for c in (SWAP, BOTH, AXIS):
            self.assertEqual(c.unsupported, [], c.name)
        e = BOTH.spell_effects[0]
        self.assertEqual((e.kind, e.data["op"], e.data["both"], e.data["may"]), ("life_total", "exchange", True, False))
        self.assertTrue(AXIS.triggers[0].effects[-1].data["may"])
        self.assertEqual(SWAP.spell_effects[0].filter, "opp")

    def test_refusals(self):
        for text in ("Exchange life totals with target creature.",
                     "Target player and each of that player's teammates exchange life totals.",
                     "If the difference between your life total and target player's life total is 5 or less, exchange "
                     "life totals with that player.",
                     "Exchange your life total with target creature's toughness.",
                     "Exchange life totals with target opponent until end of turn."):
            self.assertTrue(card("Test Odd", "{B}", "Sorcery", text).unsupported, text)


class Resolve(unittest.TestCase):
    def test_exchange_aims_at_the_opponent_and_is_gaining_life(self):
        g, a, b = game(5, 18)
        fan = g.enter_battlefield(a, FAN)
        g.settle()
        targets = cast(g, a, SWAP)
        self.assertIs(targets[0], b)
        self.assertEqual((a.life, b.life), (18, 5))
        self.assertEqual(fan.p1, 1)                  # the exchange is a life gain for us (CR 701.12, 119.5)

    def test_two_targets_needs_the_controller_targetable(self):
        g, a, b = game(5, 18)
        g.enter_battlefield(a, SHROUD)
        g.settle()
        cast(g, a, BOTH, [b])
        self.assertEqual((a.life, b.life), (5, 18))

    def test_may_only_exchanges_up(self):
        for mine, theirs, after in ((5, 18, (18, 5)), (18, 5, (18, 5))):
            g, a, b = game(mine, theirs)
            g.enter_battlefield(a, AXIS)
            g.settle()
            g.step = "upkeep"
            g.fire(a, "upkeep")
            g.settle()
            self.assertEqual((a.life, b.life), after, (mine, theirs))

    def test_ai_wants_the_exchange_only_when_behind(self):
        from mtgsim.engine.policy import default_choose_target
        from mtgsim.residual_templates import effect_value
        eff = SWAP.spell_effects[0]
        for mine, theirs, good in ((5, 18, True), (18, 5, False)):
            g, a, b = game(mine, theirs)
            with g.targeting(SWAP):
                tgt = default_choose_target(g, a, eff)
            self.assertEqual(tgt is b, good, (mine, theirs))
            self.assertEqual(effect_value(g, a, eff, b) > 0, good, (mine, theirs))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in FULL:
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)

    def test_mirror_universe_is_used_in_our_upkeep_when_behind(self):
        for mine, used in ((3, True), (20, False)):
            g, a, b = game(mine, 20 if mine < 20 else 4)
            mirror = g.enter_battlefield(a, self.db.get("Mirror Universe"))
            g.settle()
            g.active_idx, g.step = 0, "upkeep"
            from mtgsim import cx_upkeep_acts
            cx_upkeep_acts.upkeep(g, a)
            g.settle()
            self.assertEqual(mirror not in a.battlefield, used, mine)
            if used:
                self.assertEqual((a.life, b.life), (20, 3))

    def test_soul_conduit_is_worth_activating_only_when_behind(self):
        from mtgsim.engine.policy import ability_worth
        for mine, theirs, good in ((4, 20, True), (20, 4, False)):
            g, a, b = game(mine, theirs)
            conduit = g.enter_battlefield(a, self.db.get("Soul Conduit"))
            for _ in range(6):
                g.enter_battlefield(a, self.db.get("Swamp"))
            g.settle()
            self.assertEqual(ability_worth(g, a, conduit, 0), good, (mine, theirs))

    def test_mirror_universe_not_in_main_phase(self):
        g, a, b = game(3, 20)
        mirror = g.enter_battlefield(a, self.db.get("Mirror Universe"))
        g.settle()
        g.active_idx = 0
        self.assertFalse(g.can_activate(a, mirror, 0))


if __name__ == "__main__":
    unittest.main()

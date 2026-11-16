"""#786: the AI uses cards the audit found unused.

- Artifact / enchantment removal that can't hit a creature (Mogg Salvage) is used at the opponent's end step on their
  best noncreature, nonland permanent (lower bar than creature removal).
- A kicker-gated enters trigger (Slinn Voda) is valued on the kicked variant only, so the AI kicks when it pays.
- "Exile X target creature cards from your graveyard" (Midnight Ritual) picks X cards, not one.
- Whiplash Trap's conditional {U} cost is used at the opponent's end step (it was a harness error in the audit).
"""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards.model import Effect
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
SIGNET = card("Test Signet", "{2}", "Artifact", "{1}, {T}: Add {U}{B}.")


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library, b.library = [ISLAND] * 20, [ISLAND] * 20
    return g, a, b


def ready(g, p, c, n=1):
    for _ in range(n):
        g.enter_battlefield(p, c).sick = False
    g.settle()


def their_end_step(g, a, b):
    g.active_idx, g.step = g.players.index(b), "end_step"
    play = a.ai.respond(g, a)
    if play:
        g.cast(a, play[0], play[1])
        g.settle()
    return play


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class AIUses(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)
        self.land = {n: self.db.get(n) for n in ("Island", "Mountain", "Swamp")}

    def test_mogg_salvage_destroys_their_artifact_at_end_of_turn(self):
        g, a, b = game()
        ready(g, a, self.land["Mountain"])
        ready(g, b, self.land["Island"])
        ready(g, b, SIGNET)
        a.hand = [self.db.get("Mogg Salvage")]
        play = their_end_step(g, a, b)
        self.assertIsNotNone(play)
        self.assertNotIn("Test Signet", [x.card.name for x in b.battlefield])

    def test_creature_removal_still_waits_for_a_worthy_creature(self):
        g, a, b = game()
        ready(g, a, self.land["Swamp"], 2)
        ready(g, b, SIGNET)
        ready(g, b, card("Test Squire", "{W}", "Creature — Human", "", 1, 1))
        a.hand = [card("Test Murder", "{1}{B}", "Instant", "Destroy target creature.")]
        self.assertIsNone(their_end_step(g, a, b))       # a 1/1 isn't worth it, and the Signet isn't a creature

    def test_slinn_voda_is_kicked_when_the_bounce_pays(self):
        g, a, b = game()
        ready(g, a, self.land["Island"], 10)
        ready(g, b, self.db.get("Craw Wurm"))
        ready(g, b, self.db.get("Hill Giant"))
        a.hand = [self.db.get("Slinn Voda, the Rising Deep")]
        a.ai.main_phase(g, a)
        g.settle()
        self.assertEqual([x.card.name for x in b.battlefield if x.is_creature], [])
        self.assertEqual(sorted(c.name for c in b.hand), ["Craw Wurm", "Hill Giant"])

    def test_slinn_voda_is_not_kicked_into_our_own_creatures(self):
        g, a, b = game()
        ready(g, a, self.land["Island"], 10)
        ready(g, a, self.db.get("Craw Wurm"))
        a.hand = [self.db.get("Slinn Voda, the Rising Deep")]
        a.ai.main_phase(g, a)
        g.settle()
        self.assertIn("Craw Wurm", [x.card.name for x in a.battlefield])

    def test_midnight_ritual_exiles_x_cards(self):
        g, a, b = game()
        ready(g, a, self.land["Swamp"], 5)
        a.graveyard = [BEAR, self.db.get("Hill Giant")]
        a.hand = [self.db.get("Midnight Ritual")]
        a.ai.main_phase(g, a)
        g.settle()
        self.assertEqual(sum(x.card.name == "Zombie token" for x in a.battlefield), 2)

    def test_whiplash_trap_uses_its_alternative_cost(self):
        g, a, b = game()
        code = 'lib:["hist","a creature an opponent controls enters",2]'
        g.check_cond(a, Effect("alt", cond=code), None, None)
        ready(g, a, self.land["Island"])
        g.enter_battlefield(b, self.db.get("Craw Wurm"))
        g.enter_battlefield(b, self.db.get("Hill Giant"))
        g.settle()
        a.hand = [self.db.get("Whiplash Trap")]
        play = their_end_step(g, a, b)
        self.assertIsNotNone(play)
        self.assertEqual(len(b.hand), 2)


if __name__ == "__main__":
    unittest.main()

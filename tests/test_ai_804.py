"""#804: the AI casts the Trap cards the audit found unused (their rules were already right).

- Divided damage to attackers (Arrow Volley Trap) is valued in kill_attacker with cx_damage.ai_worth.
- An instant creature-token maker (Baloth Cage Trap) is cast at the opponent's end step like the other cantrips.
- "Tap up to two target creatures. They don't untap ..." (Permafrost Trap): the tap's own freeze rider counts like a
  stun, and up to two creatures are valued.
- "Attacking creatures get -3/-0 until end of turn" (Lethargy Trap): kill_attacker values a group effect on the
  attackers with the grammar's group value (cast when the attack matters, e.g. lethal).
"""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards.model import Effect
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library, b.library = [ISLAND] * 20, [ISLAND] * 20
    return g, a, b


def respond_in(g, a, b, step):
    g.active_idx, g.step = g.players.index(b), step
    play = a.ai.respond(g, a)
    if play:
        g.cast(a, play[0], play[1])
        g.settle()
    return play


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Traps(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def lands(self, g, p, name, n):
        for _ in range(n):
            g.enter_battlefield(p, self.db.get(name)).sick = False
        g.settle()

    def condition_seen(self, g, a, name):
        """The "this turn" history head is registered as the card's condition is first checked (cx_condlib)."""
        g.check_cond(a, Effect("alt", cond=self.db.get(name).advanced_rules["alt_if"][0][0]), None, None)

    def test_permafrost_trap_taps_and_freezes_two_at_their_end_step(self):
        g, a, b = game()
        self.condition_seen(g, a, "Permafrost Trap")
        self.lands(g, a, "Island", 1)
        wurm = g.enter_battlefield(b, self.db.get("Craw Wurm"))
        giant = g.enter_battlefield(b, self.db.get("Hill Giant"))
        g.settle()
        a.hand = [self.db.get("Permafrost Trap")]
        self.assertIsNotNone(respond_in(g, a, b, "end_step"))
        self.assertTrue(wurm.tapped and giant.tapped)
        g.untap_step(b)
        self.assertTrue(wurm.tapped and giant.tapped)

    def test_baloth_cage_trap_makes_its_beast_at_their_end_step(self):
        g, a, b = game()
        self.condition_seen(g, a, "Baloth Cage Trap")
        self.lands(g, a, "Forest", 2)
        g.enter_battlefield(b, card("Test Rock", "{2}", "Artifact", ""))
        g.settle()
        a.hand = [self.db.get("Baloth Cage Trap")]
        self.assertIsNotNone(respond_in(g, a, b, "end_step"))
        self.assertEqual([(x.power, x.toughness) for x in a.battlefield if x.is_creature], [(4, 4)])

    def test_arrow_volley_trap_kills_attackers(self):
        g, a, b = game()
        self.lands(g, a, "Plains", 2)
        attackers = [g.enter_battlefield(b, BEAR) for _ in range(3)] + [g.enter_battlefield(b, self.db.get("Hill Giant"))]
        g.settle()
        g.attackers = list(attackers)
        a.hand = [self.db.get("Arrow Volley Trap")]
        self.assertIsNotNone(respond_in(g, a, b, "declare_attackers"))
        self.assertEqual(sum(x in b.battlefield for x in attackers), 2)        # 5 damage: a Bear and the Giant

    def test_lethargy_trap_blunts_a_lethal_attack(self):
        g, a, b = game()
        self.lands(g, a, "Island", 1)
        a.life = 8
        attackers = [g.enter_battlefield(b, self.db.get("Hill Giant")) for _ in range(3)]
        g.settle()
        g.attackers = list(attackers)
        a.hand = [self.db.get("Lethargy Trap")]
        self.assertIsNotNone(respond_in(g, a, b, "declare_attackers"))
        self.assertEqual([x.power for x in attackers], [0, 0, 0])

    def test_arrow_volley_trap_is_held_for_a_single_small_attacker(self):
        g, a, b = game()
        self.lands(g, a, "Plains", 5)
        g.attackers = [g.enter_battlefield(b, card("Test Squire", "{W}", "Creature — Human", "", 1, 1))]
        g.settle()
        a.hand = [self.db.get("Arrow Volley Trap")]
        self.assertIsNone(respond_in(g, a, b, "declare_attackers"))


if __name__ == "__main__":
    unittest.main()

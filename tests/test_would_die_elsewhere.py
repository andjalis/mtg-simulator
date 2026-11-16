"""#407 slices: "If ~ would die, put it on top of / on the bottom of its owner's library / return it to its owner's
hand instead" (Gravebane Zombie, Nissa's Chosen), and "If a permanent dealt damage this way would die this turn,
exile it instead" (Spikefield Hazard: planeswalkers too)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card

TOP = card("Test Zombie", "{3}{B}", "Creature — Zombie", "If ~ would die, put it on top of its owner's library "
           "instead.", 3, 2)
BOTTOM = card("Test Elf", "{2}{G}", "Creature — Elf", "If ~ would die, put it on the bottom of its owner's library "
              "instead.", 2, 3)
HAND = card("Test Bird", "{2}{R}", "Creature — Bird", "If ~ would die, return it to its owner's hand instead.", 2, 2)
WATCHER = card("Test Watcher", "{1}{B}", "Creature — Human", "Whenever another creature you control dies, you gain "
               "1 life.", 1, 1)


def game():
    a, b = Player("a", [ISLAND] * 10, HeuristicAI()), Player("b", [ISLAND] * 10, HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    for p in (a, b):
        p.library = [ISLAND] * 5
    return g, a, b


class SelfDestination(unittest.TestCase):
    def test_parse(self):
        for c, dest in ((TOP, "library_top"), (BOTTOM, "library_bottom"), (HAND, "hand")):
            self.assertEqual(c.unsupported, [], c.name)
            self.assertEqual(c.advanced_rules["cx_die_dest"], dest)
        bad = card("Test Bad", "{1}", "Creature — Elf", "If ~ would die, put it into its owner's hand instead.", 1, 1)
        self.assertTrue(bad.unsupported)

    def test_destroyed_goes_on_top_and_does_not_die(self):
        g, a, b = game()
        g.enter_battlefield(a, WATCHER)
        z = g.enter_battlefield(a, TOP)
        g.destroy(z)
        g.settle()
        self.assertEqual(a.library[-1].name, TOP.name)
        self.assertEqual(a.graveyard, [])
        self.assertEqual(a.life, 20)                     # it didn't die: no "dies" trigger

    def test_sacrifice_and_lethal_damage(self):
        g, a, b = game()
        e = g.enter_battlefield(a, BOTTOM)
        g.leave_battlefield(e, "graveyard")              # a sacrifice is a death too
        self.assertEqual(a.library[0].name, BOTTOM.name)
        bird = g.enter_battlefield(a, HAND)
        g.deal_damage(bird, 5, by=b, cause="test")
        g.state_based_actions()
        self.assertIn(HAND.name, [c.name for c in a.hand])

    def test_bounce_is_not_dying(self):
        g, a, b = game()
        z = g.enter_battlefield(a, TOP)
        g.leave_battlefield(z, "exile")
        self.assertIn(TOP.name, [c.name for c in a.exile])


class DamagedPermanent(unittest.TestCase):
    def test_parse(self):
        effects, bad = _parse_effects("~ deals 3 damage to any target. If a permanent dealt damage this way would die "
                                      "this turn, exile it instead.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].data["exile_dying"], "permanent")

    @unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
    def test_planeswalker_and_creature_exiled(self):
        from mtgsim.carddb import CardDB
        effects, _ = _parse_effects("~ deals 3 damage to any target. If a permanent dealt damage this way would die "
                                    "this turn, exile it instead.")
        walker = CardDB(offline=True).get("Jace Beleren")            # loyalty 3
        for victim in (walker, card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)):
            g, a, b = game()
            v = g.enter_battlefield(b, victim)
            g.stack.append(StackItem(a, list(effects), [v], kind="ability"))
            g.resolve_top()
            g.state_based_actions()
            self.assertNotIn(v, b.battlefield, victim.name)
            self.assertEqual([c.name for c in b.exile], [victim.name])
            self.assertEqual(b.graveyard, [])


HUNT = card("Test Hunt", "{3}{G}", "Creature — Wolf", "If a creature an opponent controls would die, exile it instead. "
            "When you do, create a 2/2 green Wolf creature token.", 3, 3)


class WhenYouDo(unittest.TestCase):
    def wolves(self, a):
        return sum(x.card.name.startswith("Wolf") for x in a.battlefield)

    def test_parse(self):
        self.assertEqual(HUNT.unsupported, [])
        self.assertEqual(HUNT.advanced_rules["cx_exile_when"][0][0], "a creature an opponent controls")
        bad = card("Test Bad", "{3}{G}", "Creature — Wolf", "If a creature an opponent controls would die, exile it "
                   "instead. When you do, frobnicate the widget.", 3, 3)
        self.assertTrue(bad.unsupported)

    def test_only_when_the_exile_replaced_the_death(self):
        g, a, b = game()
        g.enter_battlefield(a, HUNT)
        ogre = g.enter_battlefield(b, card("Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3))
        mine = g.enter_battlefield(a, card("Mine", "{1}", "Creature — Elf", "", 1, 1))
        g.destroy(ogre)
        g.settle()
        self.assertEqual([c.name for c in b.exile], ["Ogre"])
        self.assertEqual(self.wolves(a), 1)
        g.destroy(mine)                                  # mine dies normally: no Wolf
        g.settle()
        self.assertEqual([c.name for c in a.graveyard], ["Mine"])
        self.assertEqual(self.wolves(a), 1)

    def test_other_exile_replacement_does_not_trigger(self):
        g, a, b = game()
        g.enter_battlefield(a, HUNT)
        ogre = g.enter_battlefield(b, card("Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3))
        g.leave_battlefield(ogre, "exile")              # exiled, not a death replaced by the Hunt
        g.settle()
        self.assertEqual(self.wolves(a), 0)


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class Cards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Gravebane Zombie", "Nissa's Chosen", "Spikefield Hazard // Spikefield Cave", "Head of the Hunt",
                     "Nemata, Primeval Warden"):
            self.assertEqual(db.get(name).unsupported, [], name)
        self.assertTrue(db.get("Firestorm Phoenix").unsupported)     # its "can't play it" rider


if __name__ == "__main__":
    unittest.main()

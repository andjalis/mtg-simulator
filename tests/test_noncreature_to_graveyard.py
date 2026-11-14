"""#389: "When ~ is put into a graveyard from the battlefield" on a noncreature permanent (an artifact, an
enchantment, an Aura) fires when it goes there: destroyed, sacrificed, or put there by state-based actions."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card

STAR = card("Test Star", "{1}", "Artifact",
            "When Test Star is put into a graveyard from the battlefield, draw a card.")
CHARM = card("Test Charm", "{1}", "Enchantment",
             "When Test Charm is put into a graveyard from the battlefield, you gain 3 life.")
AURA = card("Test Aura", "{G}", "Enchantment — Aura",
            "Enchant creature\nEnchanted creature gets +2/+0.\n"
            "When Test Aura is put into a graveyard from the battlefield, return Test Aura to its owner's hand.")


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 1, "main1"
        self.a.library, self.b.library = [ISLAND] * 20, [ISLAND] * 20

    def attach(self, c, host):
        from mtgsim import auras
        aura = self.game.enter_battlefield(self.a, c)
        if host not in aura.controller.battlefield or aura.aura_host is not host:
            auras.attach(self.game, aura, host)
        self.settle()
        self.assertIs(aura.aura_host, host)
        return aura

    def settle(self):
        for _ in range(10):
            self.game.state_based_actions()
            if not self.game.flush_triggers() and not self.game.stack:
                break
            while self.game.stack:
                self.game.resolve_top()

    def enter(self, c, who=None):
        perm = self.game.enter_battlefield(who or self.a, c)
        self.settle()
        return perm


class Fires(Base):
    def test_parsed_as_own_trigger(self):
        for c in (STAR, CHARM, AURA):
            self.assertEqual(c.unsupported, [], c.name)
            self.assertIn("dies", [t.event for t in c.triggers], c.name)

    def test_destroyed_artifact(self):
        star = self.enter(STAR)
        self.game.destroy(star)
        self.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_sacrificed_artifact(self):
        star = self.enter(STAR)
        self.game.sacrifice(star)
        self.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_destroyed_enchantment_on_opponents_side(self):
        charm = self.enter(CHARM, self.b)
        self.game.destroy(charm)
        self.settle()
        self.assertEqual((self.a.life, self.b.life), (20, 23))      # its controller's trigger

    def test_aura_returns_when_its_host_dies(self):
        bear = self.enter(BEAR)
        self.attach(AURA, bear)
        self.game.destroy(bear)
        self.settle()
        self.assertIn("Test Aura", [c.name for c in self.a.hand])


class DoesNotFire(Base):
    def test_bounced_or_exiled(self):
        star = self.enter(STAR)
        self.game.leave_battlefield(star, "hand")
        charm = self.enter(CHARM)
        self.game.leave_battlefield(charm, "exile")
        self.settle()
        self.assertEqual((len(self.a.hand), self.a.life), (1, 20))     # just the bounced Star

    def test_not_a_creature_death(self):
        # "whenever a creature dies" / "a creature died this turn" don't see a noncreature going to the graveyard
        watcher = self.enter(card("Test Watcher", "{1}", "Enchantment",
                                  "Whenever a creature dies, you gain 1 life."))
        self.assertEqual(watcher.card.unsupported, [])
        star = self.enter(STAR)
        self.game.destroy(star)
        self.settle()
        self.assertEqual(self.a.life, 20)
        self.assertFalse(getattr(self.game, "creature_died_turn", False))

    def test_creature_fires_once(self):
        zombie = self.enter(card("Test Zombie", "{1}{B}", "Creature — Zombie",
                                 "When Test Zombie dies, you gain 2 life.", 2, 2))
        self.game.destroy(zombie)
        self.settle()
        self.assertEqual(self.a.life, 22)


PHOENIX = card("Test Phoenix", "{2}{R}", "Creature — Phoenix", "When Test Phoenix dies, return it to its owner's hand.",
               2, 2)


class ReturnFromGraveyard(Base):
    """"... return it / ~ to its owner's hand" in such a trigger finds the card in the graveyard (CR 400.7)."""
    def test_creature_dies_returns_it(self):
        phoenix = self.enter(PHOENIX)
        self.game.destroy(phoenix)
        self.settle()
        self.assertEqual(([c.name for c in self.a.hand], self.a.graveyard), (["Test Phoenix"], []))

    def test_card_already_gone_from_the_graveyard_stays_gone(self):
        phoenix = self.enter(PHOENIX)
        self.game.destroy(phoenix)
        card_ = self.a.graveyard[-1]
        self.game.move_card(card_, self.a.graveyard, self.a.exile, reason="exile")     # exiled in response
        self.settle()
        self.assertEqual((self.a.hand, [c.name for c in self.a.exile]), ([], ["Test Phoenix"]))

    def test_bounced_permanent_is_not_returned_again(self):
        star = self.enter(card("Test Loop", "{1}", "Artifact",
                               "When Test Loop is put into a graveyard from the battlefield, return Test Loop to its "
                               "owner's hand."))
        self.game.leave_battlefield(star, "exile")
        self.settle()
        self.assertEqual((self.a.hand, [c.name for c in self.a.exile]), ([], ["Test Loop"]))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def card(self, name):
        from mtgsim.carddb import CardDB
        return CardDB(offline=True).get(name)

    def test_chromatic_star_sacrificed_draws(self):
        star = self.enter(self.card("Chromatic Star"))
        self.game.sacrifice(star)
        self.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_rancor_returns_when_its_creature_dies(self):
        bear = self.enter(BEAR)
        self.attach(self.card("Rancor"), bear)
        self.game.destroy(bear)
        self.settle()
        self.assertEqual([c.name for c in self.a.hand], ["Rancor"])

    def test_spirit_loop_returns_to_hand(self):
        bear = self.enter(BEAR)
        self.attach(self.card("Spirit Loop"), bear)
        self.game.destroy(bear)
        self.settle()
        self.assertIn("Spirit Loop", [c.name for c in self.a.hand])


if __name__ == "__main__":
    unittest.main()

"""Zone heads and subject qualifiers of the cx_events trigger grammar (#404 slice 2): enters from a graveyard /
exile, exiled from the battlefield, returned to hand, leaves without dying, whose graveyard, owned by another
player, chosen type, power or toughness, and the selector() fallback for subjects."""
import os
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.cx_events import compile_head
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import BEAR, Scripted
from tests.test_templates import ISLAND, card

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None
GOBLIN = card("Test Goblin", "{R}", "Creature — Goblin", "", 1, 1)
OGRE = card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)


class Heads(unittest.TestCase):
    def test_flags(self):
        for head, raw, flag in (("When ~ enters from a graveyard", "etb", "from_gy"),
                                ("Whenever a creature enters from your graveyard", "etb", "from_my_gy"),
                                ("Whenever a creature is exiled from the battlefield", "leaves", "to_exile"),
                                ("Whenever a permanent is returned to your hand", "leaves", "to_my_hand"),
                                ("Whenever another creature you control leaves the battlefield without dying", "leaves",
                                 "no_die"),
                                ("Whenever a creature is put into an opponent's graveyard from the battlefield",
                                 "perm_to_gy", "gy_opp")):
            got = compile_head(head)
            self.assertIsNotNone(got, head)
            self.assertEqual(got[1]["flags"][raw], flag, head)

    def test_qualifiers(self):
        self.assertEqual(compile_head("Whenever a creature you control with power or toughness 1 or less dies")[1]
                         ["with"], [("pt_or<=", 1)])
        self.assertEqual(compile_head("Whenever a permanent owned by another player is put into a graveyard from "
                                      "the battlefield")[1]["with"], [("own_opp",)])
        sel = compile_head("Whenever a creature with a coin counter on it dies")[1]["with"]
        self.assertEqual(sel[0][0], "sel")

    def test_refusals(self):
        for head in ("Whenever another legendary creature or creature with mana value one enters",
                     "Whenever a creature enters from a frobnicated zone",
                     "Whenever a creature is returned to a library",
                     "Whenever a creature with a frob counter and flying dies"):
            self.assertIsNone(compile_head(head), head)


@unittest.skipUnless(HAVE_DB, "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        for n in ("Triarch Praetorian", "River Kelpie", "Dredging Claw", "Flayer of the Hatebound",
                  "Kothophed, Soul Hoarder", "Arnyn, Deathbloom Botanist", "Athreos, Shroud-Veiled",
                  "Bloodline Pretender", "Molten Echoes", "Kindred Discovery", "Soulherder",
                  "Justice, Vance Astrovik", "Azorius Aethermage", "Imperial Cosmographer", "Three Tree Scribe"):
            self.assertEqual(DB.get(n).unsupported, [], n)


@unittest.skipUnless(HAVE_DB, "card database not built")
class Games(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 2, "main1", 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        self.game.settle()
        return perm

    def reanimate(self, who, c):
        """c goes to who's graveyard, then onto the battlefield from there."""
        who.hand.append(c)
        self.game.move_card(c, who.hand, who.graveyard, reason="discard")
        inst = who.graveyard[-1]
        who.graveyard.remove(inst)
        perm = self.game.enter_battlefield(who, inst)
        self.game.settle()
        return perm

    def test_enters_from_your_graveyard(self):
        claw = self.put(self.a, DB.get("Dredging Claw"))
        self.put(self.a, BEAR)                              # not from a graveyard: no trigger
        self.assertIsNone(claw.attached_to)
        theirs = self.reanimate(self.b, GOBLIN)             # their graveyard: no trigger
        self.assertIsNone(claw.attached_to)
        mine = self.reanimate(self.a, OGRE)
        self.assertIs(claw.attached_to, mine)
        self.assertIsNot(claw.attached_to, theirs)

    def test_self_enters_from_a_graveyard(self):
        hand = len(self.a.hand)
        self.put(self.a, DB.get("Triarch Praetorian"))
        self.assertEqual(len(self.a.hand), hand)
        self.reanimate(self.a, DB.get("Triarch Praetorian"))
        self.assertEqual(len(self.a.hand), hand + 2)        # "you draw two cards and you lose 2 life"
        self.assertEqual(self.a.life, 18)

    def test_exiled_from_the_battlefield(self):
        herder = self.put(self.a, DB.get("Soulherder"))
        bear, goblin = self.put(self.b, BEAR), self.put(self.b, GOBLIN)
        self.game.destroy(goblin)                           # dies: not exiled
        self.game.settle()
        self.assertEqual(herder.counters.get("+1/+1", 0), 0)
        self.game.leave_battlefield(bear, "exile")
        self.game.settle()
        self.assertEqual(herder.counters.get("+1/+1", 0), 1)

    def test_leaves_without_dying(self):
        cosmo = self.put(self.a, DB.get("Imperial Cosmographer"))
        bear, goblin = self.put(self.a, BEAR), self.put(self.a, GOBLIN)
        base = cosmo.counters.get("+1/+1", 0)
        self.game.destroy(goblin)
        self.game.settle()
        self.assertEqual(cosmo.counters.get("+1/+1", 0), base)
        self.game.leave_battlefield(bear, "hand")
        self.game.settle()
        self.assertEqual(cosmo.counters.get("+1/+1", 0), base + 2)

    def test_owned_by_another_player(self):
        self.put(self.a, DB.get("Kothophed, Soul Hoarder"))
        mine, theirs = self.put(self.a, BEAR), self.put(self.b, GOBLIN)
        hand, life = len(self.a.hand), self.a.life
        self.game.destroy(mine)
        self.game.settle()
        self.assertEqual((len(self.a.hand), self.a.life), (hand, life))
        self.game.destroy(theirs)
        self.game.settle()
        self.assertEqual((len(self.a.hand), self.a.life), (hand + 1, life - 1))

    def test_power_or_toughness_one_or_less(self):
        self.put(self.a, DB.get("Arnyn, Deathbloom Botanist"))
        ogre, goblin = self.put(self.a, OGRE), self.put(self.a, GOBLIN)
        self.game.destroy(ogre)
        self.game.settle()
        self.assertEqual(self.b.life, 20)
        self.game.destroy(goblin)
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (22, 18))

    def test_coin_counter_creature_exiled_returns(self):
        athreos = self.put(self.a, DB.get("Athreos, Shroud-Veiled"))
        bear = self.put(self.b, BEAR)
        bear.counters["coin"] = 1
        self.game.leave_battlefield(bear, "exile")
        self.game.settle()
        self.assertTrue(any(x.card.name == BEAR.name for x in self.a.battlefield))
        plain = self.put(self.b, GOBLIN)
        self.game.leave_battlefield(plain, "exile")
        self.game.settle()
        self.assertFalse(any(x.card.name == GOBLIN.name for x in self.a.battlefield))
        self.assertIsNotNone(athreos)

    def test_granted_dies_or_exiled_returns_the_card(self):
        from mtgsim.engine.state import StackItem
        for leave in ("exile", "destroy"):
            bear = self.put(self.a, BEAR)
            spell = DB.get("Ashnod's Intervention")
            self.game.stack.append(StackItem(self.a, spell.spell_effects, [bear] * len(spell.spell_effects),
                                             card=spell, kind="spell"))
            self.game.settle()
            if leave == "exile":
                self.game.leave_battlefield(bear, "exile")
            else:
                self.game.destroy(bear)
            self.game.settle()
            self.assertIn(bear.front, self.a.hand, leave)
            self.a.hand.remove(bear.front)

    def test_returned_to_your_hand(self):
        self.put(self.a, DB.get("Azorius Aethermage"))
        bear = self.put(self.b, BEAR)
        hand = len(self.a.hand)
        self.game.leave_battlefield(bear, "hand")           # their card to their hand: no trigger
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand)

    def test_whose_graveyard(self):
        grave = card("Test Grave Watcher", "{2}{B}", "Enchantment",
                     "Whenever a creature is put into an opponent's graveyard from the battlefield, you gain 1 life.")
        self.assertEqual(grave.unsupported, [])
        self.put(self.a, grave)
        mine, theirs = self.put(self.a, BEAR), self.put(self.b, BEAR)
        self.game.destroy(mine)
        self.game.settle()
        self.assertEqual(self.a.life, 20)
        self.game.destroy(theirs)
        self.game.settle()
        self.assertEqual(self.a.life, 21)


if __name__ == "__main__":
    unittest.main()

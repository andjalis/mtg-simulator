"""Damage trigger heads from any source with "that much" payoffs (#521)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_trigger
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")
MOUNTAIN = card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")
ISLAND = card("Island", types="Basic Land — Island", text="({T}: Add {U}.)")
BOLT = card("Test Bolt", "{R}", "Instant", "~ deals 3 damage to any target.")
FROST = card("Test Frost", "{U}", "Instant", "~ deals 3 damage to any target.")
SWEEP = card("Test Sweep", "{R}", "Sorcery", "~ deals 1 damage to each creature.")


def parsed(line):
    out = _parse_trigger(line)
    if out is None or out[1] or not out[0]:
        return None
    return [(t.event, [(e.kind, e.data.get("src"), e.data.get("to"), e.data.get("gain")) for e in t.effects])
            for t in out[0]]


class Parsing(unittest.TestCase):
    def test_heads(self):
        self.assertEqual(parsed("Whenever a creature deals damage to ~, ~ deals that much damage to that creature."),
                         [("cx_dmg", [("cx_dmg_payoff", "self", "that_creature", None)])])
        self.assertEqual(parsed("Whenever a noncreature source you control deals damage, you gain that much life."),
                         [("cx_dmg", [("cx_dmg_payoff", None, None, True)])])
        self.assertEqual(parsed("Whenever an Archer you control deals damage to a creature, that Archer deals that "
                                "much damage to that creature's controller."),
                         [("cx_dmg", [("cx_dmg_payoff", "subject", "that_creature_controller", None)])])

    def test_refusals(self):
        for line in ("Whenever an instant or sorcery spell you control that targets only a single creature deals "
                     "damage to that creature, ~ deals that much damage to each opponent.",          # Imodane
                     "Whenever a spell deals damage, draw a card.",                                   # not a payoff
                     "Whenever an artifact spell deals damage, you gain that much life.",             # unknown noun
                     "Whenever a creature deals damage to ~, ~ deals that much damage to that creature's controller.",
                     "Whenever ~ deals damage to a creature, it deals that much damage to that creature.",
                     "Whenever a creature deals damage to a creature, ~ deals that much damage to each other "
                     "creature defending player controls."):                                          # no blocker
            with self.subTest(line):
                self.assertIsNone(parsed(line))


class Behaviour(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [MOUNTAIN] * 20

    def perm(self, p, text, name="Test Watcher", types="Creature — Beast", pt=(3, 3)):
        return self.game.enter_battlefield(p, card(name, "{3}", types, text, *pt))

    def cast(self, p, spell, target=None, land=MOUNTAIN):
        self.game.enter_battlefield(p, land).sick = False
        p.hand.append(spell)
        self.assertTrue(self.game.cast(p, spell, targets=[target] if target is not None else None))
        self.game.settle()

    def test_creature_and_spell_damage_to_me(self):
        teph = self.perm(self.a, "Whenever a creature deals damage to ~, ~ deals that much damage to that creature.\n"
                                 "Whenever a spell deals damage to ~, ~ deals that much damage to that spell's "
                                 "controller.", pt=(4, 5))
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.game.deal_damage(teph, 2, by=self.b, source=bear, combat=True)
        self.game.settle()
        self.assertEqual(bear.damage, 2)
        self.cast(self.b, BOLT, teph)
        self.assertEqual((self.b.life, teph.damage), (17, 5))

    def test_noncreature_source_batches_one_resolution(self):
        self.perm(self.a, "Whenever a noncreature source you control deals damage, you gain that much life.")
        for _ in range(3):
            self.game.enter_battlefield(self.b, BEAR)
        self.cast(self.a, SWEEP)
        self.assertEqual(self.a.life, 20 + 4)          # three Bears and the watcher itself, one trigger for 4
        self.assertEqual(sum("Test Watcher trigger resolves" in line for line in self.game.events), 1)
        bear = self.game.enter_battlefield(self.a, BEAR)
        self.game.deal_damage(self.b, 2, by=self.a, source=bear, combat=True)     # a creature: no life
        self.game.settle()
        self.assertEqual(self.a.life, 24)

    def test_red_creature_or_spell_hits_its_controller(self):
        self.perm(self.a, "Whenever a red creature or spell deals damage, ~ deals that much damage to that "
                          "creature's or spell's controller.", types="Enchantment", pt=(None, None))
        self.cast(self.b, BOLT, self.a)
        self.assertEqual((self.a.life, self.b.life), (17, 17))
        self.cast(self.b, FROST, self.a, land=ISLAND)                # blue: nothing
        self.assertEqual((self.a.life, self.b.life), (14, 17))
        goblin = self.game.enter_battlefield(self.b, card("Goblin", "{R}", "Creature — Goblin", "", 2, 1))
        self.game.deal_damage(self.a, 2, by=self.b, source=goblin, combat=True)
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (12, 15))

    def test_satyr_aims_at_a_creature_of_the_damaged_opponent(self):
        self.perm(self.a, "Whenever an instant or sorcery spell you control deals damage to an opponent, ~ deals "
                          "that much damage to target creature that player controls.", pt=(1, 1))
        small = self.game.enter_battlefield(self.b, BEAR)
        big = self.game.enter_battlefield(self.b, card("Big", "{4}", "Creature — Giant", "", 5, 5))
        self.cast(self.a, BOLT, self.b)
        self.assertNotIn(small, self.b.battlefield)        # the one it kills
        self.assertEqual(big.damage, 0)

    def test_kusari_gama_hits_the_other_defenders(self):
        gama = self.perm(self.a, "Whenever equipped creature deals damage to a blocking creature, ~ deals that much "
                                 "damage to each other creature defending player controls.",
                         name="Test Gama", types="Artifact — Equipment", pt=(None, None))
        mine = self.game.enter_battlefield(self.a, card("Hero", "{2}", "Creature — Human", "", 2, 2))
        gama.attached_to = mine
        mine.equipment.append(gama)
        blocker = self.game.enter_battlefield(self.b, card("Wall", "{2}", "Creature — Wall", "", 0, 4))
        other = self.game.enter_battlefield(self.b, card("Other", "{2}", "Creature — Ogre", "", 3, 3))
        self.game.blocks = {mine: [blocker]}
        self.game.deal_damage(blocker, 2, by=self.a, source=mine, combat=True)
        self.game.settle()
        self.assertEqual((blocker.damage, other.damage), (2, 2))

    def test_greatbow_archer_hits_the_damaged_creatures_controller(self):
        self.perm(self.a, "Whenever an Archer you control deals damage to a creature, that Archer deals that much "
                          "damage to that creature's controller.", name="Doyen", types="Creature — Elf Archer")
        archer = self.game.enter_battlefield(self.a, card("Archer", "{1}", "Creature — Elf Archer", "", 1, 1))
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.game.deal_damage(bear, 1, by=self.a, source=archer)
        self.game.settle()
        self.assertEqual(self.b.life, 19)
        self.game.deal_damage(self.b, 1, by=self.a, source=archer)     # to a player: not "a creature"
        self.game.settle()
        self.assertEqual(self.b.life, 18)

    def test_flesh_reaver(self):
        reaver = self.perm(self.a, "Whenever ~ deals damage to a creature or opponent, ~ deals that much damage to "
                                   "you.", pt=(4, 4))
        self.game.deal_damage(self.b, 4, by=self.a, source=reaver, combat=True)
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (16, 16))


@unittest.skipUnless(os.path.exists(DB), "card database not built")
class RealCards(unittest.TestCase):
    def test_wrathful_raptors_aim_away_from_dinosaurs(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 1, "main1"
        raptors = game.enter_battlefield(a, db.get("Wrathful Raptors"))
        dino = game.enter_battlefield(b, card("Dino", "{1}", "Creature — Dinosaur", "", 1, 1))
        bear = game.enter_battlefield(b, BEAR)
        game.deal_damage(raptors, 2, by=b, source=dino)
        game.settle()
        self.assertNotIn(bear, b.battlefield)                # a 2/2 it kills, not the Dinosaur
        self.assertIn(dino, b.battlefield)

    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.database_coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Tephraderm", "Flesh Reaver", "Tamanoa", "Justice", "Satyr Firedancer", "Kusari-Gama",
                     "Greatbow Doyen", "Wrathful Raptors"):
            self.assertEqual(card_coverage(db.get(name)).ignored, [], name)


if __name__ == "__main__":
    unittest.main()

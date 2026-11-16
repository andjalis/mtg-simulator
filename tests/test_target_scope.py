"""'target <np> that player controls' / 'defending player controls' (#338): the selector's scope is the trigger's
player or the player the source attacks (permanent_templates.scope_player), "opp" where it can't be told."""
import os
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from mtgsim.permanent_templates import selector
from tests.test_combat_triggers import BEAR, Scripted
from tests.test_templates import ISLAND, MOUNTAIN, card

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None
ANY_CAST = card("Test Judge", "{2}{B}", "Enchantment",
                "Whenever a player casts a creature spell, return target creature that player controls to its owner's "
                "hand.")


class Parse(unittest.TestCase):
    def test_selector(self):
        self.assertEqual(selector("creature that player controls"),
                         {"scope": "that_player", "controller": "opp", "types_all": ["creature"]})
        self.assertEqual(selector("artifact defending player controls")["scope"], "defending")
        self.assertIsNone(selector("creature that player controls you control"))
        self.assertEqual(ANY_CAST.unsupported, [])


class Games(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 3, "main1", 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def test_that_player_is_the_caster_even_when_it_is_you(self):
        self.put(self.a, ANY_CAST)
        mine, theirs = self.put(self.a, BEAR), self.put(self.b, BEAR)
        goblin = card("Test Goblin", "{R}", "Creature — Goblin", "", 1, 1)
        self.game.enter_battlefield(self.a, MOUNTAIN).tapped = False
        self.a.hand = [goblin]
        self.assertTrue(self.game.cast(self.a, goblin, []))
        self.game.settle()
        self.assertIn(theirs, self.b.battlefield)               # a cast it: the bounce is aimed at a's creature
        self.assertNotIn(mine, self.a.battlefield)

    def test_that_player_is_the_targeted_player_of_the_same_ability(self):
        from mtgsim.engine.state import StackItem
        c = card("Test Hex", "{B}", "Sorcery", "Target player loses 2 life. Tap target creature that player controls.")
        self.assertEqual(c.unsupported, [])
        mine, theirs = self.put(self.a, BEAR), self.put(self.b, BEAR)
        tap = c.spell_effects[-1]
        with self.game.targeting(StackItem(self.a, c.spell_effects, [self.a, None], card=c, kind="spell")):
            legal = self.game.legal_targets(self.a, tap)
        self.assertIn(mine, legal)
        self.assertNotIn(theirs, legal)

    @unittest.skipUnless(HAVE_DB, "card database not built")
    def test_full(self):
        for n in ("Arm with Aether", "Storm the Citadel", "Mistblade Shinobi", "Ancient Hellkite", "Silumgar, the "
                  "Drifting Death", "Commando Raid", "Riptide Entrancer"):
            self.assertEqual(DB.get(n).unsupported, [], n)

    @unittest.skipUnless(HAVE_DB, "card database not built")
    def test_mistblade_bounces_the_damaged_players_creature(self):
        shinobi = self.put(self.a, DB.get("Mistblade Shinobi"))
        mine, theirs = self.put(self.a, BEAR), self.put(self.b, BEAR)
        self.a.ai = type("Yes", (Scripted,), {"choose_yes": lambda *a, **k: True})()
        self.a.ai.attack, self.a.ai.block = [shinobi], {}
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)

    @unittest.skipUnless(HAVE_DB, "card database not built")
    def test_defending_player_from_an_attacking_source(self):
        hellkite = self.put(self.a, DB.get("Ancient Hellkite"))
        mine, theirs = self.put(self.a, BEAR), self.put(self.b, BEAR)
        self.game.attackers = [hellkite]
        self.game.attack_targets = {hellkite: self.b}
        from mtgsim.engine.state import StackItem
        eff = next(a for a in hellkite.activated if a.effects and a.effects[0].kind == "damage").effects[0]
        with self.game.targeting(StackItem(self.a, [eff], [], source=hellkite, kind="ability")):
            legal = self.game.legal_targets(self.a, eff)
        self.assertIn(theirs, legal)
        self.assertNotIn(mine, legal)

    def test_defending_player_of_another_players_attacker(self):
        """'Whenever a creature attacks, you may have it deal 1 damage to each creature defending player controls':
        the defending player is the attacker's, not "an opponent" of the trigger's controller."""
        watch = card("Test Watch", "{2}", "Enchantment", "Whenever a creature attacks, you may have it deal 1 damage "
                     "to each creature defending player controls.")
        self.assertEqual(watch.unsupported, [])
        self.put(self.a, watch)
        mine = self.put(self.a, card("Test Elf", "{G}", "Creature — Elf", "", 1, 1))
        ogre = self.put(self.b, card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3))
        bystander = self.put(self.b, card("Test Imp", "{B}", "Creature — Imp", "", 1, 1))
        self.game.active_idx = 1
        self.b.ai.attack = [ogre]
        self.game.combat(self.b, self.a)
        self.game.settle()
        self.assertNotIn(mine, self.a.battlefield)          # a is the defending player: its Elf takes the 1
        self.assertIn(bystander, self.b.battlefield)        # the attacker's own side is untouched


if __name__ == "__main__":
    unittest.main()

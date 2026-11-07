"""cx_mech: Freerunning, Prowl, Web-slinging, Beam me up and Reinforce."""
import random
import unittest

from mtgsim import cx_mech
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, BEAR


class AltCasts(unittest.TestCase):
    def setUp(self):
        self.db = CardDB()
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def put(self, who, name):
        perm = self.game.enter_battlefield(who, name if not isinstance(name, str) else self.db.get(name))
        perm.sick = False
        self.game.settle()
        return perm

    def options(self, prefix):
        return [v for v in self.game.spell_options(self.a) if v.name.startswith(prefix)]

    def test_parse_clean(self):
        for n in ("Brotherhood Ambushers", "Chain Assassination", "Amazing Spider-Girl", "Adversary by Algorithm",
                  "Bannerhide Krushok"):
            self.assertEqual(self.db.get(n).unsupported, [], n)

    def test_freerunning_needs_an_assassin_hit(self):
        card = self.db.get("Brotherhood Ambushers")
        self.a.hand = [card]
        for _ in range(4):
            self.put(self.a, "Swamp")
        self.assertFalse(self.options("Brotherhood Ambushers (cond_alt"))
        cx_mech.note_hit(self.game, self.put(self.a, self.db.get("Altaïr Ibn-La'Ahad")))
        (v,) = self.options("Brotherhood Ambushers (cond_alt")
        self.assertEqual(v.mana_cost, card.alt_costs[0].cost)

    def test_hit_by_a_non_assassin_does_not_count(self):
        self.a.hand = [self.db.get("Brotherhood Ambushers")]
        self.put(self.a, "Swamp")
        cx_mech.note_hit(self.game, self.put(self.a, BEAR))
        self.assertFalse(self.options("Brotherhood Ambushers (cond_alt"))

    def test_web_slinging_returns_a_tapped_creature(self):
        card = self.db.get("Amazing Spider-Girl")
        self.a.hand = [card]
        for land in ("Plains", "Plains", "Plains"):
            self.put(self.a, land)
        bear = self.put(self.a, BEAR)
        self.assertFalse(self.options("Amazing Spider-Girl (cond_alt"))     # nothing tapped to return
        bear.tapped = True
        (v,) = self.options("Amazing Spider-Girl (cond_alt")
        self.assertTrue(self.game.cast(self.a, v))
        self.game.settle()
        self.assertIn(BEAR, self.a.hand)
        self.assertTrue(any(x.card.name == "Amazing Spider-Girl" for x in self.a.battlefield))

    def test_beam_me_up_casts_from_graveyard_and_exiles(self):
        card = self.db.get("Adversary by Algorithm")
        self.a.graveyard = [card]
        for land in ("Forest",) * 4:
            self.put(self.a, land)
        self.assertFalse(self.options("Adversary by Algorithm (beam"))     # no creature to return
        self.put(self.a, BEAR)
        (v,) = self.options("Adversary by Algorithm (beam")
        self.assertTrue(self.game.cast(self.a, v))
        self.game.settle()
        self.assertIn(BEAR, self.a.hand)
        self.assertIn(card, self.a.exile)
        self.assertNotIn(card, self.a.graveyard)
        self.assertTrue(any(x.card.is_token for x in self.a.battlefield))

    def test_reinforce_discards_for_counters(self):
        card = self.db.get("Bannerhide Krushok")
        self.a.hand = [card]
        for land in ("Forest", "Forest"):
            self.put(self.a, land)
        bear = self.put(self.a, BEAR)
        (v,) = self.options("Bannerhide Krushok (channel")
        self.assertTrue(self.game.cast(self.a, v))
        self.game.settle()
        self.assertEqual(bear.counters.get("+1/+1"), 2)
        self.assertIn(card, self.a.graveyard)

    def test_recover_pays_to_return_or_exiles(self):
        for paid in (True, False):
            self.setUp()
            card = self.db.get("Grim Harvest")
            self.a.graveyard = [card]
            if paid:
                for land in ("Swamp",) * 3:
                    self.put(self.a, land)
            victim = self.put(self.a, BEAR)
            self.game.dies(victim)
            self.game.settle()
            self.assertIn(card, self.a.hand if paid else self.a.exile, paid)
            self.assertNotIn(card, self.a.graveyard)


class AiUse(unittest.TestCase):
    """The default AI (HeuristicAI) finds and uses each new cast option on its own."""

    def setUp(self):
        from mtgsim.ai import HeuristicAI
        self.db = CardDB()
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def put(self, who, name):
        perm = self.game.enter_battlefield(who, name if not isinstance(name, str) else self.db.get(name))
        perm.sick = False
        self.game.settle()
        return perm

    def test_ai_casts_a_prowl_card_for_its_prowl_cost_after_a_hit(self):
        card = self.db.get("Enigma Thief")        # prowl {3}{U}; {5}{U}{U} to cast normally
        self.a.hand = [card]
        for _ in range(4):
            self.put(self.a, "Island")
        self.game.main_phase(self.a)
        self.assertFalse(any(x.card.name == "Enigma Thief" for x in self.a.battlefield))   # no hit yet
        cx_mech.note_hit(self.game, self.put(self.a, "Thieves' Guild Enforcer"))
        self.game.main_phase(self.a)
        self.assertTrue(any(x.card.name == "Enigma Thief" for x in self.a.battlefield))

    def test_ai_casts_beam_me_up_from_the_graveyard(self):
        card = self.db.get("Adversary by Algorithm")
        self.a.graveyard = [card]
        for _ in range(4):
            self.put(self.a, "Forest")
        self.put(self.a, BEAR)
        self.game.main_phase(self.a)
        self.assertIn(card, self.a.exile)
        self.assertTrue(any(x.card.is_token for x in self.a.battlefield))

    def test_ai_player_recovers_a_card_when_its_creature_dies(self):
        card = self.db.get("Grim Harvest")
        self.a.graveyard = [card]
        for _ in range(3):
            self.put(self.a, "Swamp")
        victim = self.put(self.a, BEAR)
        self.game.dies(victim)
        self.game.settle()
        self.assertIn(card, self.a.hand)

    def test_ai_uses_reinforce_from_hand(self):
        card = self.db.get("Bannerhide Krushok")
        self.a.hand = [card]
        for _ in range(2):
            self.put(self.a, "Forest")
        bear = self.put(self.a, BEAR)
        self.game.step = "main2"
        self.game.main_phase(self.a)
        self.assertEqual(bear.counters.get("+1/+1"), 2)
        self.assertIn(card, self.a.graveyard)


if __name__ == "__main__":
    unittest.main()

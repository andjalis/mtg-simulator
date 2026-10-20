"""The legend rule (704.5j) as a state-based action, and legendary-aware copy targets, with real cards."""
import random
import unittest
from pathlib import Path

from mtgsim import copies
from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Permanent, Player

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class LegendRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def card(self, name):
        return self.db.get(name)

    def setUp(self):
        island = self.card("Island")
        self.a = Player("a", [island] * 10, HeuristicAI())
        self.b = Player("b", [island] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [island] * 20

    def perm(self, name_or_card, owner, sick=False):
        c = self.card(name_or_card) if isinstance(name_or_card, str) else name_or_card
        p = Permanent(c, owner)
        p.sick, p.tapped = sick, False
        owner.battlefield.append(p)
        return p

    def lands(self, owner, name, n):
        for _ in range(n):
            self.perm(name, owner)

    def cast(self, owner, name):
        c = self.card(name)
        owner.hand.append(c)
        self.assertTrue(self.game.cast(owner, c))
        self.game.run_priority()

    def named(self, owner, name):
        return [x for x in owner.battlefield if x.card.name == name]

    # ------------------------------------------------------------------ copy targets

    def test_fits_reads_permanent_legendary_and_nonlegendary(self):
        isamaru, bear = self.card("Isamaru, Hound of Konda"), self.card("Grizzly Bears")
        self.assertFalse(copies.fits(isamaru, "nonlegendary creature"))
        self.assertTrue(copies.fits(bear, "nonlegendary creature"))
        self.assertTrue(copies.fits(isamaru, "legendary creature"))
        self.assertFalse(copies.fits(bear, "legendary creature"))
        self.assertTrue(copies.fits(bear, "permanent"))
        self.assertFalse(copies.fits(self.card("Lightning Bolt"), "permanent"))

    def test_kiki_jiki_cannot_copy_a_legendary_creature(self):
        kiki = self.perm("Kiki-Jiki, Mirror Breaker", self.a)
        self.perm("Isamaru, Hound of Konda", self.a)
        eff = kiki.card.activated[0].effects[0]
        self.assertEqual(copies.candidates(self.game, self.a, eff, kiki), [])
        bear = self.perm("Grizzly Bears", self.a)
        self.assertEqual(copies.candidates(self.game, self.a, eff, kiki), [bear])

    # ------------------------------------------------------------------ the rule itself

    def test_second_copy_goes_to_graveyard_and_death_trigger_fires(self):
        kept = self.perm("Kokusho, the Evening Star", self.a)
        kept.counters["+1/+1"] = 1
        new = self.perm("Kokusho, the Evening Star", self.a, sick=True)
        self.game.state_based_actions()
        self.assertEqual(self.named(self.a, "Kokusho, the Evening Star"), [kept])
        self.assertIn(new.front, self.a.graveyard)
        self.game.run_priority()
        self.assertEqual(self.b.life, 15)       # Kokusho's dies trigger drained 5

    def test_indestructible_does_not_help(self):
        first = self.perm("Avacyn, Angel of Hope", self.a)
        self.perm("Avacyn, Angel of Hope", self.a, sick=True)
        self.game.state_based_actions()
        self.assertEqual(self.named(self.a, "Avacyn, Angel of Hope"), [first])
        self.assertEqual([c.name for c in self.a.graveyard], ["Avacyn, Angel of Hope"])

    def test_noncreature_legendary_permanents(self):
        self.perm("Esika's Chariot", self.a)
        self.perm("Esika's Chariot", self.a)
        self.game.state_based_actions()
        self.assertEqual(len(self.named(self.a, "Esika's Chariot")), 1)
        self.assertEqual(len(self.a.graveyard), 1)

    def test_each_player_may_control_one(self):
        self.perm("Isamaru, Hound of Konda", self.a)
        self.perm("Isamaru, Hound of Konda", self.b)
        self.game.state_based_actions()
        self.assertEqual(len(self.named(self.a, "Isamaru, Hound of Konda")), 1)
        self.assertEqual(len(self.named(self.b, "Isamaru, Hound of Konda")), 1)

    def test_different_names_and_nonlegendary_duplicates_stay(self):
        self.perm("Isamaru, Hound of Konda", self.a)
        self.perm("Kokusho, the Evening Star", self.a)
        self.perm("Grizzly Bears", self.a)
        self.perm("Grizzly Bears", self.a)
        self.game.state_based_actions()
        self.assertEqual(len(self.a.battlefield), 4)

    def test_token_copy_is_legendary_and_ceases_to_exist(self):
        original = self.perm("Isamaru, Hound of Konda", self.a)
        self.lands(self.a, "Island", 3)
        self.cast(self.a, "Cackling Counterpart")
        self.assertEqual(self.named(self.a, "Isamaru, Hound of Konda"), [original])   # untapped, not sick: kept
        self.assertEqual([c.name for c in self.a.graveyard], ["Cackling Counterpart"])  # the token left no card

    def test_copy_that_isnt_legendary_is_exempt(self):
        self.perm("Isamaru, Hound of Konda", self.a)
        self.lands(self.a, "Island", 5)
        self.cast(self.a, "Quantum Misalignment")
        both = self.named(self.a, "Isamaru, Hound of Konda")
        self.assertEqual(len(both), 2)
        self.assertEqual(sorted(x.card.legendary for x in both), [False, True])

    def test_clone_that_becomes_legendary(self):
        original = self.perm("Isamaru, Hound of Konda", self.a)
        self.lands(self.a, "Island", 4)
        self.cast(self.a, "Clone")
        self.assertEqual(self.named(self.a, "Isamaru, Hound of Konda"), [original])
        self.assertIn("Clone", [c.name for c in self.a.graveyard])     # the Clone card, not the copy

    def test_opponents_legend_cloned_does_not_interact(self):
        self.perm("Isamaru, Hound of Konda", self.b)
        self.lands(self.a, "Island", 4)
        self.cast(self.a, "Clone")
        self.assertEqual(len(self.named(self.a, "Isamaru, Hound of Konda")), 1)
        self.assertEqual(len(self.named(self.b, "Isamaru, Hound of Konda")), 1)

    def test_transformed_faces_use_their_current_name(self):
        front = self.perm("Jace, Vryn's Prodigy", self.a)
        back = self.perm("Jace, Vryn's Prodigy", self.a)
        back.counters["loyalty"] = 5
        self.game.transform(back)
        self.game.state_based_actions()
        self.assertEqual(len(self.a.battlefield), 2)        # Jace, Vryn's Prodigy and Jace, Telepath Unbound
        self.game.transform(front)
        front.counters["loyalty"] = 2
        self.game.state_based_actions()
        self.assertEqual(self.a.battlefield, [back])        # more loyalty kept
        self.assertEqual([c.name for c in self.a.graveyard], ["Jace, Vryn's Prodigy"])   # front face card

    def test_default_keeps_the_most_valuable(self):
        tapped = self.perm("Isamaru, Hound of Konda", self.a)
        tapped.tapped = True
        sick = self.perm("Isamaru, Hound of Konda", self.a, sick=True)
        ready = self.perm("Isamaru, Hound of Konda", self.a)
        self.game.state_based_actions()
        self.assertEqual(self.named(self.a, "Isamaru, Hound of Konda"), [ready])
        self.assertEqual(len(self.a.graveyard), 2)
        self.assertNotIn(tapped, self.a.battlefield)
        self.assertNotIn(sick, self.a.battlefield)

    def test_choice_hook_is_overridable(self):
        first = self.perm("Isamaru, Hound of Konda", self.a)
        first.counters["+1/+1"] = 3
        second = self.perm("Isamaru, Hound of Konda", self.a)
        seen = []
        self.a.ai.choose_legend = lambda game, me, perms: seen.append(list(perms)) or perms[-1]
        self.game.state_based_actions()
        self.assertEqual(seen, [[first, second]])
        self.assertEqual(self.named(self.a, "Isamaru, Hound of Konda"), [second])

    # ------------------------------------------------------------------ exemptions

    def test_mirror_gallery_exempts_everyone(self):
        self.perm("Mirror Gallery", self.b)
        self.perm("Isamaru, Hound of Konda", self.a)
        self.perm("Isamaru, Hound of Konda", self.a)
        self.game.state_based_actions()
        self.assertEqual(len(self.named(self.a, "Isamaru, Hound of Konda")), 2)

    def test_scoped_exemption_only_for_its_controller_and_kind(self):
        self.assertEqual(self.card("The Master, Multiplied").legend_exempt, "creature token")
        self.perm("Council of Reeds", self.a)     # creatures you control
        for p in (self.a, self.b):
            self.perm("Esika's Chariot", p)
            self.perm("Esika's Chariot", p)
            self.perm("Isamaru, Hound of Konda", p)
            self.perm("Isamaru, Hound of Konda", p)
        self.game.state_based_actions()
        self.assertEqual(len(self.named(self.a, "Isamaru, Hound of Konda")), 2)
        self.assertEqual(len(self.named(self.a, "Esika's Chariot")), 1)      # not a creature
        self.assertEqual(len(self.named(self.b, "Isamaru, Hound of Konda")), 1)

    def test_hall_of_echoes_turns_the_rule_off_this_turn(self):
        hall = self.perm("Hall of Echoes", self.a)
        self.assertEqual(hall.card.unsupported, [])
        self.perm("Isamaru, Hound of Konda", self.a)
        self.lands(self.a, "Island", 5)
        self.assertTrue(self.game.activate_ability(self.a, hall, 0))
        self.game.run_priority()
        self.assertEqual(len(self.named(self.a, "Isamaru, Hound of Konda")), 2)
        self.game.turn += 1                          # next turn, before cleanup reverts it
        self.game.state_based_actions()
        self.assertEqual(len(self.named(self.a, "Isamaru, Hound of Konda")), 1)


if __name__ == "__main__":
    unittest.main()

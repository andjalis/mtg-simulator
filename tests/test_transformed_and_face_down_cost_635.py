"""#635: the "transformed" selector trait (Mutagen Connoisseur) and face-down cost reductions (Dream Chisel, Obscuring
Aether, Kadena)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


class Parse(unittest.TestCase):
    def test_selector_and_discounts(self):
        from mtgsim.permanent_templates import selector
        self.assertEqual(selector("transformed permanent you control")["traits"], ["transformed"])
        self.assertEqual(db("Dream Chisel").cost_discount, (("face_down", 1),))
        self.assertEqual(db("Kadena, Slinking Sorcerer").cost_discount, (("face_down_first", 3),))

    def test_refusals(self):
        # a discount only "this turn" (Goblin Maskmaker) or for "the next" spell (Panoptic Projektor): not read
        for name in ("Goblin Maskmaker", "Panoptic Projektor", "Oculus Whelp"):
            self.assertFalse(db(name).fully_supported, name)
        # "face-down" in other templates' descriptions is untouched (Cryptid Inspector stays full)
        self.assertTrue(db("Cryptid Inspector").fully_supported)

    def test_real_cards_full(self):
        for name in ("Dream Chisel", "Kadena, Slinking Sorcerer", "Mutagen Connoisseur", "Obscuring Aether"):
            self.assertTrue(db(name).fully_supported, name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Game_(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def put(self, p, name):
        x = self.game.enter_battlefield(p, db(name))
        self.game.settle()
        return x

    def test_mutagen_counts_my_transformed_permanents(self):
        mutagen = self.put(self.a, "Mutagen Connoisseur")
        mine = self.put(self.a, "Geier Reach Bandit // Vildin-Pack Alpha")
        self.assertEqual(mutagen.power, 0)
        self.game.transform(mine)
        self.assertEqual(mutagen.power, 1)
        theirs = self.put(self.b, "Geier Reach Bandit // Vildin-Pack Alpha")
        self.game.transform(theirs)
        self.assertEqual(mutagen.power, 1)              # theirs doesn't count
        self.game.transform(mine)
        self.assertEqual(mutagen.power, 0)              # front face up again

    def face_down_costs(self):
        return [self.game.cost_of(self.a, o) for o in self.game.spell_options(self.a) if "morph" in o.name.lower()]

    def test_dream_chisel_only_face_down(self):
        self.put(self.a, "Dream Chisel")
        self.a.hand = [db("Skinthinner")]
        costs = {o.name: self.game.cost_of(self.a, o) for o in self.game.spell_options(self.a)}
        self.assertEqual(costs["Skinthinner (morph)"], {"generic": 2})
        self.assertEqual(costs["Skinthinner"], {"generic": 1, "B": 1})

    def test_kadena_first_face_down_spell_each_turn(self):
        self.put(self.a, "Kadena, Slinking Sorcerer")
        self.a.hand = [db("Skinthinner"), db("Skinthinner")]
        self.assertEqual(self.face_down_costs()[0], {"generic": 0})
        first = next(o for o in self.game.spell_options(self.a) if "morph" in o.name.lower())
        self.assertTrue(self.game.cast(self.a, first))
        self.game.settle()
        self.assertEqual(self.face_down_costs()[0], {"generic": 3})
        self.game.turn += 1
        self.assertEqual(self.face_down_costs()[0], {"generic": 0})     # a new turn

    def manifest(self, p):
        from mtgsim.manifest import manifest_one
        perm = manifest_one(self.game, p)
        self.game.settle()
        return perm

    def test_kadena_draws_for_my_face_down_entries(self):
        """opus-refs on #805: 'whenever a face-down creature you control enters' never fired; the creature now
        enters face down instead of being turned down after its enters events."""
        self.put(self.a, "Kadena, Slinking Sorcerer")
        self.a.hand = [db("Skinthinner")]
        morph = next(o for o in self.game.spell_options(self.a) if "morph" in o.name.lower())
        self.assertTrue(self.game.cast(self.a, morph))
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)                            # cast face down: draw one
        self.assertIsNotNone(self.manifest(self.a).hidden)
        self.assertEqual(len(self.a.hand), 2)                            # manifested: another
        self.manifest(self.b)
        self.put(self.a, "Grizzly Bears")
        self.assertEqual(len(self.a.hand), 2)                            # not theirs, not a face-up creature

    def test_face_down_morph_has_no_enters_ability(self):
        from tests.test_templates import card
        morpher = card("T Morpher", "{4}{U}", "Creature — Shapeshifter", "When this creature enters, draw a card.\n"
                       "Morph {U}", 3, 3)
        for _ in range(3):
            self.put(self.a, "Island")
        self.a.hand = [morpher]
        morph = next(o for o in self.game.spell_options(self.a) if self.game._origin(o)[1] == "morph")
        self.assertTrue(self.game.cast(self.a, morph))
        self.game.settle()
        perm = next(x for x in self.a.battlefield if x.hidden is not None)
        self.assertEqual((perm.card.name, perm.power), ("Face-down creature", 2))
        self.assertEqual(self.a.hand, [])                                 # its own "when this enters" didn't trigger
        self.game.destroy(perm)
        self.game.settle()
        self.assertEqual([c.name for c in self.a.graveyard], ["T Morpher"])   # the real card goes to the graveyard

    def test_skirk_alarmist_sacrifices_it_at_the_end_step(self):
        """opus-refs on #805 (probable): the delayed sacrifice works when the ability gets a target per effect."""
        self.game.active_idx = 0
        self.a.my_turn, self.b.my_turn = True, False
        skirk = self.put(self.a, "Skirk Alarmist")
        skirk.sick = False
        down = self.manifest(self.a)
        self.assertTrue(self.game.activate_ability(self.a, skirk, 0))    # targets chosen by the engine
        self.game.settle()
        self.assertIsNone(down.hidden)
        self.game.begin_end_step(self.a)
        self.game.settle()
        self.assertNotIn(down, self.a.battlefield)


if __name__ == "__main__":
    unittest.main()

"""#324 tail: quantities of the mana spent to cast a spell. "for each color of mana spent to cast ~" (converge)
on tokens, "the amount of mana spent to cast ~ / that spell", "~ enters with N counters on it for each [color
of] mana spent to cast it" / "equal to the amount of mana spent to cast it", and "target ... if its mana value
is less than or equal to the number of colors of mana spent to cast ~" (checked against the effect's target)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, PLAINS, SWAMP, card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
BOLT = card("Test Bolt", "{1}{R}", "Instant", "Test Bolt deals 1 damage to any target.")
ONE_DROP = card("Test Relic", "{1}", "Artifact", "")
FIVE_DROP = card("Test Colossus", "{5}", "Artifact Creature — Golem", "", 5, 5)


class ManaSpentQuantities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    @classmethod
    def tearDownClass(cls):
        if cls.db._all is not None:
            cls.db._all.close()

    def real(self, name):
        if self.db._all is None:
            self.skipTest("card database not built")
        return self.db.get(name)

    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick = p.tapped = False
        owner.battlefield.append(p)
        return p

    def lands(self, *cards):
        for c in cards:
            self.perm(c, self.a)

    def cast(self, c, targets=None):
        self.a.hand = [c]
        self.assertTrue(self.g.cast(self.a, c, targets))
        self.g.settle()

    def spell(self, c, spent, colours, x=0, targets=None):
        """Resolve c as a spell whose payment was `spent` mana (X excluded) of `colours`."""
        effects = list(c.spell_effects)
        item = StackItem(self.a, effects, targets or [None] * len(effects), card=c)
        item.mana_spent, item.x, item.mana_colors = spent, x, set(colours)
        self.g.stack.append(item)
        self.g.resolve_top()
        self.g.settle()

    # parser
    def test_real_cards_are_full(self):
        for name in ("Sweep the Skies", "Unified Front", "Molten Note", "Verazol, the Split Current", "The Spike Cactus",
                     "Glinting Creeper", "Prism Array", "Manaform Hellkite", "Grandmother Goby", "Magmablood Archaic",
                     "Uncover the Moon-Letters", "Prismatic Ending", "Exert Influence"):
            with self.subTest(card=name):
                self.assertEqual(self.real(name).unsupported, [])

    def test_quantities(self):
        for text, spec in (("Draw X cards, where X is the amount of mana spent to cast ~.", ("cxq", "mana_amount")),
                           ("Create a 1/1 white Soldier creature token for each color of mana spent to cast ~.",
                            ("cxq", "converge"))):
            with self.subTest(text=text):
                effects, bad = _parse_effects(text)
                self.assertFalse(bad)
                self.assertEqual(effects[-1].data.get("xq"), spec)

    def test_near_misses_refused(self):
        for text in ("Draw X cards, where X is the amount of mana spent to cast another spell.",
                     "Exile target nonland permanent if its mana value is less than or equal to the number of "
                     "creatures you control.",
                     "~ enters with a +1/+1 counter on it for each mana spent to cast another spell."):
            with self.subTest(text=text):
                effects, bad = _parse_effects(text)
                self.assertTrue(bad, effects)

    # spells
    def test_unified_front_one_token_per_colour(self):
        self.spell(self.real("Unified Front"), 4, "WUB")
        self.assertEqual(len([x for x in self.a.creatures if x.card.is_token]), 3)

    def test_sweep_the_skies_counts_colours_not_mana(self):
        self.spell(self.real("Sweep the Skies"), 2, "U", x=3)
        self.assertEqual(len([x for x in self.a.creatures if x.card.is_token]), 1)

    def test_molten_note_damage_is_mana_spent_with_x(self):
        target = self.perm(card("Big", "{4}", "Creature — Giant", "", 9, 9), self.b)
        note = self.real("Molten Note")
        self.spell(note, 2, "RW", x=3, targets=[target] + [None] * (len(note.spell_effects) - 1))
        self.assertEqual(target.damage, 5)

    def test_copy_spent_nothing(self):
        target = self.perm(card("Big", "{4}", "Creature — Giant", "", 9, 9), self.b)
        note = self.real("Molten Note")
        effects = list(note.spell_effects)
        item = StackItem(self.a, effects, [target] + [None] * (len(effects) - 1), card=note, kind="copy")
        item.mana_spent, item.x = 2, 3
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertEqual(target.damage, 0)

    # entering permanents
    def test_spike_cactus_counters_equal_mana_spent(self):
        self.lands(FOREST, FOREST, FOREST)
        cactus = self.real("The Spike Cactus")
        self.cast(cactus)
        perm = [x for x in self.a.creatures if x.card.name == cactus.name][0]
        self.assertEqual(perm.counters.get("+1/+1", 0), 3)

    def test_glinting_creeper_two_per_colour(self):
        self.lands(FOREST, ISLAND, MOUNTAIN, PLAINS, SWAMP)
        creeper = self.real("Glinting Creeper")
        self.cast(creeper)
        perm = [x for x in self.a.creatures if x.card.name == creeper.name][0]
        self.assertEqual(perm.counters.get("+1/+1", 0), 10)

    def test_prism_array_crystal_counters(self):
        self.lands(ISLAND, ISLAND, ISLAND, MOUNTAIN, FOREST)
        array = self.real("Prism Array")
        self.cast(array)
        perm = [x for x in self.a.battlefield if x.card.name == array.name][0]
        self.assertEqual(perm.counters.get("crystal", 0), 3)

    def test_not_cast_gets_no_counters(self):
        perm = self.g.enter_battlefield(self.a, self.real("The Spike Cactus"))
        self.g.settle()
        self.assertEqual(perm.counters.get("+1/+1", 0), 0)

    # cast triggers: "that spell"
    def test_manaform_hellkite_token_size_is_spells_mana(self):
        self.perm(self.real("Manaform Hellkite"), self.a)
        self.lands(MOUNTAIN, MOUNTAIN)
        self.cast(BOLT, [self.b])
        dragons = [x for x in self.a.creatures if x.card.is_token]
        self.assertEqual([(x.power, x.toughness) for x in dragons], [(2, 2)])

    def test_magmablood_counts_that_spells_colours(self):
        archaic = self.perm(self.real("Magmablood Archaic"), self.a)
        self.lands(MOUNTAIN, ISLAND)
        self.cast(BOLT, [self.b])
        self.assertEqual(archaic.power - archaic.card.power, 2)

    # Prismatic Ending: the target against the spell's colours
    def test_prismatic_ending_exiles_within_converge(self):
        ending = self.real("Prismatic Ending")
        relic = self.perm(ONE_DROP, self.b)
        self.spell(ending, 1, "W", x=1, targets=[relic])
        self.assertNotIn(relic, self.b.battlefield)

    def test_prismatic_ending_too_expensive_target_stays(self):
        ending = self.real("Prismatic Ending")
        colossus = self.perm(FIVE_DROP, self.b)
        self.spell(ending, 1, "WU", x=1, targets=[colossus])
        self.assertIn(colossus, self.b.battlefield)

    def test_ai_aims_prismatic_ending_at_a_reachable_opponent_permanent(self):
        ending = self.real("Prismatic Ending")
        relic, colossus = self.perm(ONE_DROP, self.b), self.perm(FIVE_DROP, self.b)
        self.perm(card("Mine", "{1}", "Artifact", ""), self.a)
        self.lands(PLAINS, PLAINS)
        eff = ending.spell_effects[0]
        with self.g.targeting(ending):
            self.g.target_source = ending
            tgt = self.a.ai.choose_target(self.g, self.a, eff, ending)
        self.assertIs(tgt, relic)       # one colour available: the 5-drop is out of reach
        self.assertIsNot(tgt, colossus)


if __name__ == "__main__":
    unittest.main()

"""Copy effects (mtgsim.copies): token copies, clones, and copies of spells. Card text is written out
so the tests don't need the card DB."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, _mode_value

from tests.test_templates import BEAR, DRAGON3, ISLAND, MOUNTAIN, SHOCK, card

KIKI = card("Kiki Copy", "{2}{R}", "Creature — Goblin", (
    "{4}{R}{R}, {T}: Create a token that's a copy of target creature you control. It gains haste. Sacrifice it at "
    "the beginning of the next end step."), 2, 2)
TWIN = card("Twinning", "{2}{U}", "Sorcery", (
    "Create a token that's a copy of target creature you control, except it's a 1/1 Mirror in addition to its "
    "other types and it has flying."))
SPLIT = card("Self Splitter", "{3}{G}", "Creature — Ooze", (
    "{2}: Create a token that's a copy of this creature, except it isn't legendary."), 2, 2)
CLONE = card("Test Clone", "{3}{U}", "Creature — Shapeshifter", (
    "You may have Test Clone enter as a copy of any creature on the battlefield."), 0, 0)
MIRRORS = card("Hall of Mirrors", "{4}{U}", "Sorcery", (
    "For each nontoken creature you control, create a token that's a copy of that creature."))
STORM = card("Double Cast", "{R}", "Instant", (
    "When you next cast an instant or sorcery spell this turn, copy that spell. You may choose new targets "
    "for the copy."))
ECHO = card("Echo Bolt", "{1}{R}", "Instant", (
    "When you cast this spell, if you've cast another spell this turn, copy it. You may choose new targets "
    "for the copy.\nEcho Bolt deals 2 damage to any target."))


class CopyTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def test_templates_match(self):
        for c in (KIKI, TWIN, SPLIT, CLONE, MIRRORS, STORM, ECHO):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual(CLONE.clone["who"], "any")
        self.assertEqual(KIKI.activated[0].effects[0].data["mods"], {"keywords": frozenset({"haste"}), "sac_end": True})
        self.assertEqual(ECHO.cast_copy, {"cond": "another", "n": 1})

    def test_token_copy_with_changes(self):
        self.perm(DRAGON3, self.a)
        for _ in range(3):
            self.perm(ISLAND, self.a)
        self.a.hand = [TWIN]
        self.assertGreater(_mode_value(self.game, self.a, TWIN.spell_effects), 0)
        self.game.cast(self.a, TWIN)
        copy = [c for c in self.a.creatures if c.card.is_token]
        self.assertEqual(len(copy), 1)
        self.assertEqual((copy[0].card.name, copy[0].power, copy[0].toughness), ("Big Dragon", 1, 1))
        self.assertIn("Mirror", copy[0].card.subtypes)
        self.assertTrue(copy[0].has("flying"))

    def test_copy_spell_is_worthless_without_a_creature(self):
        self.assertLess(_mode_value(self.game, self.a, TWIN.spell_effects), 0)

    def test_kiki_token_has_haste_and_is_sacrificed_at_end_step(self):
        kiki = self.perm(KIKI, self.a)
        self.perm(DRAGON3, self.a)
        for _ in range(6):
            self.perm(MOUNTAIN, self.a)
        self.assertTrue(self.game.activate_ability(self.a, kiki, 0))
        tokens = [c for c in self.a.creatures if c.card.is_token]
        self.assertEqual([t.card.name for t in tokens], ["Big Dragon"])
        self.assertTrue(tokens[0].has("haste"))
        self.game.fire(self.a, "end_step")
        self.game.run_priority()
        self.assertEqual([c for c in self.a.creatures if c.card.is_token], [])
        self.assertEqual(self.a.graveyard, [])          # tokens don't go to the graveyard

    def test_self_copy_etb(self):
        src = self.perm(SPLIT, self.a)
        for _ in range(2):
            self.perm(ISLAND, self.a)
        self.assertTrue(self.game.activate_ability(self.a, src, 0))
        self.game.run_priority()
        self.assertEqual(sorted(c.card.is_token for c in self.a.creatures), [False, True])

    def test_clone_copies_the_best_creature_and_dies_as_itself(self):
        self.perm(BEAR, self.a)
        self.perm(DRAGON3, self.b)
        clone = self.game.enter_battlefield(self.a, CLONE)
        self.assertEqual((clone.card.name, clone.power), ("Big Dragon", 3))
        self.game.destroy(clone)
        self.assertEqual([c.name for c in self.a.graveyard], ["Test Clone"])

    def test_clone_with_nothing_to_copy_enters_as_itself(self):
        clone = self.game.enter_battlefield(self.a, CLONE)
        self.assertEqual(clone.card.name, "Test Clone")

    def test_for_each_nontoken_creature(self):
        self.perm(BEAR, self.a)
        self.perm(DRAGON3, self.a)
        for _ in range(5):
            self.perm(ISLAND, self.a)
        self.a.hand = [MIRRORS]
        self.game.cast(self.a, MIRRORS)
        self.assertEqual(sum(c.card.is_token for c in self.a.creatures), 2)

    def test_next_spell_is_copied(self):
        for _ in range(2):
            self.perm(MOUNTAIN, self.a)
        self.a.hand = [STORM, SHOCK]
        self.game.cast(self.a, STORM)
        self.game.cast(self.a, SHOCK, [self.b])
        self.assertEqual(self.b.life, 16)

    def test_cast_copy_needs_another_spell_first(self):
        for _ in range(5):
            self.perm(MOUNTAIN, self.a)
        self.a.hand = [ECHO, SHOCK, ECHO]
        self.game.cast(self.a, ECHO, [self.b])
        self.assertEqual(self.b.life, 18)               # first spell this turn: no copy
        self.game.cast(self.a, SHOCK, [self.b])
        self.game.cast(self.a, ECHO, [self.b])
        self.assertEqual(self.b.life, 12)               # 2 (Shock) + 2 + 2 (copy)


if __name__ == "__main__":
    unittest.main()

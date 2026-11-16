""""<draw / gain / lose> ... for each <permanent> destroyed this way" (#337): the shared quantity reader binds the count
to what the destroy just before it in the same resolution destroyed (Game state.note_this_way), summed over a group's
members and over directly consecutive destroy effects (Fracturing Gust), and only counting what really died."""
import unittest

from mtgsim.cx_grammar_quantity import quantity

from tests.test_cx_grammar import BEAR, DB_FILE, Base, card

ENCH = card("Test Charm", "{1}", "Enchantment", "")
ART = card("Test Trinket", "{1}", "Artifact", "")


class Parsing(unittest.TestCase):
    def test_quantity(self):
        self.assertEqual(quantity("the number of creatures destroyed this way"), ("this_way", "destroyed", "creature"))
        self.assertEqual(quantity("the number of permanents destroyed this way"),
                         ("this_way", "destroyed", "permanent"))
        for q in ("the number of creature cards destroyed this way", "the number of creatures exiled this way",
                  "the number of Goblins destroyed this way"):
            self.assertIsNone(quantity(q), q)

    def test_near_misses_stay_unsupported(self):
        for text in ("Destroy all creatures. You gain 1 life for each creature card destroyed this way.",
                     "Destroy all creatures. You gain 1 life for each Goblin destroyed this way."):
            self.assertNotEqual(card("Test Spell", "{1}", "Sorcery", text).unsupported, [], text)


class Resolving(Base):
    def test_life_for_each_creature_destroyed(self):
        c = self.spell("Destroy all creatures. You gain 1 life for each creature destroyed this way.", "Sorcery")
        self.perm(BEAR, self.b), self.perm(BEAR, self.b), self.perm(BEAR, self.a)
        self.cast(c)
        self.assertEqual((self.a.life, self.b.life), (23, 20))

    def test_nothing_destroyed_is_zero(self):
        c = self.spell("Destroy all creatures. Draw a card for each creature destroyed this way.", "Sorcery")
        hand = len(self.a.hand)
        self.cast(c)
        self.assertEqual(len(self.a.hand), hand)

    def test_indestructible_isnt_counted(self):
        c = self.spell("Destroy all creatures. Draw a card for each creature destroyed this way.", "Sorcery")
        self.perm(card("Test Wall", "{1}", "Creature — Wall", "Indestructible", 0, 4), self.b)
        self.perm(BEAR, self.b)
        hand = len(self.a.hand)
        self.cast(c)
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_selected_group_counts_only_its_members(self):
        c = self.spell("Destroy all creatures with power 3 or less. Draw a card for each creature destroyed this way.",
                       "Sorcery")
        self.perm(BEAR, self.b)
        big = self.perm(card("Test Giant", "{4}", "Creature — Giant", "", 5, 5), self.b)
        hand = len(self.a.hand)
        self.cast(c)
        self.assertIn(big, self.b.battlefield)
        self.assertEqual(len(self.a.hand), hand + 1)

    def test_lose_life_reads_the_caster(self):
        c = self.spell("Destroy all creatures. You lose 2 life for each creature destroyed this way.", "Sorcery")
        self.perm(BEAR, self.b), self.perm(BEAR, self.a)
        self.cast(c)
        self.assertEqual((self.a.life, self.b.life), (16, 20))

    def test_a_later_destroy_is_not_chained_through_another_effect(self):
        """Only directly consecutive destroys form one set: a draw in between ends the first one."""
        c = self.spell("Destroy target creature. Draw a card. Destroy target artifact. You gain 1 life for each "
                       "permanent destroyed this way.", "Sorcery")
        bear, trinket = self.perm(BEAR, self.b), self.perm(ART, self.b)
        targets = [bear if e.target in ("creature",) else trinket if e.target not in ("none",) else None
                   for e in c.spell_effects]
        self.cast(c, targets)
        self.assertEqual(self.a.life, 21)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def setUp(self):
        super().setUp()
        from mtgsim.carddb import CardDB
        self.db = CardDB()

    def test_cards_parse_fully(self):
        from mtgsim.coverage import FULL, card_coverage
        for name in ("Fumigate", "Decree of Pain", "Overwhelming Forces", "Death Begets Life", "Righteous Fury",
                     "Rain of Daggers", "Multani's Decree", "Paraselene", "Ori, Plate Stacker",
                     "Ob Nixilis, the Ascended", "Fracturing Gust"):
            row = card_coverage(self.db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))

    def test_fracturing_gust_counts_both_destroys(self):
        self.perm(ART, self.b), self.perm(ART, self.b), self.perm(ENCH, self.a)
        self.cast(self.db.get("Fracturing Gust"))
        self.assertEqual(self.a.life, 26)

    def test_death_begets_life_group(self):
        self.perm(BEAR, self.b), self.perm(ENCH, self.b), self.perm(BEAR, self.a)
        hand = len(self.a.hand)
        self.cast(self.db.get("Death Begets Life"))
        self.assertEqual(len(self.a.hand), hand + 3)

    def test_righteous_fury_only_tapped(self):
        self.perm(BEAR, self.b).tapped = True
        self.perm(BEAR, self.b)
        self.cast(self.db.get("Righteous Fury"))
        self.assertEqual(self.a.life, 22)

    def test_ai_casts_decree_of_pain_when_behind(self):
        decree = self.db.get("Decree of Pain")
        for _ in range(3):
            self.perm(card("Test Giant", "{4}", "Creature — Giant", "", 5, 5), self.b)
        for _ in range(8):
            self.perm(self.db.get("Swamp"), self.a)
        self.a.hand = [decree]
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(decree, self.a.hand, "the AI didn't cast it")
        self.assertEqual(self.b.creatures, [])
        self.assertEqual(len(self.a.hand), 3)


if __name__ == "__main__":
    unittest.main()

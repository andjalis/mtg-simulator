"""Color and mana-value references read the spell which caused a cast trigger."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Permanent, Player
from tests.test_templates import ISLAND, MOUNTAIN, card

CANNONS = card("Mana Cannons", "{R}", "Enchantment", "Whenever you cast a multicolored spell, this enchantment deals X damage to any target, where X is the number of colors that spell is.")
CRYSTAL = card("Crystal", "{3}{R}{W}", "Creature — Inhuman", "Whenever you cast a noncreature spell, Crystal deals X damage to each opponent, where X is the number of colors that spell is.", 4, 4)
KIRIN = card("Cloudhoof Kirin", "{3}{U}{U}", "Creature — Kirin Spirit", "Whenever you cast a Spirit or Arcane spell, you may have target player mill X cards, where X is that spell's mana value.", 4, 4)
DRAIN = card("Spinecrawler", "{4}{B}", "Creature — Horror", "Whenever you cast a multicolored spell, for each of that spell's colors, each opponent loses 1 life and you gain 1 life.", 4, 4)


class SpellColorQuantityTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 1, "main1"
        self.a.library, self.b.library = [ISLAND] * 20, [ISLAND] * 20
        for c in [ISLAND] * 6 + [MOUNTAIN] * 6:
            self.a.battlefield.append(Permanent(c, self.a))

    def host(self, c):
        p = Permanent(c, self.a)
        self.a.battlefield.append(p)
        return p

    def cast(self, c):
        self.a.hand = [c]
        self.assertTrue(self.game.cast(self.a, c))
        self.game.settle()

    def test_templates(self):
        for c in (CANNONS, CRYSTAL, KIRIN, DRAIN):
            self.assertEqual(c.unsupported, [], c.name)

    def test_damage_counts_spell_colors_instead_of_source_or_cost(self):
        self.host(CANNONS)
        self.cast(card("Color spell", "{3}{U}{R}", "Sorcery", "Draw a card."))
        self.assertEqual(self.b.life, 18)

    def test_colorless_noncreature_spell_causes_zero_damage(self):
        self.host(CRYSTAL)
        self.cast(card("Colorless", "{3}", "Artifact"))
        self.assertEqual(self.b.life, 20)

    def test_creature_spell_does_not_fire_noncreature_trigger(self):
        self.host(CRYSTAL)
        self.cast(card("Blue creature", "{U}", "Creature — Human", "", 1, 1))
        self.assertEqual(self.b.life, 20)

    def test_noncreature_damage_uses_one_spell_color(self):
        self.host(CRYSTAL)
        self.cast(card("Blue spell", "{4}{U}", "Sorcery", "Draw a card."))
        self.assertEqual(self.b.life, 19)

    def test_target_player_mills_triggering_spell_mana_value(self):
        self.host(KIRIN)
        self.cast(card("Arcane spell", "{2}{U}", "Sorcery — Arcane", "Draw a card."))
        self.assertEqual(len(self.b.library), 17)
        self.assertEqual(len(self.b.graveyard), 3)
        self.assertEqual(len(self.a.library), 19)

    def test_prefixed_color_count_scales_each_part_of_drain(self):
        self.host(DRAIN)
        self.cast(card("Two colors", "{U}{R}", "Sorcery", "Draw a card."))
        self.assertEqual((self.a.life, self.b.life), (22, 18))

    def test_mana_spent_color_counts_are_not_treated_as_spell_colors(self):
        c = card("Spent colors", "{2}", "Creature — Eldrazi", "Whenever you cast an instant or sorcery spell, creatures you control get +1/+0 until end of turn for each color of mana spent to cast that spell.", 2, 2)
        self.assertTrue(c.unsupported)

    def test_real_database_entries(self):
        db = CardDB(offline=True)
        if db._all is None:
            self.skipTest("offline card database is missing")
        for n in ("Mana Cannons", "Crystal, Inhuman Princess", "Cloudhoof Kirin"):
            self.assertEqual(db.get(n).unsupported, [], n)
        self.assertFalse(any("for each of that spell's colors" in s for s in db.get("Lurking Spinecrawler").unsupported))


if __name__ == "__main__":
    unittest.main()

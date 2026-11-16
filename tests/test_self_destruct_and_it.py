"""#320: Self-Destruct ("deals X damage to any other target and X damage to itself, where X is its power": two bites
of one recorded source) and a leading "It" in an activated ability (Myojin of Roaring Blades)."""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem

from tests.test_cx_grammar import BEAR, DB_FILE, ISLAND, Base, card

LINE = ("Target creature you control deals X damage to any other target and X damage to itself, where X is its power.")
GOLEM = card("Test Golem", "{3}", "Artifact Creature — Golem", "", 3, 5)


class Parsing(unittest.TestCase):
    def test_self_destruct_shape(self):
        effs, bad = _parse_effects(LINE)
        self.assertEqual((bad, [e.kind for e in effs]), ([], ["bite_src", "ref_bite", "ref_bite"]))
        self.assertTrue(effs[1].data.get("keep"))
        self.assertEqual(effs[2].data["to"], "self_each")

    def test_activated_it(self):
        c = card("Test Myojin", "{4}{R}", "Creature — Spirit", "Remove a +1/+1 counter from ~: It deals 7 damage to "
                 "each of up to three targets.", 4, 4)
        self.assertEqual(c.unsupported, [])
        self.assertEqual([e.kind for e in c.activated[0].effects], ["damage"] * 3)

    def test_activated_it_with_another_object_in_the_cost_stays(self):
        from mtgsim.self_trigger_it import activated_it
        for cost in ("Sacrifice a creature", "{1}, Exile a creature card from your graveyard", "Discard a card"):
            self.assertIsNone(activated_it(cost, "It deals 2 damage to any target."), cost)
        self.assertEqual(activated_it("{2}, {T}", "It deals 2 damage to any target."), "~ deals 2 damage to any target.")


class Resolving(Base):
    def test_both_bites(self):
        golem, bear = self.perm(GOLEM, self.a), self.perm(BEAR, self.b)
        c = self.spell(LINE)
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [golem, bear, None], card=c, name=c.name))
        self.game.resolve_top()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(golem.damage, 3)

    def test_face(self):
        golem = self.perm(GOLEM, self.a)
        c = self.spell(LINE)
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [golem, self.b, None], card=c, name=c.name))
        self.game.resolve_top()
        self.assertEqual((self.b.life, golem.damage), (17, 3))


class DefaultAI(Base):
    def test_ai_aims_it_at_their_creature(self):
        golem, bear = self.perm(GOLEM, self.a), self.perm(BEAR, self.b)
        spell = card("Test Destruct", "{U}", "Sorcery", LINE)
        self.perm(ISLAND, self.a)
        self.a.hand = [spell]
        self.game.step = "main2"
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand, "the AI didn't cast it")
        self.assertNotIn(bear, self.b.battlefield)
        self.assertIn(golem, self.a.battlefield)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Self-Destruct", "Myojin of Roaring Blades"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()

""""Protection from <card type / creature type>" (#326, mtgsim/protection_types.py): the keyword reads on keyword lines
("protection from Demons and from Dragons"), through equipment ("has protection from instants and from sorceries")
and every DEBT rule follows engine.state.protected_from."""
import unittest

from mtgsim.engine import StackItem
from mtgsim.engine.state import can_block, protected_from

from tests.test_cx_grammar import BEAR, DB_FILE, Base, card

ANGEL = card("Test Angel", "{3}{W}{W}", "Creature — Angel",
             "Flying, protection from Demons and from Dragons", 5, 5)
DEMON = card("Test Demon", "{3}{B}", "Creature — Demon", "Flying", 4, 4)
SHAPESHIFTER = card("Test Shifter", "{2}", "Creature — Shapeshifter", "Changeling\nFlying", 2, 2)
SHOCK = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to any target.")
ARCANE = card("Test Arcane Bolt", "{R}", "Instant — Arcane", "~ deals 2 damage to any target.")
FOX = card("Test Fox", "{2}{W}", "Creature — Fox Shaman", "Protection from Spirits and from Arcane", 2, 2)


class Parsing(unittest.TestCase):
    def test_keywords(self):
        self.assertEqual(ANGEL.unsupported, [])
        self.assertLessEqual({"protection from demons", "protection from dragons"}, set(ANGEL.keywords))
        self.assertIn("protection from arcane", FOX.keywords)
        for text in ("Protection from creatures", "Protection from planeswalkers and from Wizards",
                     "Protection from Elves"):
            self.assertEqual(card("Test Thing", "{1}", "Creature — Human", text, 1, 1).unsupported, [], text)

    def test_unknown_words_stay_unsupported(self):
        for text in ("Protection from Foos", "Protection from Demons and from Foos",     # "everything" is read since #646
                     "Protection from each color"):
            self.assertNotEqual(card("Test Thing", "{1}", "Creature — Human", text, 1, 1).unsupported, [], text)


class Rules(Base):
    def test_damage_from_a_demon_is_prevented_not_from_others(self):
        angel, demon, bear = self.perm(ANGEL, self.a), self.perm(DEMON, self.b), self.perm(BEAR, self.b)
        self.game.deal_damage(angel, 4, by=self.b, cause="demon", source=demon)
        self.assertEqual(angel.damage, 0)
        self.game.deal_damage(angel, 2, by=self.b, cause="bear", source=bear)
        self.assertEqual(angel.damage, 2)

    def test_demons_cant_block_it(self):
        angel, demon = self.perm(ANGEL, self.a), self.perm(DEMON, self.b)
        other = self.perm(card("Test Bird", "{1}", "Creature — Bird", "Flying", 1, 1), self.b)
        self.assertFalse(can_block(demon, angel))
        self.assertTrue(can_block(other, angel))

    def test_changeling_has_every_creature_type(self):
        angel, shifter = self.perm(ANGEL, self.a), self.perm(SHAPESHIFTER, self.b)
        self.assertTrue(protected_from(angel, shifter))

    def test_arcane_spell_cant_target_it(self):
        fox = self.perm(FOX, self.a)
        with self.game.targeting(ARCANE):
            self.assertNotIn(fox, self.game.legal_targets(self.b, ARCANE.spell_effects[0]))
        with self.game.targeting(SHOCK):
            self.assertIn(fox, self.game.legal_targets(self.b, SHOCK.spell_effects[0]))

    def test_equipment_grants_protection_from_instants(self):
        sword = card("Test Sword", "{3}", "Artifact — Equipment", "Equipped creature gets +2/+2 and has protection "
                     "from instants and from sorceries.\nEquip {2}")
        self.assertEqual(sword.unsupported, [])
        bear, eq = self.perm(BEAR, self.a), self.perm(sword, self.a)
        eq.attached_to = bear
        self.assertTrue(bear.has("protection from instants"))
        with self.game.targeting(SHOCK):
            self.assertNotIn(bear, self.game.legal_targets(self.b, SHOCK.spell_effects[0]))
        self.game.stack.append(StackItem(self.b, list(SHOCK.spell_effects), [bear], card=SHOCK))
        self.game.resolve_top()
        self.assertEqual(bear.damage, 0)


class DefaultAI(Base):
    def test_ai_doesnt_aim_an_arcane_bolt_at_the_fox(self):
        fox, bear = self.perm(FOX, self.b), self.perm(BEAR, self.b)
        bolt = card("Test Arcane Bolt", "{U}", "Sorcery — Arcane", "~ deals 2 damage to target creature.")
        self.perm(card("Test Island", "", "Land — Island", "({T}: Add {U}.)"), self.a)
        self.a.hand = [bolt]
        self.game.step = "main2"
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn(fox, self.b.battlefield)
        self.assertNotIn(bear, self.b.battlefield)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Baneslayer Angel", "Greensleeves, Maro-Sorcerer", "Kitsune Riftwalker",
                     "Sword of Wealth and Power", "Mystic Crusader", "Holy Mantle"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()

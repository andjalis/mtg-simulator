"""#633: exalted, training, dethrone and riot granted to a group (mtgsim.kw_trigger_grants, counted keywords)."""
import unittest

from mtgsim.coverage import card_coverage
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, card

RHYTHM = card("Test Rhythm", "{1}{R}{G}", "Enchantment", "Nontoken creatures you control have riot.")
ZARDA = card("Test Zarda", "{2}{W}", "Legendary Creature — Human Wizard", "Other Wizards you control have exalted.",
             2, 2)
TRAINER = card("Test Trainer", "{2}{W}", "Creature — Human", "Creature tokens you control have training.", 2, 2)
HERO = card("Test Hero", "{1}{W}", "Creature — Human Wizard", "", 2, 2)


class Parsing(unittest.TestCase):
    def test_lines(self):
        for c in (RHYTHM, ZARDA, TRAINER):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(RHYTHM.static_keyword_grants[0][1], ("riot",))

    def test_refusals(self):
        for text in ("Creatures you control have myriad.", "Other Slivers you control have outlast {2}.",
                     "Creatures you control with exalted have riot."):
            c = card("Test Refused", "{3}", "Enchantment", text)
            self.assertTrue(c.unsupported, text)


class Engine(Base):
    def test_exalted_for_other_wizards(self):
        zarda = self.perm(ZARDA, self.a)
        hero = self.perm(HERO, self.a)
        bear = self.perm(BEAR, self.a)
        self.assertEqual((hero.exalted_count, zarda.exalted_count, bear.exalted_count), (1, 0, 0))
        self.game.fire(self.a, "attacks_alone", context=bear)
        self.game.settle()
        self.assertEqual(bear.power, 3)                              # one exalted instance (the other Wizard's)

    def test_riot_on_entering(self):
        self.perm(RHYTHM, self.a)
        self.game.turn, self.game.step = 1, "main1"
        self.game.enter_battlefield(self.a, BEAR)
        bear = next(x for x in self.a.battlefield if x.card.name == "Grizzly Bears")
        self.assertTrue(bear.has("haste") or bear.p1 == 1)
        token = card("Test Token", "", "Creature — Soldier", "", 1, 1)
        token.is_token = True
        self.game.enter_battlefield(self.a, token)
        tok = next(x for x in self.a.battlefield if x.card.name == "Test Token")
        self.assertFalse(tok.has("haste") or tok.p1)                 # nontoken only

    def test_training_for_tokens(self):
        self.perm(TRAINER, self.a)
        token = card("Test Token", "", "Creature — Soldier", "", 1, 1)
        token.is_token = True
        tok = self.perm(token, self.a)
        bear = self.perm(BEAR, self.a)
        self.assertTrue(tok.has("training"))
        self.assertFalse(bear.has("training"))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Rhythm of the Wild", "Elder Arthur Maxson"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()

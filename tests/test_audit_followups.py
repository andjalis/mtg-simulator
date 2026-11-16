"""Audit 2026-11-16 (opus-cast) follow-ups: #824 "target nonland permanent an opponent controls with mana value N or
less" allowed the caster's own permanents; #833 Depopulate's "each player who controls a multicolored creature
draws a card" was matched and dropped; #827 Deceit's two spent-colour triggers and impulse draws, and #815
"any color that a land ... could produce" (Fellwar Stone), counted full."""
import unittest

from mtgsim.engine import Permanent, StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import card, BEAR

RIP = card("Test Rip", "{W}", "Enchantment", "When ~ enters, exile target nonland permanent an opponent controls with "
                                             "mana value 2 or less until ~ leaves the battlefield.")
RING = card("Test Ring", "{1}{W}", "Enchantment", "When ~ enters, exile target nonland permanent an opponent controls "
                                                  "until ~ leaves the battlefield.")
DEPOP = card("Test Depopulate", "{2}{W}{W}", "Instant", "Each player who controls a multicolored creature draws a card. "
                                                        "Then destroy all creatures.")
GOLD = card("Test Gold", "{W}{U}", "Creature — Human", "", 2, 2)
ISLAND = card("Island", "", "Basic Land — Island", "({T}: Add {U}.)")


class SeamRip(Base):
    def legal(self, c):
        eff = c.triggers[0].effects[0]
        with self.game.targeting(c):
            return self.game.legal_targets(self.a, eff)

    def test_only_their_permanents(self):
        mine, theirs = Permanent(BEAR, self.a), Permanent(BEAR, self.b)
        self.a.battlefield, self.b.battlefield = [mine], [theirs]
        self.assertEqual(self.legal(RIP), [theirs])

    def test_mana_value_cap_kept(self):
        big = Permanent(card("Test Big", "{3}", "Creature — Beast", "", 3, 3), self.b)
        self.b.battlefield = [big]
        self.assertEqual(self.legal(RIP), [])

    def test_uncapped_wording_unchanged(self):
        self.assertEqual(RING.triggers[0].effects[0].filter, "opp")


class Depopulate(Base):
    def resolve(self):
        item = StackItem(self.a, list(DEPOP.spell_effects), [None] * len(DEPOP.spell_effects), card=DEPOP,
                         name=DEPOP.name)
        self.game.stack.append(item)
        self.game.resolve_top()
        self.game.settle()

    def test_parse(self):
        self.assertEqual([e.kind for e in DEPOP.spell_effects], ["draw_each", "wrath"])

    def test_only_a_multicolored_creatures_controller_draws(self):
        self.a.battlefield, self.b.battlefield = [Permanent(GOLD, self.a)], [Permanent(BEAR, self.b)]
        self.a.library, self.b.library = [ISLAND] * 3, [ISLAND] * 3
        self.a.hand, self.b.hand = [], []
        self.resolve()
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (1, 0))
        self.assertFalse(any(p.is_creature for p in self.a.battlefield + self.b.battlefield))

    def test_no_multicolored_creature_no_draw(self):
        self.a.battlefield = [Permanent(BEAR, self.a)]
        self.a.library, self.a.hand = [ISLAND] * 3, []
        self.resolve()
        self.assertEqual(self.a.hand, [])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Seam Rip", "Portable Hole", "Solitary Cell"):
            eff = db.get(name).triggers[0].effects[0]
            self.assertEqual(eff.data.get("selector"), {"controller": "opp"}, name)
        self.assertEqual(db.get("Depopulate").spell_effects[0].kind, "draw_each")
        for name in ("Deceit", "Vibrance", "Cori Mountain Monastery", "Act on Impulse", "Fellwar Stone", "Exotic Orchard"):
            self.assertEqual(card_coverage(db.get(name)).status, "simplified", name)
        self.assertEqual(card_coverage(db.get("Depopulate")).status, "full")


if __name__ == "__main__":
    unittest.main()

""""Instead" riders on a prevention shield (#333): "If it's a green creature, prevent the next 2 damage instead."
(Elvish Healer) and the kicked "prevent the next 4 damage ... instead" (Orim's Touch)."""
import unittest

from mtgsim.engine import StackItem

from tests.test_cx_grammar import BEAR, DB_FILE, Base, card

HEALER = card("Test Healer", "{2}{W}", "Creature — Elf Cleric", "{T}: Prevent the next 1 damage that would be dealt to "
              "any target this turn. If it's a green creature, prevent the next 2 damage instead.", 1, 2)
BLUE = card("Test Blue", "{1}{U}", "Creature — Merfolk", "", 2, 2)


class Parsing(unittest.TestCase):
    def test_rider_on_the_shield(self):
        self.assertEqual(HEALER.unsupported, [])
        eff = HEALER.activated[0].effects[0]
        self.assertEqual((eff.kind, eff.amount, eff.data["instead"]["amount"]), ("prevent_next", 1, 2))

    def test_refusals(self):
        for text in ("{T}: You gain 1 life. If it's a green creature, prevent the next 2 damage instead.",
                     "{T}: Prevent the next 1 damage that would be dealt to you this turn. If it's a green creature, "
                     "prevent the next 2 damage instead.",
                     "{T}: Prevent the next 1 damage that would be dealt to any target this turn. If it's a Foo or "
                     "the like, prevent the next 2 damage instead."):
            self.assertNotEqual(card("Test Thing", "{1}", "Creature — Elf", text, 1, 1).unsupported, [], text)


class Resolving(Base):
    def shield(self, target):
        src = self.perm(HEALER, self.a)
        effs = list(HEALER.activated[0].effects)
        self.game.stack.append(StackItem(self.a, effs, [target], source=src, kind="ability", name=HEALER.name))
        self.game.resolve_top()

    def test_green_creature_gets_two(self):
        bear = self.perm(BEAR, self.a)                  # Grizzly Bears: green
        self.shield(bear)
        self.assertEqual(bear.prevent_next, 2)

    def test_other_creature_gets_one(self):
        blue = self.perm(BLUE, self.a)
        self.shield(blue)
        self.assertEqual(blue.prevent_next, 1)

    def test_player_gets_one(self):
        self.shield(self.a)
        self.assertEqual(self.a.prevent_next, 1)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(Base):
    def setUp(self):
        super().setUp()
        from mtgsim.carddb import CardDB
        self.db = CardDB()

    def test_cards_parse_fully(self):
        from mtgsim.coverage import FULL, card_coverage
        for name in ("Elvish Healer", "Orim's Touch"):
            row = card_coverage(self.db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))

    def test_orims_touch_kicked_shield(self):
        touch = self.db.get("Orim's Touch")
        self.assertEqual([e.amount for e in touch.spell_effects if e.kind == "prevent_next"], [2])
        kicker = next(a for a in touch.alt_costs if a.kind == "kicker")
        self.assertEqual([e.amount for e in kicker.effects if e.kind == "prevent_next"], [4])
        bear = self.perm(BEAR, self.a)
        self.game.stack.append(StackItem(self.a, list(kicker.effects), [bear], card=touch, name=touch.name))
        self.game.resolve_top()
        self.assertEqual(bear.prevent_next, 4)


if __name__ == "__main__":
    unittest.main()

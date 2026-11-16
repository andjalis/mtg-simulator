"""#646 slice 8: Ward with non-mana costs (CR 702.21, mtgsim.ward_costs)."""
import unittest

from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent, StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, SHOCK, card


def warded(text, p=4, t=4):
    return card("Test Warded", "{3}", "Creature — Horror", text, p, t)


RIPPER = warded("Flying\nWard—Sacrifice a creature.")
GORGER = warded("Menace, lifelink\nWard—Pay life equal to ~'s power.", 3, 5)
SOCIETY = warded("Ward—Get five poison counters.")
TITANIA = warded("Ward—Discard a card or pay {2}.")
FEROX = warded("Ward—Collect evidence 4.")


class Parsing(unittest.TestCase):
    def test_positives(self):
        for c, spec in ((RIPPER, {"sacrifice": "creature"}), (GORGER, {"life_power": True}),
                        (SOCIETY, {"poison": 5}), (TITANIA, {"discard_or": 2}), (FEROX, {"evidence": 4})):
            self.assertEqual(c.unsupported, [], c.name)
            self.assertEqual(c.advanced_rules["ward_cost"], spec)

    def test_refusals(self):
        for text in ("Ward—Sacrifice a blorb.", "Ward—Tap an untapped creature you control.",
                     "Ward—Discard two cards.", "Ward—Pay life equal to its toughness."):
            c = warded(text)
            self.assertTrue(c.unsupported, text)
            self.assertNotIn("ward_cost", c.advanced_rules, text)


class Engine(Base):
    def shock(self, target):
        """b casts Shock at a's warded creature; the ward trigger goes on the stack above it (CR 702.21a)."""
        item = StackItem(self.b, list(SHOCK.spell_effects), [target], card=SHOCK, name="Shock")
        self.game.stack.append(item)
        self.game.check_ward(item)
        self.game.settle()
        return item

    def test_sacrifice_or_countered(self):
        """CR 702.21a: counter it unless that player pays (sacrifices a creature)."""
        x = self.perm(GORGER, self.a)
        x2 = self.perm(RIPPER, self.a)
        self.shock(x2)                                       # b has no creature: countered
        self.assertEqual(x2.damage, 0)
        bear = self.perm(BEAR, self.b)
        self.shock(x2)
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(x2.damage, 2)
        del x

    def test_life_equal_to_power(self):
        x = self.perm(GORGER, self.a)
        x.counters["+1/+1"] = 2                              # power 5 when the trigger resolves
        self.shock(x)
        self.assertEqual(self.b.life, 15)
        self.assertEqual(x.damage, 2)

    def test_poison(self):
        x = self.perm(SOCIETY, self.a)
        self.shock(x)
        self.assertEqual(self.b.counters.get("poison"), 5)
        self.b.counters["poison"] = 5
        self.shock(x)                                        # five more would be lethal: let it be countered
        self.assertEqual(self.b.counters["poison"], 5)
        self.assertEqual(x.damage, 2)

    def test_discard_or_pay(self):
        x = self.perm(TITANIA, self.a)
        self.b.battlefield = [Permanent(MOUNTAIN, self.b) for _ in range(2)]
        self.b.hand = [BEAR]
        self.shock(x)
        self.assertEqual(self.b.hand, [BEAR])                # paid {2} instead
        self.assertTrue(all(m.tapped for m in self.b.battlefield))
        self.shock(x)
        self.assertEqual(self.b.hand, [])                    # no mana left: discarded

    def test_collect_evidence(self):
        x = self.perm(FEROX, self.a)
        self.b.graveyard = [BEAR, ISLAND]                    # mana value 2: not enough
        self.shock(x)
        self.assertEqual(x.damage, 0)
        self.b.graveyard = [BEAR, BEAR, ISLAND]
        self.shock(x)
        self.assertEqual(x.damage, 2)
        self.assertEqual([c.name for c in self.b.graveyard], ["Island", "Shock"])    # the Bears exiled; Shock resolved


class HeuristicUse(Base):
    def test_ai_does_not_aim_into_a_ward_it_cannot_pay(self):
        from mtgsim.ai import _ward_payable
        x = self.perm(RIPPER, self.a)
        self.assertFalse(_ward_payable(self.game, self.b, x, SHOCK))     # nothing to sacrifice
        self.perm(BEAR, self.b)
        self.assertTrue(_ward_payable(self.game, self.b, x, SHOCK))
        s = self.perm(SOCIETY, self.a)
        self.b.counters["poison"] = 4
        self.assertFalse(_ward_payable(self.game, self.b, s, SHOCK))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Phyrexian Fleshgorger", "Raubahn, Bull of Ala Mhigo", "Vein Ripper", "Ulamog's Dreadsire",
                     "The Serpent Society", "Titania, Rugged Rumbler", "Axebane Ferox"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))
        self.assertEqual(card_coverage(db.get("Sauron, the Dark Lord")).status, "partial")


if __name__ == "__main__":
    unittest.main()

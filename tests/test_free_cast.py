"""#625 FREE-CAST: "You may cast a <kind> spell [with mana value N or less] from your hand without paying its mana
cost" (mtgsim.free_cast)."""
import unittest

from mtgsim.cards.parse import _parse_effects
from mtgsim.coverage import card_coverage
from mtgsim.engine import Permanent, StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

SHOCK = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to any target.")
GIANT = card("Test Giant", "{2}{R}{R}", "Creature — Giant", "", 4, 4)
DRAGON = card("Test Dragon", "{4}{R}{R}", "Creature — Dragon", "Flying", 6, 6)
TOME = card("Test Tome", "{3}", "Artifact", "{T}: Draw a card.")
DIVINATION = card("Test Divination", "{2}{U}", "Sorcery", "Draw two cards.")


def free(text):
    effects, bad = _parse_effects(text)
    return effects, bad


class Parsing(unittest.TestCase):
    def one(self, text):
        effects, bad = free(text)
        self.assertEqual(bad, [], text)
        self.assertEqual([e.kind for e in effects], ["hand_free_cast"], text)
        return effects[0]

    def test_wordings(self):
        e = self.one("You may cast a spell with mana value 4 or less from your hand without paying its mana cost.")
        self.assertEqual((e.amount, e.data), (4, {"desc": "a card", "capped": True}))
        e = self.one("You may cast an instant or sorcery spell from your hand without paying its mana cost.")
        self.assertEqual(e.data, {"desc": "a instant card or a sorcery card"})
        e = self.one("You may cast a noncreature or Robot spell from your hand without paying its mana cost.")
        self.assertEqual(e.data["desc"], "a noncreature card or a Robot card")
        e = self.one("You may cast a spell with mana value X or less from your hand without paying its mana cost.")
        self.assertTrue(e.data["x"])
        e = self.one("You may cast a sorcery spell from your hand with mana value less than or equal to that damage "
                     "without paying its mana cost.")
        self.assertTrue(e.data["that_much"])
        e = self.one("You may cast a spell with mana value X or less from your hand without paying its mana cost, "
                     "where X is the number of attacking creatures.")
        self.assertEqual(e.amount, 1)
        self.assertTrue(e.data["xq"])
        e = self.one("Then you may cast a spell from your hand with mana value 8 or less without paying its mana cost.")
        self.assertEqual(e.amount, 8)

    def test_refusals(self):
        for text in (
                "You may cast a spell with equal or lesser mana value from your hand without paying its mana cost.",
                "You may cast a spell that shares a card type with it from your hand without paying its mana cost.",
                "You may cast spells from your hand without paying their mana costs.",            # a static
                "You may cast a spell from your hand or the top of your library without paying its mana cost.",
                "You may cast a spell from your hand without paying its mana cost if it has the same name as a spell "
                "that was cast this turn.",
                "Once during each of your turns, you may cast an instant or sorcery spell from your hand without "
                "paying its mana cost.",
                "You may cast a spell with mana value X or less from your hand without paying its mana cost, where X "
                "is the number of foos you bar.",
                "You may cast a spell with mana value 4 or less from your hand."):                # paid normally
            effects, bad = free(text)
            self.assertNotIn("hand_free_cast", [e.kind for e in effects], text)
            self.assertTrue(bad, text)


class Engine(Base):
    def resolve(self, text, *, x=0, context=None):
        effects, bad = free(text)
        self.assertEqual(bad, [])
        item = StackItem(self.a, effects, [None] * len(effects), name="test", kind="trigger", context=context)
        item.x = x
        self.game.stack.append(item)
        self.game.resolve_top()

    def test_casts_the_best_spell_under_the_cap_for_free(self):
        self.a.hand = [DRAGON, GIANT, BEAR]
        self.resolve("You may cast a spell with mana value 4 or less from your hand without paying its mana cost.")
        self.assertEqual(sorted(x.card.name for x in self.a.battlefield), ["Test Giant"])
        self.assertEqual(sorted(c.name for c in self.a.hand), ["Grizzly Bears", "Test Dragon"])

    def test_no_mana_is_needed_and_the_spell_resolves(self):
        self.a.hand = [DIVINATION]
        before = len(self.a.library)
        self.resolve("You may cast a sorcery spell from your hand without paying its mana cost.")
        self.assertEqual(len(self.a.library), before - 2)          # Divination drew two
        self.assertIn("Test Divination", [c.name for c in self.a.graveyard])

    def test_kind_filter(self):
        self.a.hand = [GIANT, TOME]
        self.resolve("You may cast a noncreature spell from your hand without paying its mana cost.")
        self.assertEqual([x.card.name for x in self.a.battlefield], ["Test Tome"])
        self.assertEqual([c.name for c in self.a.hand], ["Test Giant"])

    def test_x_cap(self):
        self.a.hand = [GIANT]
        self.resolve("You may cast a spell with mana value X or less from your hand without paying its mana cost.",
                     x=3)
        self.assertEqual([c.name for c in self.a.hand], ["Test Giant"])     # mana value 4 > 3
        self.resolve("You may cast a spell with mana value X or less from your hand without paying its mana cost.",
                     x=4)
        self.assertEqual([x.card.name for x in self.a.battlefield], ["Test Giant"])

    def test_where_x_count(self):
        self.a.hand = [GIANT]
        for _ in range(3):
            self.perm(BEAR, self.a).attacking = True
        self.game.attackers = [x for x in self.a.battlefield]
        text = ("You may cast a spell with mana value X or less from your hand without paying its mana cost, where X "
                "is the number of attacking creatures.")
        self.resolve(text)
        self.assertEqual([c.name for c in self.a.hand], ["Test Giant"])     # three attackers: 4 is too much
        self.game.attackers.append(self.perm(BEAR, self.a))
        self.resolve(text)
        self.assertIn("Test Giant", [x.card.name for x in self.a.battlefield])

    def test_targets_go_to_the_opponent(self):
        self.a.hand = [SHOCK]
        life = self.b.life
        self.resolve("You may cast an instant or sorcery spell from your hand without paying its mana cost.")
        self.assertEqual(self.b.life, life - 2)
        self.assertEqual(self.a.life, 20)

    def test_nothing_castable_does_nothing(self):
        self.a.hand = [ISLAND, DRAGON]
        self.resolve("You may cast a spell with mana value 3 or less from your hand without paying its mana cost.")
        self.assertEqual(self.a.battlefield, [])
        self.assertEqual(len(self.a.hand), 2)


class HeuristicUse(Base):
    def test_ai_casts_an_expertise_and_gets_the_free_spell(self):
        expertise = card("Test Expertise", "{2}{R}{R}", "Sorcery",
                         "You may cast a spell with mana value 3 or less from your hand without paying its mana cost.")
        self.assertEqual(expertise.unsupported, [])
        self.a.hand = [expertise, SHOCK]
        self.a.battlefield = [Permanent(MOUNTAIN, self.a) for _ in range(4)]
        life = self.b.life
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn("Test Expertise", [c.name for c in self.a.graveyard])
        self.assertIn("Test Shock", [c.name for c in self.a.graveyard])
        self.assertEqual(self.b.life, life - 2)                     # the free Shock went at the opponent

    def test_ai_activates_only_with_something_to_cast(self):
        adept = card("Test Adept", "{1}{U}", "Creature — Human Wizard",
                     "{2}{U}, {T}: You may cast an instant or sorcery spell from your hand without paying its mana "
                     "cost.", 1, 1)
        big = card("Test Big Draw", "{6}{U}{U}", "Sorcery", "Draw three cards.")
        for hand, used in (([], False), ([big], True)):
            self.setUp()
            self.game.step = "main2"
            self.a.hand = list(hand)
            self.a.battlefield = [Permanent(ISLAND, self.a) for _ in range(3)] + [Permanent(adept, self.a)]
            for x in self.a.battlefield:
                x.sick = False
            self.a.ai.use_abilities(self.game, self.a)
            self.assertEqual(self.a.battlefield[-1].tapped, used, hand)
            self.assertEqual("Test Big Draw" in [c.name for c in self.a.graveyard], used)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Baral's Expertise", "Sram's Expertise", "Yahenni's Expertise", "Rishkar's Expertise",
                     "Electrodominance", "Epistolary Librarian", "Aisha of Sparks and Smoke", "Maelstrom Archangel",
                     "Wildfire Eternal", "Surtland Elementalist", "Yue, the Moon Spirit", "Omnispell Adept",
                     "Marvo, Deep Operative", "Buster Sword", "Omniscience"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))

    def test_near_misses_stay_partial(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        # (Omniscience is read since #667: group_altcost's "cast spells from your hand without paying their mana costs")
        for name in ("Reinterpret", "Counterlash", "Zaffai and the Tempests", "Twinning Glass",
                     "One with the Multiverse"):
            self.assertEqual(card_coverage(db.get(name)).status, "partial", name)


if __name__ == "__main__":
    unittest.main()

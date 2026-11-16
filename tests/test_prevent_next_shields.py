"""#333 follow-up: qualified single targets ("target Cleric or Wizard creature", "target green creature"), the
combat-only and by-source shields (Decorated Griffin, Barbed Wire, as cx_shields rules with a budget), "player or
planeswalker" shields (Noble Vestige) and Samite Alchemist's "It doesn't untap during your next untap step"."""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem
from mtgsim.engine.policy import protective_ability

from tests.test_cx_grammar import BEAR, DB_FILE, Base, card

CLERIC = card("Test Cleric", "{W}", "Creature — Human Cleric", "", 1, 1)
WALKER = card("Test Walker", "{3}", "Legendary Planeswalker — Testy", "", 0, 0)
MAGE = card("Test Mage", "{2}{U}", "Creature — Human Wizard",
            "{U}: Prevent the next 1 damage that would be dealt to target Cleric or Wizard creature this turn.", 2, 2)
SHOCK = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to any target.")


class Parsing(unittest.TestCase):
    def one(self, text):
        effects, bad = _parse_effects(text)
        self.assertFalse(bad, text)
        self.assertEqual(len(effects), 1)
        return effects[0]

    def test_qualified_targets(self):
        e = self.one("Prevent the next 1 damage that would be dealt to target Cleric or Wizard creature this turn.")
        self.assertEqual((e.kind, e.amount, e.target, e.data), ("prevent_next", 1, "creature",
                                                                {"cx_desc": "Cleric or Wizard creature"}))
        e = self.one("Prevent the next 2 damage that would be dealt this turn to target green creature.")
        self.assertEqual(e.data["selector"], {"colors": ["G"], "types_all": ["creature"]})

    def test_budget_shields(self):
        e = self.one("Prevent the next 1 combat damage that would be dealt to you this turn.")
        self.assertEqual((e.kind, e.data["rule"]), ("cx_shield", {"combat": True, "to": ("you",), "by": ("any",),
                                                                  "budget": 1}))
        e = self.one("Prevent the next 1 damage that would be dealt by ~ this turn.")
        self.assertEqual(e.data["rule"], {"combat": None, "to": ("any",), "by": ("self",), "budget": 1})

    def test_player_or_planeswalker_keeps_the_planeswalker(self):
        e = self.one("Prevent the next 1 damage that would be dealt to target player or planeswalker this turn.")
        self.assertEqual((e.target, e.data.get("or_pw")), ("player", True))


class Resolving(Base):
    def run_effects(self, effects, targets, source=None):
        self.game.stack.append(StackItem(self.a, list(effects), targets, source=source, kind="ability", name="t"))
        self.game.resolve_top()

    def test_cleric_or_wizard_shield(self):
        cleric, bear = self.perm(CLERIC, self.a), self.perm(BEAR, self.a)
        eff = MAGE.activated[0].effects[0]
        legal = self.game.legal_targets(self.a, eff)
        self.assertIn(cleric, legal)
        self.assertNotIn(bear, legal)
        self.run_effects([eff], [cleric])
        self.game.deal_damage(cleric, 1, by=self.b, cause="test")
        self.assertIn(cleric, self.a.battlefield)

    def test_combat_only_shield(self):
        effects, _ = _parse_effects("Prevent the next 2 combat damage that would be dealt to you this turn.")
        attacker = self.perm(BEAR, self.b)
        self.run_effects(effects, [None])
        self.game.deal_damage(self.a, 1, by=self.b, cause="ping", source=attacker)      # noncombat: not prevented
        self.assertEqual(self.a.life, 19)
        self.game.deal_damage(self.a, 3, by=self.b, cause="combat", source=attacker, combat=True)
        self.assertEqual(self.a.life, 18)                                               # 2 of 3 prevented
        self.game.deal_damage(self.a, 1, by=self.b, cause="combat", source=attacker, combat=True)
        self.assertEqual(self.a.life, 17)                                               # the shield is used up

    def test_source_shield_filters_on_the_source(self):
        wire = card("Test Wire", "{3}", "Artifact", "{2}: Prevent the next 1 damage that would be dealt by ~ this turn.")
        self.assertEqual(wire.unsupported, [])
        src, other = self.perm(wire, self.a), self.perm(BEAR, self.a)
        self.run_effects(wire.activated[0].effects, [None], source=src)
        self.game.deal_damage(self.b, 1, by=self.a, cause="other", source=other)       # another source: dealt
        self.assertEqual(self.b.life, 19)
        self.game.deal_damage(self.b, 2, by=self.a, cause="wire", source=src)          # 1 of 2 prevented
        self.assertEqual(self.b.life, 18)
        self.game.deal_damage(self.a, 1, by=self.a, cause="wire", source=src)          # used up
        self.assertEqual(self.a.life, 19)

    def test_shield_expires_with_the_turn(self):
        effects, _ = _parse_effects("Prevent the next 1 combat damage that would be dealt to you this turn.")
        attacker = self.perm(BEAR, self.b)
        self.run_effects(effects, [None])
        self.game.turn += 1
        self.game.deal_damage(self.a, 1, by=self.b, cause="combat", source=attacker, combat=True)
        self.assertEqual(self.a.life, 19)

    def test_planeswalker_is_a_legal_shield_target(self):
        effects, _ = _parse_effects("Prevent the next 1 damage that would be dealt to target player or planeswalker "
                                    "this turn.")
        walker = self.perm(WALKER, self.a)
        walker.counters["loyalty"] = 3
        self.assertIn(walker, self.game.legal_targets(self.a, effects[0]))

    def test_samite_alchemist_skips_only_your_untap(self):
        alch = card("Test Alchemist", "{W}", "Creature — Human Cleric", "{W}{W}, {T}: Prevent the next 4 damage "
                    "that would be dealt this turn to target creature you control. Tap that creature. It doesn't "
                    "untap during your next untap step.", 0, 2)
        self.assertEqual(alch.unsupported, [])
        bear = self.perm(BEAR, self.a)
        self.run_effects(alch.activated[0].effects, [bear, None, None])
        self.assertTrue(bear.tapped)
        self.assertEqual((bear.prevent_next, bear.skip_untap), (4, 1))
        theirs = self.perm(BEAR, self.b)        # "your next untap step" of their creature: no effect
        effects, _ = _parse_effects("Tap target creature. It doesn't untap during your next untap step.")
        self.assertEqual(effects[-1].data.get("yours_only"), True)
        self.run_effects(effects, [theirs, None])
        self.assertEqual(theirs.skip_untap, 0)


class DefaultAI(Base):
    def test_ai_shields_a_cleric_but_not_a_bear(self):
        self.perm(MAGE, self.a).sick = False
        self.perm(card("Test Island", "", "Land — Island", "({T}: Add {U}.)"), self.a)
        cleric, bear = self.perm(card("Test Cleric", "{W}", "Creature — Human Cleric", "", 1, 2), self.a), \
            self.perm(card("Test Bear", "{1}{G}", "Creature — Bear", "", 1, 2), self.a)
        shock = StackItem(self.b, list(SHOCK.spell_effects), [cleric], card=SHOCK)
        action = protective_ability(self.game, self.a, shock, cleric)
        self.assertIsNotNone(action)
        self.assertEqual(action[3][0], cleric)
        shock = StackItem(self.b, list(SHOCK.spell_effects), [bear], card=SHOCK)
        self.assertIsNone(protective_ability(self.game, self.a, shock, bear))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Decorated Griffin", "Barbed Wire", "Samite Alchemist", "Noble Vestige"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()
